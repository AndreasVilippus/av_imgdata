#!/usr/bin/env python3
import io
import json
import os
import importlib
import importlib.util
import hashlib
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.request
import zipfile
from contextlib import nullcontext
from copy import deepcopy
from importlib import metadata as importlib_metadata
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from time import monotonic, sleep
from threading import Lock, Thread
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from api.session_manager import SessionBootstrapRequired, SessionManager, SessionManagerError
from handler.core_handler import CoreHandler
from handler.exiftool_handler import ExifToolHandler
from handler.file_handler import FileHandler, SidecarLookupCache
from handler.photos_handler import PhotosHandler, PhotosLookupCache
from models.file_face import FileFace
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from models.photos_face import PhotosFace
from parser.metadata_parser import MetadataParser, NS_ACD, NS_MICROSOFT, NS_MWG_REGIONS
from services.bbox_normalizer import denormalize_xmp_face, from_photos, from_xmp, to_display_face
from services.config_service import ConfigService
from services.checks_workflow_service import ChecksWorkflowService
from services.exiftool_service import ExifToolService
from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector
from services.face_embedder import InsightFaceEmbedder
from services.face_frame_standardization_service import FaceFrameStandardizationService
from services.face_recognition_service import FaceRecognitionService
from services.image_decode_service import ImageDecodeService
from services.face_coordinate_precision import FACE_COORDINATE_DIGITS, FACE_COORDINATE_TOLERANCE, format_face_coordinate, round_face_coordinate
from services.face_matcher import FaceMatcher, compute
from services.face_match_mutation_service import FaceMatchMutationService
from services.face_match_findings_service import FaceMatchFindingsService
from services.face_match_workflow_service import FaceMatchWorkflowService
from services.file_analysis_service import FileAnalysisService
from services.name_mapping_service import NameMappingService
from av_imgdata.db.repositories.face_suppressions import FaceSuppressionRepository
from services.runtime_operation_service import RuntimeOperationService
from services.runtime_state_service import RuntimeStateService
from services.status_payload_builder import StatusPayloadBuilder
from services.write_lock_service import WriteLockService


class ImgDataOperationError(Exception):
    def __init__(self, message: str, details: Dict[str, Any]):
        super().__init__(message)
        self.details = details


class WriteDebouncer:
    def __init__(
        self,
        min_interval_seconds: int,
        min_entry_delta: int,
        *,
        now_func: Callable[[], float] = monotonic,
    ):
        self.min_interval_seconds = max(0, int(min_interval_seconds))
        self.min_entry_delta = max(1, int(min_entry_delta))
        self._now_func = now_func
        self._last_flush_at = 0.0
        self._last_entry_count = 0

    def should_flush(self, *, force: bool = False, entry_count: int = 0) -> bool:
        if force:
            return True
        normalized_entry_count = max(0, int(entry_count or 0))
        if normalized_entry_count <= self._last_entry_count:
            return False
        if self._last_entry_count <= 0:
            return True
        if normalized_entry_count - self._last_entry_count >= self.min_entry_delta:
            return True
        return (self._now_func() - self._last_flush_at) >= self.min_interval_seconds

    def mark_flushed(self, entry_count: int) -> None:
        self._last_entry_count = max(0, int(entry_count or 0))
        self._last_flush_at = self._now_func()


class IoMetrics:
    def __init__(self):
        self.file_reads = 0
        self.file_read_bytes = 0
        self.file_writes = 0
        self.file_write_bytes = 0
        self.exiftool_calls = 0
        self.photos_api_calls = 0
        self.cache_hits: Dict[str, int] = {}
        self.cache_misses: Dict[str, int] = {}

    def increment_cache_hit(self, key: str) -> None:
        normalized = str(key or "").strip()
        if normalized:
            self.cache_hits[normalized] = self.cache_hits.get(normalized, 0) + 1

    def increment_cache_miss(self, key: str) -> None:
        normalized = str(key or "").strip()
        if normalized:
            self.cache_misses[normalized] = self.cache_misses.get(normalized, 0) + 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "file_reads": self.file_reads,
            "file_read_bytes": self.file_read_bytes,
            "file_writes": self.file_writes,
            "file_write_bytes": self.file_write_bytes,
            "exiftool_calls": self.exiftool_calls,
            "photos_api_calls": self.photos_api_calls,
            "cache_hits": dict(self.cache_hits),
            "cache_misses": dict(self.cache_misses),
        }


class ScanContext:
    def __init__(self, config: Dict[str, Any]):
        self.config = dict(config) if isinstance(config, dict) else {}
        self.sidecar_cache = SidecarLookupCache()
        self.photos_lookup_cache = PhotosLookupCache()
        self.metadata_context_cache: Dict[str, Dict[str, Any]] = {}
        self.name_mapping_index: Dict[str, Dict[str, Any]] = {}
        debug_config = self.config.get("debug") if isinstance(self.config.get("debug"), dict) else {}
        self.io_metrics: Optional[IoMetrics] = IoMetrics() if bool(debug_config.get("IO_METRICS_ENABLED", False)) else None


class ImgDataService:
    """Orchestrates business use-cases across Photos and file handlers."""
    SESSION_KEEPALIVE_INTERVAL_SECONDS = 180
    FACE_MATCH_KEEPALIVE_INTERVAL_SECONDS = SESSION_KEEPALIVE_INTERVAL_SECONDS
    FACE_MATCH_FINDINGS_FLUSH_INTERVAL_SECONDS = 60
    FACE_MATCH_FINDINGS_FLUSH_ENTRY_INTERVAL = 25
    CHECKS_FINDINGS_FLUSH_INTERVAL_SECONDS = 60
    CHECKS_FINDINGS_FLUSH_ENTRY_INTERVAL = 25
    CHECKS_AUTO_APPLY_MAX_ACTIONS_PER_CALL = 25
    STOPPING_PROGRESS_STALE_SECONDS = 120

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.config = ConfigService()
        self.exiftool = ExifToolService(self.config)
        self.exiftool_handler = ExifToolHandler(self.config)
        self.core = CoreHandler(session_manager)
        self.photos = PhotosHandler(session_manager, self.config)
        self.photos_lookup_cache = PhotosLookupCache()
        self.files = FileHandler(self.config)
        self.image_decoder = ImageDecodeService(self.config)
        self.metadata_parser = MetadataParser()
        self.name_mappings = NameMappingService()
        self.face_suppressions = FaceSuppressionRepository(self.name_mappings._database)
        self.face_matcher = FaceMatcher()
        self.file_analysis = FileAnalysisService()
        self.face_match_findings = FaceMatchFindingsService(self.name_mappings._database)
        self._debug_logger: Optional[Callable[..., None]] = None
        self._checks_start_lock = Lock()
        self.write_locks = WriteLockService(self._buildWriteConflictError)
        self.face_match_mutations = FaceMatchMutationService(self, self._debugLog)
        self.status_builder = StatusPayloadBuilder()
        self.runtime_operations = RuntimeOperationService(
            timestamp_func=self._timestamp_now,
            status_builder=self.status_builder,
            stale_stopping_seconds=self.STOPPING_PROGRESS_STALE_SECONDS,
        )
        self.runtime_state = RuntimeStateService(
            runtime_operations=self.runtime_operations,
            status_builder=self.status_builder,
            persistence=self.file_analysis,
        )
        self.checks_workflow = ChecksWorkflowService(self, ImgDataOperationError)
        self.face_match_workflow = FaceMatchWorkflowService(self)
        self.face_frame_standardization = FaceFrameStandardizationService(self)
        self.face_recognition = FaceRecognitionService(self)
    @staticmethod
    def _buildWriteConflictError(
        lock_key: str,
        phase: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ImgDataOperationError:
        return ImgDataOperationError(
            "write_conflict",
            {
                "code": "write_conflict",
                "message_key": "write_conflict",
                "phase": phase,
                "lock_key": lock_key,
                "retryable": True,
                **(context or {}),
            },
        )

    def _writeOperationLock(
        self,
        key: str,
        *,
        phase: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        return self.write_locks.acquire(key, phase=phase, context=context)

    def _checkFindingsLock(self, finding_type: str):
        lock_factory = getattr(self.file_analysis, "lockCheckFindings", None)
        lock = lock_factory(finding_type) if callable(lock_factory) else None
        return lock if hasattr(lock, "__enter__") and hasattr(lock, "__exit__") else nullcontext()

    @staticmethod
    def _metadataWriteLockKey(path: Any) -> str:
        return f"metadata:{str(path or '').strip()}"

    @staticmethod
    def _photosFaceWriteLockKey(face_id: Any) -> str:
        return f"photos:face:{str(face_id or '').strip()}"

    @staticmethod
    def _photosItemWriteLockKey(item_id: Any) -> str:
        return f"photos:item:{str(item_id or '').strip()}"

    @staticmethod
    def _findPhotosFaceById(faces: List[Dict[str, Any]], face_id: Any) -> Optional[Dict[str, Any]]:
        try:
            expected_face_id = int(face_id)
        except (TypeError, ValueError):
            return None
        for face in faces if isinstance(faces, list) else []:
            if not isinstance(face, dict):
                continue
            try:
                current_face_id = int(face.get("face_id"))
            except (TypeError, ValueError):
                continue
            if current_face_id == expected_face_id:
                return face
        return None

    def _raisePhotosFaceChanged(
        self,
        *,
        phase: str,
        face_id: Any,
        item_id: Any = None,
        person_id: Any = None,
        image_path: str = "",
        reason: str = "photos_face_changed_during_operation",
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
    ) -> None:
        details: Dict[str, Any] = {
            "code": "photos_face_changed_during_operation",
            "message_key": "photos_face_changed_during_operation",
            "reason": reason,
            "phase": phase,
            "face_id": face_id,
            "retryable": False,
        }
        if item_id is not None:
            details["item_id"] = item_id
        if person_id is not None:
            details["person_id"] = person_id
        if image_path:
            details["image_path"] = str(image_path or "").strip()
        if before is not None:
            details["before"] = before
        if after is not None:
            details["after"] = after
        raise ImgDataOperationError("photos_face_changed_during_operation", details)

    def _readPhotosFaceOnItem(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        item_id: int,
        face_id: int,
    ) -> Optional[Dict[str, Any]]:
        faces = self.photos.list_faceFotoTeamItems(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            id_item=int(item_id),
        )
        return self._findPhotosFaceById(faces, face_id)

    def _validatePhotosFaceOnItem(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        item_id: int,
        face_id: int,
        phase: str,
        image_path: str = "",
        expected_person_id: Optional[int] = None,
        before: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = self._readPhotosFaceOnItem(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            item_id=int(item_id),
            face_id=int(face_id),
        )
        if current is None:
            self._raisePhotosFaceChanged(
                phase=phase,
                face_id=face_id,
                item_id=item_id,
                person_id=expected_person_id,
                image_path=image_path,
                reason="photos_face_missing",
                before=before,
                after=None,
            )
        if expected_person_id is not None:
            try:
                current_person_id = int(current.get("person_id"))
            except (TypeError, ValueError):
                current_person_id = None
            if current_person_id != int(expected_person_id):
                self._raisePhotosFaceChanged(
                    phase=phase,
                    face_id=face_id,
                    item_id=item_id,
                    person_id=expected_person_id,
                    image_path=image_path,
                    reason="photos_face_person_mismatch",
                    before=before,
                    after=current,
                )
        return current

    @staticmethod
    def _fileChangeSnapshot(path: Any) -> Optional[Dict[str, Any]]:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return None
        try:
            stat = Path(normalized_path).stat()
        except OSError:
            return None
        return {
            "path": normalized_path,
            "mtime_ns": int(stat.st_mtime_ns),
            "size": int(stat.st_size),
        }

    @staticmethod
    def _fileSnapshotChanged(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> bool:
        if not before or not after:
            return False
        return before.get("mtime_ns") != after.get("mtime_ns") or before.get("size") != after.get("size")

    @staticmethod
    def _fileChangedSince(path: Any, cutoff_mtime_ns: int) -> bool:
        normalized_path = str(path or "").strip()
        if not normalized_path or cutoff_mtime_ns <= 0:
            return False
        try:
            return int(Path(normalized_path).stat().st_mtime_ns) >= int(cutoff_mtime_ns)
        except OSError:
            return False

    def _raiseIfFileChangedDuringOperation(
        self,
        *,
        phase: str,
        image_path: str,
        target_path: str,
        image_snapshot: Optional[Dict[str, Any]],
        target_snapshot: Optional[Dict[str, Any]],
    ) -> None:
        current_image_snapshot = self._fileChangeSnapshot(image_path)
        current_target_snapshot = self._fileChangeSnapshot(target_path)
        changed_path = ""
        before_snapshot = None
        after_snapshot = None
        if self._fileSnapshotChanged(image_snapshot, current_image_snapshot):
            changed_path = str(image_path or "").strip()
            before_snapshot = image_snapshot
            after_snapshot = current_image_snapshot
        elif str(target_path or "").strip() != str(image_path or "").strip() and self._fileSnapshotChanged(target_snapshot, current_target_snapshot):
            changed_path = str(target_path or "").strip()
            before_snapshot = target_snapshot
            after_snapshot = current_target_snapshot
        if not changed_path:
            return
        raise ImgDataOperationError(
            "image_changed_during_operation",
            {
                "code": "image_changed_during_operation",
                "message_key": "image_changed_during_operation",
                "phase": phase,
                "image_path": str(image_path or "").strip(),
                "target_path": str(target_path or "").strip(),
                "changed_path": changed_path,
                "retryable": False,
                "before": before_snapshot,
                "after": after_snapshot,
            },
        )


    @staticmethod
    def _utcNowIso() -> str:
        return RuntimeOperationService.utc_now_iso()

    @staticmethod
    def _parseProgressTimestamp(value: Any) -> Optional[datetime]:
        return RuntimeOperationService.parse_timestamp(value)

    def _isStaleStoppingProgress(self, progress: Any) -> bool:
        return self.runtime_operations.is_stale_stopping_progress(progress)

    def _checksProgressKeys(self, user_key: str = "", check_type: str = "") -> List[str]:
        normalized_user = str(user_key or "").strip()
        normalized_type = str(check_type or "").strip().lower()
        keys: List[str] = []
        if normalized_user and normalized_type:
            keys.append(f"{normalized_user}:{normalized_type}")
        if normalized_user:
            keys.append(normalized_user)
        if normalized_type:
            keys.append(normalized_type)
        return keys

    def _setActiveChecksContext(self, *, user_key: str = "", check_type: str = "", save_only: bool = False) -> None:
        self.runtime_state.replace_values("checks_active_context", {
            "user_key": str(user_key or "").strip(),
            "check_type": str(check_type or "").strip().lower(),
            "save_only": bool(save_only),
            "last_progress_at": self._utcNowIso(),
        })

    def _clearChecksStopRequest(self, *, user_key: str = "", check_type: str = "") -> None:
        normalized_user = str(user_key or "").strip()
        normalized_type = self._normalizeChecksType(check_type) if str(check_type or "").strip() else ""
        progress_state_keys: List[str] = []
        if normalized_user and normalized_type:
            progress_state_keys.append(self._checksStateKey(normalized_user, normalized_type))
        elif normalized_user:
            progress_state_keys.extend(
                self._checksStateKey(normalized_user, candidate_type)
                for candidate_type in self._checksTypeOptions()
            )
        with self.runtime_state.lock("checks_progress"):
            for key in self._checksProgressKeys(user_key, check_type):
                self.runtime_state.values("checks_stop_requests").pop(key, None)
            self.runtime_state.values("checks_stop_requests").pop("*", None)
            for state_key in progress_state_keys:
                progress = dict(self.runtime_state.memory("checks_progress").get(state_key, {}))
                if not progress:
                    progress = self.runtime_state.read_persisted("checks_progress", state_key)
                    progress = dict(progress) if isinstance(progress, dict) else {}
                if not isinstance(progress, dict) or not progress.get("stop_requested"):
                    continue
                progress["stop_requested"] = False
                progress.pop("stop_requested_at", None)
                progress["last_updated_at"] = self._timestamp_now()
                self.runtime_state.memory("checks_progress")[state_key] = progress
                self.runtime_state.persist("checks_progress", state_key, progress)

    def requestStopChecks(self, user_key: str = "", check_type: str = "") -> Dict[str, Any]:
        normalized_user = str(user_key or "").strip()
        normalized_type = str(check_type or "").strip().lower()
        now = self._utcNowIso()
        with self.runtime_state.lock("checks_progress"):
            keys = self._checksProgressKeys(normalized_user, normalized_type)
            if not keys:
                keys = ["*"]
            for key in keys:
                self.runtime_state.values("checks_stop_requests")[key] = now

            updated_progress = {}
            for key, progress in list(self.runtime_state.memory("checks_progress").items()):
                if not isinstance(progress, dict):
                    continue
                progress_type = str(progress.get("check_type") or "").strip().lower()
                if normalized_type and progress_type and progress_type != normalized_type:
                    continue
                progress["stop_requested"] = True
                progress["stop_requested_at"] = now
                progress["last_progress_at"] = now
                updated_progress[key] = dict(progress)
            return {
                "stop_requested": True,
                "check_type": normalized_type,
                "updated_progress": updated_progress,
            }

    def _isChecksStopRequested(self, *, user_key: str = "", check_type: str = "") -> bool:
        with self.runtime_state.lock("checks_progress"):
            stop_requests = self.runtime_state.values("checks_stop_requests")
            if stop_requests.get("*"):
                return True
            for key in self._checksProgressKeys(user_key, check_type):
                if stop_requests.get(key):
                    return True
            context = self.runtime_state.values("checks_active_context")
            context_user = str(context.get("user_key") or "").strip() if isinstance(context, dict) else ""
            context_type = str(context.get("check_type") or "").strip().lower() if isinstance(context, dict) else ""
            for key in self._checksProgressKeys(context_user, context_type):
                if stop_requests.get(key):
                    return True
            return False

    def _raiseIfChecksStopRequested(self) -> None:
        context = self.runtime_state.values("checks_active_context")
        user_key = str(context.get("user_key") or "").strip() if isinstance(context, dict) else ""
        check_type = str(context.get("check_type") or "").strip().lower() if isinstance(context, dict) else ""
        if not self._isChecksStopRequested(user_key=user_key, check_type=check_type):
            return
        raise ImgDataOperationError(
            "checks_stop_requested",
            {
                "code": "checks_stop_requested",
                "message_key": "checks_stop_requested",
                "check_type": check_type,
                "retryable": False,
            },
        )

    def _updateChecksProgressHeartbeat(self, *, current_path: str = "", finding_delta: int = 0, flush: bool = False) -> None:
        context = self.runtime_state.values("checks_active_context")
        if not isinstance(context, dict):
            return
        user_key = str(context.get("user_key") or "").strip()
        check_type = str(context.get("check_type") or "").strip().lower()
        if not user_key and not check_type:
            return
        now = self._utcNowIso()
        normalized_path = str(current_path or "").strip()
        with self.runtime_state.lock("checks_progress"):
            for key in self._checksProgressKeys(user_key, check_type):
                progress = self.runtime_state.memory("checks_progress").get(key)
                if not isinstance(progress, dict):
                    continue
                progress["last_progress_at"] = now
                progress["heartbeat_at"] = now
                progress["running"] = True
                progress["finished"] = False
                if normalized_path:
                    progress["current_path"] = normalized_path
                if finding_delta:
                    progress["findings_count"] = max(0, int(progress.get("findings_count") or 0) + int(finding_delta))
                    progress["last_finding_at"] = now
                if flush:
                    progress["last_flush_at"] = now
                    progress["last_flush_count"] = int(progress.get("findings_count") or 0)
                self.runtime_state.persist("checks_progress", key, dict(progress))

    def update_session_context(
        self,
        *,
        user_key: str,
        base_url: str,
        kk_message: Optional[str] = None,
        synotoken: Optional[str] = None,
        account: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        self.session_manager.update_context(
            user_key,
            base_url=base_url,
            kk_message=kk_message,
            synotoken=synotoken,
            account=account,
            cookies=cookies,
        )

    def status_persons(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, int]:
        status = self.photos.person_status(user_key=user_key, cookies=cookies, base_url=base_url)
        status["mappings"] = len(self.name_mappings.readNameMappings())
        return status

    def status_system(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, str]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        return {"shared_folder": shared_folder or ""}

    def exiftool_status(self) -> Dict[str, Any]:
        return self.exiftool.getStatus()

    def exiftool_extensions(self) -> Dict[str, Any]:
        return self.exiftool.getSupportedReadableExtensions()

    def install_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.installLatest()

    def remove_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.removeInstalled()

    def _readImageMetadata(
        self,
        image_path: str,
        *,
        include_unnamed_acd: bool = False,
        metadata_context_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        scan_context: Optional[ScanContext] = None,
        allow_exiftool_context_fallback: bool = True,
        allow_exiftool_sidecar_read: bool = True,
        jpeg_context_override: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> MetadataPayload:
        self._raiseIfChecksStopRequested()
        self._updateChecksProgressHeartbeat(current_path=image_path)
        config = scan_context.config if scan_context is not None else self.config.readMergedConfig()
        if metadata_context_cache is None and scan_context is not None:
            metadata_context_cache = scan_context.metadata_context_cache
        io_metrics = scan_context.io_metrics if scan_context is not None else None
        files_config = dict(config.get("files") if isinstance(config.get("files"), dict) else {})
        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))
        use_exiftool_for_sidecars = bool(
            files_config.get("USE_EXIFTOOL_FOR_SIDECARS", files_config.get("USE_EXIFTOOL_FOR_SIDECARDS", False))
        )
        sidecar_exiftool_fallback_enabled = bool(files_config.get("SIDECAR_EXIFTOOL_FALLBACK_ENABLED", False))
        sidecar_read_mode = str(files_config.get("SIDECAR_READ_MODE", "") or "").strip().lower()
        if sidecar_read_mode not in {"direct_first", "direct_only", "exiftool_first", "exiftool_only"}:
            sidecar_read_mode = "direct_first" if (use_exiftool_for_sidecars or sidecar_exiftool_fallback_enabled) else "direct_only"
        if not allow_exiftool_sidecar_read:
            sidecar_read_mode = "direct_only"
        prefer_exiftool_for_context = bool(files_config.get("PREFER_EXIFTOOL_FOR_CONTEXT", False))
        exiftool_available = use_exiftool and self.exiftool_handler.isAvailable()

        def report_progress(stage: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(stage)
            except Exception:
                pass

        sidecar_cache = scan_context.sidecar_cache if scan_context is not None else None
        report_progress("sidecar_lookup")
        xmp_path = self.files.findXmpForImage(image_path, lookup_cache=sidecar_cache)
        xmp_content = None
        xmp_source = ""

        exiftool_context: Optional[Dict[str, Any]] = None

        def get_exiftool_metadata_context(*, include_xmp: bool = True) -> Optional[Dict[str, Any]]:
            nonlocal exiftool_context
            self._raiseIfChecksStopRequested()
            checks_context = self.runtime_state.values("checks_active_context")
            checks_user_key = str(checks_context.get("user_key") or "").strip() if isinstance(checks_context, dict) else ""
            checks_type = str(checks_context.get("check_type") or "").strip().lower() if isinstance(checks_context, dict) else ""
            if checks_user_key and checks_type and self._shouldStopChecks(checks_user_key, checks_type):
                raise RuntimeError("checks_stop_requested")
            if not exiftool_available:
                return None
            if exiftool_context is not None:
                return exiftool_context
            if metadata_context_cache and image_path in metadata_context_cache:
                if io_metrics:
                    io_metrics.increment_cache_hit("metadata_context")
                exiftool_context = metadata_context_cache[image_path]
                return exiftool_context
            if io_metrics:
                io_metrics.increment_cache_miss("metadata_context")
                io_metrics.exiftool_calls += 1
            exiftool_context = self.exiftool_handler.readMetadataContext(image_path, include_xmp=include_xmp)
            return exiftool_context


        if xmp_path:
            report_progress("sidecar_read")
            if sidecar_read_mode == "exiftool_only":
                if exiftool_available:
                    if io_metrics:
                        io_metrics.exiftool_calls += 1
                    xmp_content = self.exiftool_handler.loadXmpFile(xmp_path)
                    xmp_source = "xmp_file" if xmp_content else ""
            elif sidecar_read_mode == "exiftool_first":
                if exiftool_available:
                    if io_metrics:
                        io_metrics.exiftool_calls += 1
                    xmp_content = self.exiftool_handler.loadXmpFile(xmp_path)
                    xmp_source = "xmp_file" if xmp_content else ""
                if not xmp_content:
                    if io_metrics:
                        io_metrics.file_reads += 1
                    xmp_content = self.files.loadXmpFromFile(xmp_path)
                    if xmp_content:
                        xmp_source = "xmp_file"
            else:
                if io_metrics:
                    io_metrics.file_reads += 1
                xmp_content = self.files.loadXmpFromFile(xmp_path)
                if xmp_content:
                    xmp_source = "xmp_file"
                elif sidecar_read_mode == "direct_first" and exiftool_available:
                    if io_metrics:
                        io_metrics.exiftool_calls += 1
                    xmp_content = self.exiftool_handler.loadXmpFile(xmp_path)
                    xmp_source = "xmp_file" if xmp_content else ""

        jpeg_context: Dict[str, Any] = dict(jpeg_context_override or {})
        if Path(image_path).suffix.lower() in {".jpg", ".jpeg"} and not prefer_exiftool_for_context:
            report_progress("jpeg_context")
            if not jpeg_context and io_metrics:
                io_metrics.file_reads += 1
            if not jpeg_context:
                jpeg_context = self.files.readJpegContext(image_path)
            if not xmp_content and jpeg_context.get("xmp_content"):
                xmp_content = jpeg_context.get("xmp_content")
                xmp_source = jpeg_context.get("xmp_source") or "embedded_xmp_parsed"

        if not xmp_content and exiftool_available:
            # Do not start ExifTool only to prove that embedded XMP is absent.
            # Reuse XMP only if a context was already loaded for another reason.
            if exiftool_context and exiftool_context.get("success") and exiftool_context.get("xmp_content"):
                xmp_content = exiftool_context["xmp_content"]
                xmp_source = "embedded_xmp_exiftool"
            cached_context_handled = False
            if not xmp_content and metadata_context_cache and image_path in metadata_context_cache:
                if io_metrics:
                    io_metrics.increment_cache_hit("metadata_context")
                cached_context = metadata_context_cache[image_path]
                if cached_context.get("success") and cached_context.get("xmp_content"):
                    exiftool_context = cached_context
                    xmp_content = cached_context["xmp_content"]
                    xmp_source = "embedded_xmp_exiftool"
                    cached_context_handled = True
                elif cached_context.get("success"):
                    exiftool_context = cached_context
                    cached_context_handled = True
            if not xmp_content and not cached_context_handled:
                # Do not start ExifTool only to prove that embedded XMP is absent.
                # If a context was already loaded for size/orientation, reuse its XMP.
                if exiftool_context and exiftool_context.get("success") and exiftool_context.get("xmp_content"):
                    xmp_content = exiftool_context["xmp_content"]
                    xmp_source = "embedded_xmp_exiftool"

        if not xmp_content:
            embedded_xmp_full_scan_enabled = bool(files_config.get("EMBEDDED_XMP_FULL_SCAN_ENABLED", False))
            embedded_xmp_full_scan_max_bytes = int(files_config.get("EMBEDDED_XMP_FULL_SCAN_MAX_BYTES", 67108864))
            
            if embedded_xmp_full_scan_enabled:
                report_progress("embedded_xmp_full_scan")
                if io_metrics:
                    io_metrics.file_reads += 1
                xmp_content = self.files.loadXmpFromImageParsed(image_path, max_bytes=embedded_xmp_full_scan_max_bytes)
                xmp_source = "embedded_xmp_parsed" if xmp_content else ""

        image_dimensions = {
            "width": jpeg_context.get("width"),
            "height": jpeg_context.get("height"),
            "unit": "pixel",
        } if jpeg_context else {"width": None, "height": None, "unit": "pixel"}
        image_orientation = jpeg_context.get("orientation") if jpeg_context else None

        if exiftool_available and prefer_exiftool_for_context:
            report_progress("exiftool_context")
            exiftool_context = get_exiftool_metadata_context(include_xmp=not xmp_content)
            if exiftool_context.get("success"):
                if not xmp_content and exiftool_context.get("xmp_content"):
                    xmp_content = exiftool_context["xmp_content"]
                    xmp_source = "embedded_xmp_exiftool"

        if prefer_exiftool_for_context and exiftool_available:
            if exiftool_context and exiftool_context.get("success"):
                image_dimensions = exiftool_context["image_dimensions"]
                image_orientation = exiftool_context["image_orientation"]
            else:
                if io_metrics:
                    io_metrics.exiftool_calls += 2
                image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
                image_orientation = self.exiftool_handler.readImageOrientation(image_path)
            if not image_dimensions.get("width") or not image_dimensions.get("height"):
                if io_metrics:
                    io_metrics.file_reads += 1
                image_dimensions = self.files.readImageDimensions(image_path)
            if image_orientation is None:
                if io_metrics:
                    io_metrics.file_reads += 1
                image_orientation = self.files.readJpegExifOrientation(image_path)
        else:
            image_dimensions = {
                "width": jpeg_context.get("width"),
                "height": jpeg_context.get("height"),
                "unit": "pixel",
            } if jpeg_context else self.files.readImageDimensions(image_path)
            image_orientation = jpeg_context.get("orientation") if jpeg_context else self.files.readJpegExifOrientation(image_path)
            if (
                jpeg_context
                and Path(image_path).suffix.lower() in {".jpg", ".jpeg"}
                and jpeg_context.get("complete") is True
                and image_dimensions.get("width")
                and image_dimensions.get("height")
                and image_orientation is None
            ):
                image_orientation = 1
            missing_dimensions = not image_dimensions.get("width") or not image_dimensions.get("height")
            missing_orientation = image_orientation is None
            if allow_exiftool_context_fallback and exiftool_available and (missing_dimensions or missing_orientation):
                report_progress("exiftool_context_fallback")
                fallback_context = get_exiftool_metadata_context(include_xmp=False)
                if fallback_context and fallback_context.get("success"):
                    # Fallback context is requested with include_xmp=False here.
                    # Do not copy XMP from mocks or unexpected ExifTool output in this path;
                    # this fallback is only for missing size/orientation.
                    fallback_dimensions = fallback_context.get("image_dimensions")
                    if (
                        missing_dimensions
                        and isinstance(fallback_dimensions, dict)
                        and fallback_dimensions.get("width")
                        and fallback_dimensions.get("height")
                    ):
                        image_dimensions = fallback_dimensions
                    if missing_orientation and fallback_context.get("image_orientation") is not None:
                        image_orientation = fallback_context.get("image_orientation")

                # Compatibility fallback: keep the previous single-value ExifTool readers as a
                # last resort if the bundled context call fails or omits a value. This preserves
                # existing behavior for formats/tests where only the old fallback is mocked.
                if missing_dimensions and (not image_dimensions.get("width") or not image_dimensions.get("height")):
                    self._raiseIfChecksStopRequested()
                    if io_metrics:
                        io_metrics.exiftool_calls += 1
                    image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
                if missing_orientation and image_orientation is None:
                    self._raiseIfChecksStopRequested()
                    if io_metrics:
                        io_metrics.exiftool_calls += 1
                    image_orientation = self.exiftool_handler.readImageOrientation(image_path)
        metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        configured_schemas = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}
        default_schemas = ConfigService.defaultConfig()["metadata"]["SCHEMAS"]
        schemas = {
            "ACD": bool(configured_schemas.get("ACD", default_schemas["ACD"])),
            "MICROSOFT": bool(configured_schemas.get("MICROSOFT", default_schemas["MICROSOFT"])),
            "MWG_REGIONS": bool(configured_schemas.get("MWG_REGIONS", default_schemas["MWG_REGIONS"])),
            "IPTC_EXT_REGIONS": bool(configured_schemas.get("IPTC_EXT_REGIONS", default_schemas["IPTC_EXT_REGIONS"])),
        }
        report_progress("metadata_parse")
        return self.metadata_parser.parse(
            image_path=image_path,
            xmp_content=xmp_content,
            xmp_path=xmp_path or "",
            xmp_source=xmp_source,
            image_dimensions=image_dimensions,
            image_orientation=image_orientation,
            use_acd=schemas["ACD"],
            use_microsoft=schemas["MICROSOFT"],
            use_mwg_regions=schemas["MWG_REGIONS"],
            use_iptc_ext_regions=schemas["IPTC_EXT_REGIONS"],
            include_unnamed_acd=include_unnamed_acd,
        )

    def analyzeImageFaceMetadata(self, image_path: str) -> Dict[str, Any]:
        return self.files.analyzeMetadata(self._readImageMetadata(image_path))

    def readAllPersonsFromImage(self, image_path: str) -> List[Dict[str, Any]]:
        return self.files.readAllPersonsFromMetadata(self._readImageMetadata(image_path))

    def _shouldSkipRawFaceCheckWithoutSidecar(
        self,
        image_path: str,
        check_type: str,
        scan_context: Optional[ScanContext] = None,
    ) -> bool:
        normalized_type = str(check_type or "").strip().lower()
        if normalized_type not in {"duplicate_faces", "position_deviations", "name_conflicts"}:
            return False

        if Path(image_path).suffix.lower() not in FileHandler.RAW_PREVIEW_EXTENSIONS:
            return False

        config = scan_context.config if scan_context is not None else self.config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        if bool(files_config.get("PREFER_EXIFTOOL_FOR_CONTEXT", False)):
            return False

        sidecar_cache = scan_context.sidecar_cache if scan_context is not None else None
        return not bool(self.files.findXmpForImage(image_path, lookup_cache=sidecar_cache))

    def _shouldProbeJpegFaceCheckWithoutSidecar(
        self,
        image_path: str,
        check_type: str,
        scan_context: Optional[ScanContext] = None,
    ) -> bool:
        normalized_type = str(check_type or "").strip().lower()
        if normalized_type not in {"duplicate_faces", "position_deviations", "name_conflicts"}:
            return False

        if Path(image_path).suffix.lower() not in {".jpg", ".jpeg"}:
            return False

        if not os.path.isfile(image_path):
            return False

        config = scan_context.config if scan_context is not None else self.config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        if bool(files_config.get("PREFER_EXIFTOOL_FOR_CONTEXT", False)):
            return False

        sidecar_cache = scan_context.sidecar_cache if scan_context is not None else None
        return not bool(self.files.findXmpForImage(image_path, lookup_cache=sidecar_cache))

    @staticmethod
    def _sameMetadataFaceCandidate(
        left: MetadataFace,
        right: MetadataFace,
        *,
        tolerance: float = FACE_COORDINATE_TOLERANCE,
    ) -> bool:
        if str(left.source_format or "").strip().upper() != str(right.source_format or "").strip().upper():
            return False
        if str(left.name or "").strip() != str(right.name or "").strip():
            return False
        return all(
            abs(float(getattr(left, key, 0.0)) - float(getattr(right, key, 0.0))) <= tolerance
            for key in ("x", "y", "w", "h")
        )

    @staticmethod
    def _sameMetadataFaceLocation(
        left: MetadataFace,
        right: MetadataFace,
        *,
        tolerance: float = FACE_COORDINATE_TOLERANCE,
    ) -> bool:
        if str(left.source_format or "").strip().upper() != str(right.source_format or "").strip().upper():
            return False
        return all(
            abs(float(getattr(left, key, 0.0)) - float(getattr(right, key, 0.0))) <= tolerance
            for key in ("x", "y", "w", "h")
        )

    @staticmethod
    def _metadataFaceEditTargetFromData(face_data: Dict[str, Any]) -> MetadataFace:
        target_data = dict(face_data) if isinstance(face_data, dict) else {}
        source_format = str(target_data.get("source_format") or "").strip().upper()
        orientation = target_data.get("orientation")
        if (
            target_data.get("display_normalized")
            and source_format in {"MICROSOFT", "MWG_REGIONS"}
            and orientation not in (None, "", 1, "1")
        ):
            target_data = denormalize_xmp_face(target_data)
        return MetadataFace.from_dict(target_data)

    @staticmethod
    def _findParentMap(root: ET.Element) -> Dict[ET.Element, ET.Element]:
        return {child: parent for parent in root.iter() for child in parent}

    def _acdFaceElements(self, root: ET.Element, *, source: str) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        for description in root.findall(".//rdf:Description", NS_ACD):
            if description.get("{http://ns.acdsee.com/regions/}Type") != "Face":
                continue
            if description.get("{http://ns.acdsee.com/regions/}NameAssignType") == "denied":
                continue
            name = description.get("{http://ns.acdsee.com/regions/}Name")
            if name is None:
                continue
            area = description.find("acdsee-rs:DLYArea", NS_ACD)
            if area is None:
                continue
            try:
                face = MetadataFace.from_center_box(
                    name=str(name or ""),
                    x=float(area.get("{http://ns.acdsee.com/sType/Area#}x")),
                    y=float(area.get("{http://ns.acdsee.com/sType/Area#}y")),
                    w=float(area.get("{http://ns.acdsee.com/sType/Area#}w")),
                    h=float(area.get("{http://ns.acdsee.com/sType/Area#}h")),
                    source=source,
                    source_format="ACD",
                )
            except (TypeError, ValueError):
                continue
            elements.append({"element": description, "face": face})
        return elements

    def _mwgFaceElements(self, root: ET.Element, *, source: str, orientation: Optional[int]) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        candidates = list(root.findall(".//rdf:Description", NS_MWG_REGIONS)) + list(root.findall(".//rdf:li", NS_MWG_REGIONS))
        for description in candidates:
            face_type = description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Type")
            if not face_type:
                type_node = description.find("mwg-rs:Type", NS_MWG_REGIONS)
                face_type = type_node.text.strip() if type_node is not None and type_node.text else ""
            if face_type != "Face":
                continue
            area = description.find("mwg-rs:Area", NS_MWG_REGIONS)
            if area is None:
                continue
            try:
                face = MetadataFace.from_center_box(
                    name=str(
                        description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Name")
                        or (description.findtext("mwg-rs:Name", default="", namespaces=NS_MWG_REGIONS) or "")
                    ),
                    x=MetadataParser._readFloatAttributeOrChild(area, "x", NS_MWG_REGIONS["stArea"]),
                    y=MetadataParser._readFloatAttributeOrChild(area, "y", NS_MWG_REGIONS["stArea"]),
                    w=MetadataParser._readFloatAttributeOrChild(area, "w", NS_MWG_REGIONS["stArea"]),
                    h=MetadataParser._readFloatAttributeOrChild(area, "h", NS_MWG_REGIONS["stArea"]),
                    source=source,
                    source_format="MWG_REGIONS",
                    focus_usage=str(
                        description.get("{http://www.metadataworkinggroup.com/schemas/regions/}FocusUsage")
                        or (description.findtext("mwg-rs:FocusUsage", default="", namespaces=NS_MWG_REGIONS) or "")
                    ),
                    orientation=orientation,
                )
            except (TypeError, ValueError):
                continue
            if orientation not in (None, 1):
                face = MetadataFace.from_dict(face.to_dict())
            elements.append({"element": description, "face": face})
        return elements

    def _microsoftFaceElements(self, root: ET.Element, *, source: str) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        for description in root.iter():
            if description.tag not in {
                "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description",
                "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li",
            }:
                continue
            rectangle = ""
            name = ""
            for key, value in description.attrib.items():
                local_name = key.split("}", 1)[-1]
                if local_name == "Rectangle" and value:
                    rectangle = value.strip()
                elif local_name == "PersonDisplayName" and value:
                    name = value.strip()
            if not rectangle or not name:
                for child in list(description):
                    local_name = child.tag.split("}", 1)[-1]
                    text = child.text.strip() if child.text else ""
                    if local_name == "Rectangle" and text and not rectangle:
                        rectangle = text
                    elif local_name == "PersonDisplayName" and text and not name:
                        name = text
            if not rectangle:
                continue
            try:
                x, y, width, height = [float(value.strip()) for value in rectangle.split(",")]
            except (TypeError, ValueError):
                continue
            face = MetadataFace.from_top_left_box(
                name=name,
                left=x,
                top=y,
                w=width,
                h=height,
                source=source,
                source_format="MICROSOFT",
            )
            elements.append({"element": description, "face": face})
        return elements

    def deleteMetadataFace(self, *, image_path: str, face_data: Dict[str, Any]) -> Dict[str, Any]:
        edit_context, warning = self._prepareMetadataFaceEdit(
            image_path=image_path,
            not_found_warning="checks:warning_face_delete_not_found",
        )
        if warning == "checks:warning_exiftool_required":
            return {"deleted": False, "warning": "checks:warning_exiftool_required"}
        if warning:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        target = self._metadataFaceEditTargetFromData(face_data if isinstance(face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()
        root = edit_context["root"]
        parent_map = self._findParentMap(root)

        removed = False
        for candidate in self._metadataFaceEditCandidates(edit_context, source_format):
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            parent = parent_map.get(candidate["element"])
            if parent is None:
                continue
            parent.remove(candidate["element"])
            removed = True
            break

        if not removed:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        write_result = self._writeMetadataEditContext(
            edit_context,
            phase="metadata_face_delete",
            context={},
        )
        return {
            "deleted": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_delete_failed",
            "target_path": edit_context["target_path"],
            "used_sidecar": bool(edit_context["xmp_path"]),
            "details": write_result if not write_result.get("updated") else None,
        }

    @staticmethod
    def _setExistingElementValueByLocalName(element: ET.Element, local_name: str, value: str) -> bool:
        updated = False
        replacement_value = str(value or "").strip()
        for key in list(element.attrib.keys()):
            if key.split("}", 1)[-1] != local_name:
                continue
            element.set(key, replacement_value)
            updated = True
        for child in list(element):
            if child.tag.split("}", 1)[-1] != local_name:
                continue
            child.text = replacement_value
            updated = True
        return updated

    @staticmethod
    def _setMetadataFaceName(element: ET.Element, source_format: str, new_name: str) -> None:
        normalized_format = str(source_format or "").strip().upper()
        replacement_name = str(new_name or "").strip()
        if normalized_format == "ACD":
            if not ImgDataService._setExistingElementValueByLocalName(element, "Name", replacement_name):
                element.set("{http://ns.acdsee.com/regions/}Name", replacement_name)
            return
        if normalized_format == "MICROSOFT":
            if not ImgDataService._setExistingElementValueByLocalName(element, "PersonDisplayName", replacement_name):
                element.append(ET.Element(f"{{{NS_MICROSOFT['MPReg']}}}PersonDisplayName"))
                element[-1].text = replacement_name
            return
        if normalized_format == "MWG_REGIONS":
            if not ImgDataService._setExistingElementValueByLocalName(element, "Name", replacement_name):
                element.set("{http://www.metadataworkinggroup.com/schemas/regions/}Name", replacement_name)

    @staticmethod
    def _formatMetadataFaceCoordinate(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "0"
        formatted = f"{numeric:.{FACE_COORDINATE_DIGITS}f}".rstrip("0").rstrip(".")
        return formatted or "0"

    @staticmethod
    def _setMetadataFacePosition(
        element: ET.Element,
        source_format: str,
        new_face: MetadataFace,
        *,
        target_orientation: Optional[int] = None,
    ) -> bool:
        normalized_format = str(source_format or "").strip().upper()
        write_face = new_face
        if normalized_format in {"MICROSOFT", "MWG_REGIONS"} and target_orientation not in (None, 1):
            oriented_face = dict(new_face.to_dict())
            oriented_face["orientation"] = target_orientation
            write_face = MetadataFace.from_dict(denormalize_xmp_face(oriented_face))
        w = ImgDataService._formatMetadataFaceCoordinate(write_face.w)
        h = ImgDataService._formatMetadataFaceCoordinate(write_face.h)
        x = ImgDataService._formatMetadataFaceCoordinate(write_face.x)
        y = ImgDataService._formatMetadataFaceCoordinate(write_face.y)

        if normalized_format == "ACD":
            area = element.find("acdsee-rs:DLYArea", NS_ACD)
            if area is None:
                return False
            updated = False
            updated = ImgDataService._setExistingElementValueByLocalName(area, "x", x) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "y", y) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "w", w) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "h", h) or updated
            return updated

        if normalized_format == "MICROSOFT":
            left = ImgDataService._formatMetadataFaceCoordinate(write_face.x - (write_face.w / 2))
            top = ImgDataService._formatMetadataFaceCoordinate(write_face.y - (write_face.h / 2))
            rectangle = ",".join((left, top, w, h))
            if ImgDataService._setExistingElementValueByLocalName(element, "Rectangle", rectangle):
                return True
            element.append(ET.Element(f"{{{NS_MICROSOFT['MPReg']}}}Rectangle"))
            element[-1].text = rectangle
            return True

        if normalized_format == "MWG_REGIONS":
            area = element.find("mwg-rs:Area", NS_MWG_REGIONS)
            if area is None:
                return False
            updated = False
            updated = ImgDataService._setExistingElementValueByLocalName(area, "x", x) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "y", y) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "w", w) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "h", h) or updated
            return updated

        return False

    def replaceMetadataFaceName(self, *, image_path: str, face_data: Dict[str, Any], new_name: str) -> Dict[str, Any]:
        edit_context, warning = self._prepareMetadataFaceEdit(
            image_path=image_path,
            not_found_warning="checks:warning_face_replace_not_found",
        )
        if warning == "checks:warning_exiftool_required":
            return {"updated": False, "warning": "checks:warning_exiftool_required"}

        replacement_name = str(new_name or "").strip()
        if not replacement_name:
            return {"updated": False, "warning": "checks:warning_face_replace_failed"}
        if warning:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        target = self._metadataFaceEditTargetFromData(face_data if isinstance(face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()

        updated = False
        already_updated = False
        candidates = self._metadataFaceEditCandidates(edit_context, source_format)
        for candidate in candidates:
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            self._setMetadataFaceName(candidate["element"], source_format, replacement_name)
            updated = True
            break
        if not updated:
            for candidate in candidates:
                candidate_face = candidate["face"]
                if (
                    self._sameMetadataFaceLocation(candidate_face, target)
                    and str(candidate_face.name or "").strip() == replacement_name
                ):
                    already_updated = True
                    break

        if not updated and not already_updated:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        if already_updated:
            return {
                "updated": True,
                "warning": "",
                "target_path": edit_context["target_path"],
                "used_sidecar": bool(edit_context["xmp_path"]),
                "already_updated": True,
            }

        write_result = self._writeMetadataEditContext(
            edit_context,
            phase="metadata_face_name_replace",
            context={"new_name": replacement_name},
        )
        return {
            "updated": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_replace_failed",
            "target_path": edit_context["target_path"],
            "used_sidecar": bool(edit_context["xmp_path"]),
            "details": write_result if not write_result.get("updated") else None,
        }

    def _prepareMetadataFaceEdit(
        self,
        *,
        image_path: str,
        not_found_warning: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.exiftool_handler.isAvailable():
            return None, "checks:warning_exiftool_required"

        image_snapshot = self._fileChangeSnapshot(image_path)
        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return None, not_found_warning

        xmp_path = payload.xmp_path or ""
        target_path = xmp_path or image_path
        target_snapshot = self._fileChangeSnapshot(target_path)
        xmp_content = self._loadMetadataEditXmp(image_path=image_path, xmp_path=xmp_path)
        if not xmp_content:
            return None, not_found_warning

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return None, not_found_warning

        return {
            "image_path": image_path,
            "image_snapshot": image_snapshot,
            "payload": payload,
            "xmp_path": xmp_path,
            "target_path": target_path,
            "target_snapshot": target_snapshot,
            "xmp_content": xmp_content,
            "root": root,
            "orientation": MetadataParser._extractXmpTiffOrientation(xmp_content),
        }, ""

    def _loadMetadataEditXmp(self, *, image_path: str, xmp_path: str = "") -> Optional[str]:
        if xmp_path:
            xmp_content = self.files.loadXmpFromFile(xmp_path)
            if xmp_content:
                return xmp_content
            return self.exiftool_handler.loadXmpFile(xmp_path)

        if Path(image_path).suffix.lower() in {".jpg", ".jpeg"}:
            xmp_content = self.files.loadXmpFromImageParsed(image_path)
            if xmp_content:
                return xmp_content

        return self.exiftool_handler.loadEmbeddedXmp(image_path)

    def _metadataFaceEditCandidates(
        self,
        edit_context: Dict[str, Any],
        source_format: str,
        *,
        source: str = "metadata",
    ) -> List[Dict[str, Any]]:
        normalized_format = str(source_format or "").strip().upper()
        root = edit_context["root"]
        if normalized_format == "ACD":
            return self._acdFaceElements(root, source=source)
        if normalized_format == "MICROSOFT":
            return self._microsoftFaceElements(root, source=source)
        if normalized_format == "MWG_REGIONS":
            return self._mwgFaceElements(root, source=source, orientation=edit_context.get("orientation"))
        return []

    def _writeMetadataEditContext(
        self,
        edit_context: Dict[str, Any],
        *,
        phase: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        image_path = edit_context["image_path"]
        target_path = edit_context["target_path"]
        write_context = {
            "image_path": image_path,
            "target_path": target_path,
            **(context or {}),
        }
        with self._writeOperationLock(
            self._metadataWriteLockKey(target_path),
            phase=phase,
            context=write_context,
        ):
            self._raiseIfFileChangedDuringOperation(
                phase=phase,
                image_path=image_path,
                target_path=target_path,
                image_snapshot=edit_context.get("image_snapshot"),
                target_snapshot=edit_context.get("target_snapshot"),
            )
            return self.exiftool_handler.writeXmpDetailed(
                target_path,
                ET.tostring(edit_context["root"], encoding="unicode"),
            )

    @staticmethod
    def _normalizedNameMappingTable(mappings: List[Dict[str, Any]]) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for item in mappings:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or "").strip()
            target_name = str(item.get("target_name") or "").strip()
            if not source_name or not target_name:
                continue
            source_key = NameMappingService._normalize_name_value(source_name)
            if not source_key:
                continue
            lookup[source_key] = target_name
        return lookup

    def normalizeMetadataFaceNamesFromMappings(
        self,
        *,
        image_path: str,
        target_formats: List[str],
        mapping_lookup: Dict[str, str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        selected_formats = {
            str(fmt or "").strip().upper()
            for fmt in list(target_formats or [])
            if str(fmt or "").strip()
        }
        selected_formats &= {"ACD", "MICROSOFT", "MWG_REGIONS"}
        if not selected_formats:
            return {"updated": False, "updated_faces": 0, "formats": {}}
        if not self.exiftool_handler.isAvailable():
            return {
                "updated": False,
                "updated_faces": 0,
                "formats": {},
                "warning": "checks:warning_exiftool_required",
            }

        image_snapshot = self._fileChangeSnapshot(image_path)
        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        xmp_path = payload.xmp_path or ""
        target_path = xmp_path or image_path
        target_snapshot = self._fileChangeSnapshot(target_path)
        xmp_content = self._loadMetadataEditXmp(image_path=image_path, xmp_path=xmp_path)
        if not xmp_content:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        orientation = MetadataParser._extractXmpTiffOrientation(xmp_content)
        candidates: List[Dict[str, Any]] = []
        if "ACD" in selected_formats:
            candidates.extend(self._acdFaceElements(root, source="cleanup"))
        if "MICROSOFT" in selected_formats:
            candidates.extend(self._microsoftFaceElements(root, source="cleanup"))
        if "MWG_REGIONS" in selected_formats:
            candidates.extend(self._mwgFaceElements(root, source="cleanup", orientation=orientation))

        updated_faces = 0
        updated_formats: Dict[str, int] = {}
        for candidate in candidates:
            if callable(should_stop) and should_stop():
                return {"updated": False, "updated_faces": 0, "formats": {}, "stopped": True}
            face = candidate.get("face")
            element = candidate.get("element")
            if not isinstance(face, MetadataFace) or not isinstance(element, ET.Element):
                continue
            current_name = str(face.name or "").strip()
            if not current_name:
                continue
            source_key = NameMappingService._normalize_name_value(current_name)
            target_name = str(mapping_lookup.get(source_key) or "").strip()
            if not target_name:
                continue
            if NameMappingService._normalize_name_value(target_name) == source_key:
                continue
            source_format = str(face.source_format or "").strip().upper()
            self._setMetadataFaceName(element, source_format, target_name)
            updated_faces += 1
            updated_formats[source_format] = updated_formats.get(source_format, 0) + 1

        if updated_faces == 0:
            return {"updated": False, "updated_faces": 0, "formats": {}}
        if callable(should_stop) and should_stop():
            return {"updated": False, "updated_faces": 0, "formats": {}, "stopped": True}

        with self._writeOperationLock(
            self._metadataWriteLockKey(target_path),
            phase="metadata_name_normalize",
            context={"image_path": image_path, "target_path": target_path},
        ):
            self._raiseIfFileChangedDuringOperation(
                phase="metadata_name_normalize",
                image_path=image_path,
                target_path=target_path,
                image_snapshot=image_snapshot,
                target_snapshot=target_snapshot,
            )
            write_result = self.exiftool_handler.writeXmpDetailed(target_path, ET.tostring(root, encoding="unicode"))
        return {
            "updated": bool(write_result.get("updated")),
            "updated_faces": updated_faces if write_result.get("updated") else 0,
            "formats": updated_formats if write_result.get("updated") else {},
            "target_path": target_path,
            "used_sidecar": bool(xmp_path),
            "details": write_result if not write_result.get("updated") else None,
        }

    def replaceMetadataFacePosition(
        self,
        *,
        image_path: str,
        face_data: Dict[str, Any],
        source_face_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        edit_context, warning = self._prepareMetadataFaceEdit(
            image_path=image_path,
            not_found_warning="checks:warning_face_position_replace_not_found",
        )
        if warning == "checks:warning_exiftool_required":
            return {"updated": False, "warning": "checks:warning_exiftool_required"}
        if warning:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        target = self._metadataFaceEditTargetFromData(face_data if isinstance(face_data, dict) else {})
        source_face = MetadataFace.from_dict(source_face_data if isinstance(source_face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()
        source_face_format = str(source_face.source_format or "").strip().upper()
        if source_format and source_face_format and source_format == source_face_format:
            return {"updated": False, "warning": "checks:warning_face_position_same_source"}

        updated = False
        for candidate in self._metadataFaceEditCandidates(edit_context, source_format):
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            updated = self._setMetadataFacePosition(
                candidate["element"],
                source_format,
                source_face,
                target_orientation=target.orientation,
            )
            break

        if not updated:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        write_result = self._writeMetadataEditContext(
            edit_context,
            phase="metadata_face_position_replace",
            context={},
        )
        return {
            "updated": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_position_replace_failed",
            "target_path": edit_context["target_path"],
            "used_sidecar": bool(edit_context["xmp_path"]),
            "details": write_result if not write_result.get("updated") else None,
        }

    def replacePhotosFacePosition(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_data: Dict[str, Any],
        source_face_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            face_id = int((face_data or {}).get("face_id"))
        except (TypeError, ValueError):
            return {"updated": False, "warning": "checks:warning_photos_face_id_missing"}
        try:
            item_id = int((face_data or {}).get("item_id"))
        except (TypeError, ValueError):
            item_id = None

        if item_id is None:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                return {"updated": False, "warning": "shared_folder_not_found"}
            item = self.photos.findFotoTeamItemByPath(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
                additional=["thumbnail"],
                lookup_cache=self.photos_lookup_cache,
            )
            try:
                item_id = int(item.get("id"))
            except (AttributeError, TypeError, ValueError):
                return {"updated": False, "warning": "photos_item_not_found_for_image"}

        person_id = (face_data or {}).get("person_id")
        try:
            person_id_int = int(person_id)
        except (TypeError, ValueError):
            person_id_int = None
        person_name = str((face_data or {}).get("name") or "").strip()

        with self._writeOperationLock(
            self._photosItemWriteLockKey(item_id),
            phase="photos_face_position_replace",
            context={
                "image_path": str(image_path or "").strip(),
                "item_id": int(item_id),
                "face_id": int(face_id),
                "person_id": person_id_int,
                "person_name": person_name,
            },
        ):
            before_faces = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=int(item_id),
            )
            before_face = next(
                (
                    face for face in before_faces
                    if isinstance(face, dict) and str(face.get("face_id")) == str(face_id)
                ),
                None,
            )
            if before_face is None:
                return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

            face_id_temp = f"{item_id}-{int(monotonic() * 1000)}"
            add_result = self.photos.addFaceToItem(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=int(item_id),
                face_bbox=self._metadataFaceToPhotosBoundingBox(source_face_data),
                face_id_temp=face_id_temp,
                person_id=person_id_int,
                person_name=person_name if person_id_int is None else None,
            )
            created_face_id = self._extractCreatedPhotosFaceId(
                add_result=add_result,
                face_id_temp=face_id_temp,
            )
            if created_face_id is None:
                created_face = self._findCreatedPhotosFaceAfterAdd(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=int(item_id),
                    metadata_face=MetadataFace.from_dict(source_face_data if isinstance(source_face_data, dict) else {}),
                    before_faces=before_faces,
                )
                if isinstance(created_face, dict):
                    try:
                        created_face_id = int(created_face.get("face_id"))
                    except (TypeError, ValueError):
                        created_face_id = None
            if created_face_id is None:
                return {
                    "updated": False,
                    "warning": "photos_face_create_returned_no_id",
                    "add_result": add_result,
                }

            delete_result = self.photos.deleteFace(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=int(face_id),
            )

        return {
            "updated": True,
            "warning": "",
            "operation": "photos_face_position_replace",
            "face_id": int(created_face_id),
            "deleted_face_id": int(face_id),
            "item_id": int(item_id),
            "add_result": add_result,
            "delete_result": delete_result,
        }

    def _setFaceMatchingProgress(self, user_key: str, **updates: Any) -> None:
        with self.runtime_state.lock("face_match_progress"):
            current = dict(self.runtime_state.memory("face_match_progress").get(user_key, {}))
            current.update(updates)
            self._syncFaceMatchProgressCountsFromCursor(current, explicit_fields=set(updates.keys()))
            current = self.runtime_state.stamp_progress(
                current,
                operation="face_match",
            )
            current = self._jsonSafeProgressValue(current)
            self.runtime_state.memory("face_match_progress")[user_key] = current
        self.runtime_state.persist("face_match_progress", user_key, current)

    @staticmethod
    def _jsonSafeProgressValue(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "to_dict"):
            try:
                return ImgDataService._jsonSafeProgressValue(value.to_dict())
            except Exception:
                return str(value)
        if isinstance(value, dict):
            return {str(key): ImgDataService._jsonSafeProgressValue(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [ImgDataService._jsonSafeProgressValue(item) for item in value]
        return str(value)

    @staticmethod
    def _syncFaceMatchProgressCountsFromCursor(
        progress: Dict[str, Any],
        *,
        explicit_fields: Optional[set] = None,
    ) -> None:
        resume_cursor = progress.get("resume_cursor") if isinstance(progress.get("resume_cursor"), dict) else {}
        if not resume_cursor:
            return
        explicit = explicit_fields or set()
        for field in ("findings_count", "transferred_count"):
            if field in explicit or field not in resume_cursor:
                continue
            try:
                progress[field] = int(resume_cursor.get(field))
            except (TypeError, ValueError):
                continue

    def _setFaceMatchingProgressMessage(
        self,
        user_key: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
        }
        payload.update(updates)
        self._setFaceMatchingProgress(user_key, **payload)

    @staticmethod
    def _synologyErrorCode(payload: Any) -> Optional[int]:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        try:
            return int(error.get("code"))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _sessionManagerErrorNeedsLogin(cls, exc: SessionManagerError) -> bool:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        error = str(detail.get("error") or "")
        if error in {"resume_failed", "missing_synotoken_after_resume"}:
            return True
        if error in {"api_failed", "api_failed_after_resume"}:
            return cls._synologyErrorCode(detail.get("response")) in SessionManager.SESSION_RETRY_ERROR_CODES
        return False

    def _setFaceMatchingSessionExceptionProgress(
        self,
        user_key: str,
        exc: Exception,
        *,
        action: str,
        auto: bool,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]],
        skip_face_ids: Optional[List[int]],
        skip_targets: Optional[List[str]],
    ) -> None:
        detail = exc.detail if isinstance(exc, SessionManagerError) and isinstance(exc.detail, dict) else {}
        if isinstance(exc, SessionBootstrapRequired) or (
            isinstance(exc, SessionManagerError) and self._sessionManagerErrorNeedsLogin(exc)
        ):
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_auth_required",
                message=str(exc),
                running=False,
                finished=False,
                paused=True,
                auth_required=True,
                error=str(exc),
                error_details=detail,
                action=action,
                auto=auto,
                save_only=save_only,
                resume_cursor=resume_cursor or self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids or []),
                    skip_targets=list(skip_targets or []),
                    transferred_count=0,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                ),
            )
            return

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:progress_failed",
            message="Face matching failed.",
            running=False,
            finished=True,
            paused=False,
            auth_required=False,
            error=str(exc),
            error_details=detail,
            action=action,
            auto=auto,
            save_only=save_only,
        )

    @staticmethod
    def _faceMatchCandidatePathsCacheKey(user_key: str, action: Any) -> str:
        return FaceMatchWorkflowService.candidate_paths_cache_key(user_key, action)

    def _getFaceMatchCandidatePaths(
        self,
        *,
        user_key: str,
        action: Any,
        shared_folder: str,
        use_cache: bool = True,
    ) -> List[str]:
        return self.face_match_workflow.get_candidate_paths(
            user_key=user_key,
            action=action,
            shared_folder=shared_folder,
            use_cache=use_cache,
        )

    @staticmethod
    def _formatExceptionForProgress(exc: Exception) -> str:
        detail = str(exc).strip()
        return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__

    def _buildFaceMatchResumeCursor(
        self,
        *,
        skip_face_ids: List[int],
        skip_targets: Optional[List[str]] = None,
        transferred_count: int,
        auto: bool,
        save_only: bool,
        recognize_persons: bool = False,
        skip_unknown_persons: bool = False,
        action: str = "search_photo_face_in_file",
        findings_count: int = 0,
        path_index: int = 0,
        persons_read: int = 0,
        images_read: int = 0,
        faces_read: int = 0,
        target_faces_read: int = 0,
        metadata_faces_read: int = 0,
    ) -> Dict[str, Any]:
        return {
            "skip_face_ids": sorted({int(face_id) for face_id in skip_face_ids if isinstance(face_id, int)}),
            "skip_targets": [str(value) for value in (skip_targets or []) if str(value or "").strip()],
            "transferred_count": int(transferred_count),
            "auto": bool(auto),
            "save_only": bool(save_only),
            "recognize_persons": bool(recognize_persons),
            "skip_unknown_persons": bool(skip_unknown_persons),
            "action": str(action or "search_photo_face_in_file"),
            "findings_count": max(0, int(findings_count)),
            "path_index": max(0, int(path_index)),
            "persons_read": max(0, int(persons_read)),
            "images_read": max(0, int(images_read)),
            "faces_read": max(0, int(faces_read)),
            "target_faces_read": max(0, int(target_faces_read)),
            "metadata_faces_read": max(0, int(metadata_faces_read)),
        }

    def recordFaceMatchTransferProgress(
        self,
        user_key: str,
        *,
        skip_face_ids: Optional[List[int]] = None,
        skip_targets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        current = self.getFaceMatchingProgress(user_key)
        if not isinstance(current, dict):
            current = {}
        current_cursor = current.get("resume_cursor") if isinstance(current.get("resume_cursor"), dict) else {}
        current_count = max(
            int(current.get("transferred_count") or 0),
            int(current_cursor.get("transferred_count") or 0),
        )
        next_count = current_count + 1
        merged_face_ids = list(current_cursor.get("skip_face_ids") or [])
        for face_id in skip_face_ids or []:
            try:
                normalized_face_id = int(face_id)
            except (TypeError, ValueError):
                continue
            if normalized_face_id not in merged_face_ids:
                merged_face_ids.append(normalized_face_id)
        merged_targets = [str(value) for value in current_cursor.get("skip_targets") or [] if str(value or "").strip()]
        for target in skip_targets or []:
            normalized_target = str(target or "").strip()
            if normalized_target and normalized_target not in merged_targets:
                merged_targets.append(normalized_target)
        action = str(current_cursor.get("action") or current.get("action") or "search_photo_face_in_file")
        resume_cursor = self._buildFaceMatchResumeCursor(
            skip_face_ids=merged_face_ids,
            skip_targets=merged_targets,
            transferred_count=next_count,
            auto=bool(current_cursor.get("auto", current.get("auto", False))),
            save_only=bool(current_cursor.get("save_only", current.get("save_only", False))),
            recognize_persons=bool(current_cursor.get("recognize_persons", current.get("recognize_persons", False))),
            skip_unknown_persons=bool(current_cursor.get("skip_unknown_persons", current.get("skip_unknown_persons", False))),
            action=action,
            findings_count=int(current_cursor.get("findings_count") or current.get("findings_count") or 0),
            path_index=int(current_cursor.get("path_index") or current.get("images_read") or 0),
            persons_read=int(current_cursor.get("persons_read") or current.get("persons_read") or 0),
            images_read=int(current_cursor.get("images_read") or current.get("images_read") or 0),
            faces_read=int(current_cursor.get("faces_read") or current.get("faces_read") or 0),
            target_faces_read=int(current_cursor.get("target_faces_read") or current.get("target_faces_read") or 0),
            metadata_faces_read=int(current_cursor.get("metadata_faces_read") or current.get("metadata_faces_read") or 0),
        )
        self._setFaceMatchingProgress(
            user_key,
            transferred_count=next_count,
            resume_cursor=resume_cursor,
        )
        return {
            "transferred_count": next_count,
            "resume_cursor": resume_cursor,
        }

    def _normalizeFaceMatchingProgressForDisplay(self, user_key: str, progress: Dict[str, Any]) -> Dict[str, Any]:
        display_progress = dict(progress) if isinstance(progress, dict) else {}

        def normalize_stale_stop_message() -> None:
            message_key = str(display_progress.get("message_key") or display_progress.get("message") or "").strip()
            if message_key != "face_match:progress_stopping":
                return
            display_progress["message_key"] = "face_match:progress_stopped"
            display_progress["message"] = "face_match:progress_stopped"

        if not display_progress:
            return {
                "running": False,
                "finished": False,
                "stop_requested": False,
                "active": False,
                "stale": False,
                "message_key": "",
                "message_params": {},
                "persons_read": 0,
                "persons_total": 0,
                "images_read": 0,
                "faces_read": 0,
                "target_faces_read": 0,
                "metadata_faces_read": 0,
                "transferred_count": 0,
                "findings_count": 0,
                "current_person_id": None,
                "current_image_id": None,
                "current_face_id": None,
                "operation_id": "",
                "action": "",
                "auto": False,
                "save_only": False,
                "resume_available": False,
                "resume_cursor": {},
            }

        resume_cursor = display_progress.get("resume_cursor") if isinstance(display_progress.get("resume_cursor"), dict) else {}
        display_progress["resume_available"] = bool(resume_cursor)
        display_progress["resume_cursor"] = resume_cursor

        if bool(display_progress.get("save_only")) and bool(display_progress.get("finished")):
            findings = self.getFaceMatchFindings()
            entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
            stored_count = len(entries)
            display_progress["findings_count"] = stored_count
            message_params = display_progress.get("message_params")
            if isinstance(message_params, dict) and "count" in message_params:
                message_params = dict(message_params)
                message_params["count"] = stored_count
                display_progress["message_params"] = message_params
            result = display_progress.get("result")
            if isinstance(result, dict) and "findings_count" in result:
                result = dict(result)
                result["findings_count"] = stored_count
                display_progress["result"] = result
            if isinstance(resume_cursor, dict):
                resume_cursor = dict(resume_cursor)
                resume_cursor["findings_count"] = stored_count
                display_progress["resume_cursor"] = resume_cursor

        if display_progress.get("running"):
            display_progress["active"] = True
            display_progress["stale"] = False
            display_progress.setdefault("stop_requested", False)
            return display_progress

        display_progress["running"] = False
        display_progress["active"] = False
        display_progress["stale"] = True
        display_progress["stop_requested"] = False
        normalize_stale_stop_message()
        return display_progress

    @staticmethod
    def _compactFaceMatchingProgressForResponse(progress: Dict[str, Any]) -> Dict[str, Any]:
        compact = dict(progress) if isinstance(progress, dict) else {}
        if compact.get("finished") and compact.get("stale"):
            compact.pop("resume_cursor", None)
            compact["resume_available"] = False
            if compact.get("save_only"):
                compact.pop("result", None)
        return compact

    def getFaceMatchingProgress(self, user_key: str, *, compact_for_response: bool = False) -> Dict[str, Any]:
        normalized_user = str(user_key or "").strip()

        candidate_keys: List[str] = []
        for method_name in (
            "_faceMatchingStateKey",
            "_faceMatchStateKey",
            "_faceMatchingProgressStateKey",
        ):
            method = getattr(self, method_name, None)
            if callable(method):
                try:
                    candidate_keys.append(method(normalized_user))
                except Exception:
                    pass
        if normalized_user:
            candidate_keys.extend([
                normalized_user,
                f"{normalized_user}:face_match",
                f"{normalized_user}_face_match",
            ])
        candidate_keys.append("face_match")

        memory_progress: Dict[str, Any] = {}
        with self.runtime_state.lock("face_match_progress"):
            for key in candidate_keys:
                progress = self.runtime_state.memory("face_match_progress").get(key)
                if isinstance(progress, dict) and progress:
                    memory_progress = dict(progress)
                    break
            if not memory_progress and len(self.runtime_state.memory("face_match_progress")) == 1:
                only_progress = next(iter(self.runtime_state.memory("face_match_progress").values()))
                if isinstance(only_progress, dict) and only_progress:
                    memory_progress = dict(only_progress)

        if memory_progress:
            payload = self._attachFaceMatchStatusPayload(
                self._normalizeFaceMatchingProgressForDisplay(
                    user_key,
                    self._normalizeFaceMatchingProgress(user_key, memory_progress),
                )
            )
            return self._compactFaceMatchingProgressForResponse(payload) if compact_for_response else payload

        payload = self._getFaceMatchingProgressCore(user_key)
        return self._compactFaceMatchingProgressForResponse(payload) if compact_for_response else payload


    def _getFaceMatchingProgressCore(self, user_key: str) -> Dict[str, Any]:
        current = self.runtime_state.read_persisted("face_match_progress", user_key)
        if not isinstance(current, dict) or not current:
            with self.runtime_state.lock("face_match_progress"):
                current = self.runtime_state.memory("face_match_progress").get(user_key, {})
        payload = dict(current) if isinstance(current, dict) else {}
        return self._attachFaceMatchStatusPayload(
            self._normalizeFaceMatchingProgressForDisplay(
                user_key,
                self._normalizeFaceMatchingProgress(user_key, payload),
            )
        )

    def _normalizeFaceMatchingProgress(self, user_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        self._syncFaceMatchProgressCountsFromCursor(current)
        return self.runtime_state.normalize_progress(
            current,
            operation="face_match",
        )

    def requestStopFaceMatching(self, user_key: str) -> Dict[str, Any]:
        return self.face_match_workflow.request_stop(user_key)

    def _shouldStopFaceMatching(self, user_key: str) -> bool:
        return self.face_match_workflow.should_stop(user_key)

    def _refreshSessionIfNeeded(
        self,
        *,
        user_key: str,
        base_url: str,
        last_keepalive_at: float,
    ) -> float:
        now = monotonic()
        if now - last_keepalive_at < self.SESSION_KEEPALIVE_INTERVAL_SECONDS:
            return last_keepalive_at
        self.session_manager.keepalive(user_key, base_url=base_url)
        return now

    def _refreshFaceMatchingSessionIfNeeded(
        self,
        *,
        user_key: str,
        base_url: str,
        last_keepalive_at: float,
    ) -> float:
        return self._refreshSessionIfNeeded(
            user_key=user_key,
            base_url=base_url,
            last_keepalive_at=last_keepalive_at,
        )

    def _setChecksProgress(self, user_key: str, **updates: Any) -> None:
        check_type = self._normalizeChecksType(updates.get("check_type"))
        state_key = self._checksStateKey(user_key, check_type)
        with self.runtime_state.lock("checks_progress"):
            current = dict(self.runtime_state.memory("checks_progress").get(state_key, {}))
            current.update(updates)
            current["check_type"] = check_type
            current = self.runtime_state.stamp_progress(
                current,
                operation="checks",
                action=check_type,
                operation_discriminator=check_type,
            )
            self.runtime_state.memory("checks_progress")[state_key] = current
        self.runtime_state.persist("checks_progress", state_key, current)

    def _setChecksProgressMessage(
        self,
        user_key: str,
        check_type: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
            "check_type": self._normalizeChecksType(check_type),
        }
        payload.update(updates)
        self._setChecksProgress(user_key, **payload)

    @staticmethod
    def _normalizeChecksType(check_type: Any) -> str:
        normalized = str(check_type or "dimension_issues").strip().lower()
        if normalized not in {
            "dimension_issues",
            "duplicate_faces",
            "position_deviations",
            "name_conflicts",
            "face_frame_standardization",
        }:
            return "dimension_issues"
        return normalized

    @staticmethod
    def _checksTypeOptions() -> Tuple[str, ...]:
        return ("dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts")

    def _checksStateKey(self, user_key: str, check_type: Any) -> str:
        return f"{user_key}_{self._normalizeChecksType(check_type)}"

    def _runningChecksScanProgress(self, user_key: str, *, exclude_check_type: Any = "") -> Optional[Dict[str, Any]]:
        excluded_type = self._normalizeChecksType(exclude_check_type) if str(exclude_check_type or "").strip() else ""

        def is_running_scan(progress: Any, candidate_type: str) -> bool:
            return (
                isinstance(progress, dict)
                and bool(progress.get("running"))
                and str(progress.get("source_mode") or "").strip().lower() == "scan"
                and str(progress.get("check_type") or "").strip().lower() == candidate_type
            )

        for candidate_type in self._checksTypeOptions():
            if excluded_type and candidate_type == excluded_type:
                continue

            state_key = self._checksStateKey(user_key, candidate_type)
            with self.runtime_state.lock("checks_progress"):
                memory_progress = dict(self.runtime_state.memory("checks_progress").get(state_key, {}))

            if is_running_scan(memory_progress, candidate_type):
                return memory_progress

            progress = self.getChecksProgress(user_key, candidate_type)
            if is_running_scan(progress, candidate_type):
                return progress

        return None

    @staticmethod
    def _isRunningProgress(progress: Any) -> bool:
        return RuntimeOperationService.is_running_progress(progress)

    def _isBlockingRunningProgress(self, progress: Any) -> bool:
        return self.runtime_operations.is_blocking_running_progress(progress)

    def _runningOperationProgress(self, user_key: str, *, exclude_operation: str = "") -> Optional[Dict[str, Any]]:
        excluded = str(exclude_operation or "").strip().lower()

        def candidates():
            if excluded != "file_analysis":
                yield "file_analysis", self.getFileAnalysisProgress()
            if excluded != "face_match":
                yield "face_match", self.getFaceMatchingProgress(user_key)
            if excluded != "checks":
                yield "checks", self._runningChecksScanProgress(user_key)
            if excluded != "cleanup":
                yield "cleanup", self.getCleanupProgress(user_key, "normalize_names")

        return self.runtime_state.first_blocking_progress(
            candidates(),
            exclude_operation=excluded,
        )

    def _buildStartBlockedByRunningOperationPayload(
        self,
        running_progress: Dict[str, Any],
        *,
        requested_operation: str,
    ) -> Dict[str, Any]:
        return self.runtime_operations.blocked_by_running_operation_payload(
            running_progress,
            requested_operation=requested_operation,
        )

    def _normalizeStatusChecksType(self, check_type: Any) -> str:
        return self.status_builder.normalize_checks_type(check_type)

    def _deriveStatusPhase(self, *, running: Any = False, finished: Any = False, stop_requested: Any = False, message_key: str = "", status: str = "") -> str:
        return self.status_builder.derive_phase(
            running=running,
            finished=finished,
            stop_requested=stop_requested,
            message_key=message_key,
            status=status,
        )

    def _buildStatusCounter(self, key: str, *, value: Any, label_key: str = "", fallback_label: str = "", show_when_zero: bool = False) -> Dict[str, Any]:
        return self.status_builder.counter(
            key,
            value=value,
            label_key=label_key,
            fallback_label=fallback_label,
            show_when_zero=show_when_zero,
        )

    def _buildStatusProgress(
        self,
        *,
        kind: str,
        current: Any = 0,
        total: Any = 0,
        title_key: str = "",
        fallback_title: str = "",
        primary_label_key: str = "",
        fallback_primary_label: str = "",
        secondary_label_key: str = "",
        fallback_secondary_label: str = "",
    ) -> Dict[str, Any]:
        return self.status_builder.progress(
            kind=kind,
            current=current,
            total=total,
            title_key=title_key,
            fallback_title=fallback_title,
            primary_label_key=primary_label_key,
            fallback_primary_label=fallback_primary_label,
            secondary_label_key=secondary_label_key,
            fallback_secondary_label=fallback_secondary_label,
        )

    def _buildStatusPayload(
        self,
        *,
        operation: str,
        action: str,
        mode: str,
        phase: str,
        save_only: bool = False,
        progress: Optional[Dict[str, Any]] = None,
        counters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self.status_builder.payload(
            operation=operation,
            action=action,
            mode=mode,
            phase=phase,
            save_only=save_only,
            progress=progress,
            counters=counters,
        )

    def _buildChecksStatusPayload(
        self,
        *,
        check_type: str,
        source_mode: str,
        phase: str,
        save_only: bool = False,
        files_scanned: Any = 0,
        total_files: Any = 0,
        findings_count: Any = 0,
        resolved_count: Any = 0,
        ignored_count: Any = 0,
        skipped_count: Any = 0,
        errors_count: Any = 0,
        entries_current: Any = 0,
        entries_total: Any = 0,
        stored_findings_count: Any = 0,
        transferred_count: Any = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        return self.status_builder.checks_payload(
            check_type=check_type,
            source_mode=source_mode,
            phase=phase,
            save_only=save_only,
            files_scanned=files_scanned,
            total_files=total_files,
            findings_count=findings_count,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            skipped_count=skipped_count,
            errors_count=errors_count,
            entries_current=entries_current,
            entries_total=entries_total,
            stored_findings_count=stored_findings_count,
            transferred_count=transferred_count,
            **_ignored,
        )

    def _buildFaceMatchStatusPayload(
        self,
        *,
        action: str,
        source_mode: str = "scan",
        phase: str = "running",
        save_only: bool = False,
        progress_kind: str = "",
        current: Any = 0,
        total: Any = 0,
        findings_count: Any = 0,
        transferred_count: Any = 0,
        skipped_count: Any = 0,
        errors_count: Any = 0,
        created_count: Any = 0,
        assigned_count: Any = 0,
        updated_count: Any = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        return self.status_builder.face_match_payload(
            action=action,
            source_mode=source_mode,
            phase=phase,
            save_only=save_only,
            progress_kind=progress_kind,
            current=current,
            total=total,
            findings_count=findings_count,
            transferred_count=transferred_count,
            skipped_count=skipped_count,
            errors_count=errors_count,
            created_count=created_count,
            assigned_count=assigned_count,
            updated_count=updated_count,
            **_ignored,
        )

    def _attachChecksStatusPayload(self, payload: Dict[str, Any], *, check_type: str = "") -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        existing_status = payload.get("status")
        existing_status_text = existing_status if isinstance(existing_status, str) else ""
        normalized_type = self._normalizeStatusChecksType(check_type or payload.get("check_type") or "")
        source_mode = str(payload.get("source_mode") or "scan").strip().lower() or "scan"
        phase = self._deriveStatusPhase(running=payload.get("running"), finished=payload.get("finished"), stop_requested=payload.get("stop_requested"), message_key=str(payload.get("message_key") or payload.get("message") or ""), status=existing_status_text)
        payload["status"] = self._buildChecksStatusPayload(check_type=normalized_type, source_mode=source_mode, phase=phase, save_only=bool(payload.get("save_only")), files_scanned=payload.get("files_scanned", 0), total_files=payload.get("total_files", 0), findings_count=payload.get("findings_count", 0), resolved_count=payload.get("resolved_count", 0), ignored_count=payload.get("ignored_count", 0), skipped_count=payload.get("skipped_count", 0), errors_count=payload.get("errors_count", 0), entries_current=payload.get("entries_current", payload.get("current", 0)), entries_total=payload.get("entries_total", payload.get("count", payload.get("total", 0))))
        return payload

    def attachChecksStatusForResponse(
        self,
        payload: Dict[str, Any],
        *,
        check_type: str = "",
        source_mode: str = "",
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        normalized_check_type = str(check_type or payload.get("check_type") or "").strip().lower()
        if normalized_check_type:
            payload.setdefault("check_type", normalized_check_type)

        normalized_source_mode = str(source_mode or payload.get("source_mode") or "").strip().lower()
        if normalized_source_mode:
            payload.setdefault("source_mode", normalized_source_mode)

        return self._attachChecksStatusPayload(payload, check_type=normalized_check_type)

    def _attachFaceMatchStatusPayload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        existing_status = payload.get("status")
        existing_action = existing_status.get("action") if isinstance(existing_status, dict) else ""
        existing_mode = existing_status.get("mode") if isinstance(existing_status, dict) else ""
        action = str(payload.get("action") or payload.get("operation") or existing_action or "").strip().lower()
        source_mode = str(payload.get("source_mode") or payload.get("mode") or existing_mode or "scan").strip().lower() or "scan"
        phase = self._deriveStatusPhase(running=payload.get("running"), finished=payload.get("finished"), stop_requested=payload.get("stop_requested"), message_key=str(payload.get("message_key") or payload.get("message") or payload.get("status") or ""), status=str(existing_status or "") if not isinstance(existing_status, dict) else "")
        current = payload.get("entries_current", payload.get("persons_read", payload.get("images_read", payload.get("files_read", 0))))
        total = payload.get("entries_total", payload.get("persons_total", payload.get("images_total", payload.get("files_total", 0))))
        payload["status"] = self._buildFaceMatchStatusPayload(action=action, source_mode=source_mode, phase=phase, save_only=bool(payload.get("save_only")), progress_kind="entries" if source_mode == "findings" else "", current=current, total=total, findings_count=payload.get("findings_count", 0), transferred_count=payload.get("transferred_count", 0), skipped_count=payload.get("skipped_count", 0), errors_count=payload.get("errors_count", 0))
        return payload

    def _buildChecksStartBlockedPayload(self, running_progress: Dict[str, Any], *, requested_check_type: str) -> Dict[str, Any]:
        payload = dict(running_progress) if isinstance(running_progress, dict) else {}
        requested_type = self._normalizeStatusChecksType(requested_check_type)
        payload["blocked_by_running_scan"] = True
        payload["requested_check_type"] = requested_type
        payload["status"] = self._buildChecksStatusPayload(
            check_type=str(payload.get("check_type") or requested_type or ""),
            source_mode=str(payload.get("source_mode") or "scan"),
            phase="blocked",
            save_only=bool(payload.get("save_only")),
            files_scanned=payload.get("files_scanned", 0),
            total_files=payload.get("total_files", 0),
            findings_count=payload.get("findings_count", 0),
            resolved_count=payload.get("resolved_count", 0),
            ignored_count=payload.get("ignored_count", 0),
            skipped_count=payload.get("skipped_count", 0),
            errors_count=payload.get("errors_count", 0),
        )
        return payload

    def _invalidateChecksCandidatePathsCache(self, user_key: str, check_type: Any) -> None:
        self.checks_workflow.invalidate_candidate_paths_cache(user_key, check_type)

    def _getChecksCandidatePaths(
        self,
        *,
        user_key: str,
        check_type: Any,
        shared_folder: str,
        changed_since_days: int = 0,
        use_cache: bool = True,
    ) -> List[str]:
        return self.checks_workflow.get_candidate_paths(
            user_key=user_key,
            check_type=check_type,
            shared_folder=shared_folder,
            changed_since_days=changed_since_days,
            use_cache=use_cache,
        )

    def _normalizeChecksProgress(self, user_key: str, check_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        normalized_type = self._normalizeChecksType(check_type or current.get("check_type"))
        current["check_type"] = normalized_type
        current["findings_count"] = max(0, int(current.get("findings_count") or 0))
        current["resolved_count"] = max(0, int(current.get("resolved_count") or 0))
        current["ignored_count"] = max(0, int(current.get("ignored_count") or 0))
        return self.runtime_state.normalize_progress(
            current,
            operation="checks",
            action=normalized_type,
        )

    def getChecksProgress(self, user_key: str, check_type: str) -> Dict[str, Any]:
        normalized_user = str(user_key or "").strip()
        try:
            normalized_type = self._normalizeChecksType(check_type)
        except Exception:
            normalized_type = str(check_type or "").strip().lower()

        candidate_keys: List[str] = []
        try:
            candidate_keys.append(self._checksStateKey(normalized_user, normalized_type))
        except Exception:
            pass
        if normalized_user and normalized_type:
            candidate_keys.extend([
                f"{normalized_user}_{normalized_type}",
                f"{normalized_user}:{normalized_type}",
            ])
        if normalized_type:
            candidate_keys.append(normalized_type)
        if normalized_user:
            candidate_keys.append(normalized_user)

        memory_progress: Dict[str, Any] = {}
        with self.runtime_state.lock("checks_progress"):
            for key in candidate_keys:
                progress = self.runtime_state.memory("checks_progress").get(key)
                if isinstance(progress, dict) and progress:
                    memory_progress = dict(progress)
                    break
            if not memory_progress and len(self.runtime_state.memory("checks_progress")) == 1:
                only_progress = next(iter(self.runtime_state.memory("checks_progress").values()))
                if isinstance(only_progress, dict) and only_progress:
                    progress_type = str(only_progress.get("check_type") or "").strip().lower()
                    if not normalized_type or not progress_type or progress_type == normalized_type:
                        memory_progress = dict(only_progress)

        if memory_progress:
            return self._attachChecksStatusPayload(memory_progress, check_type=normalized_type)

        return self._getChecksProgressCore(user_key, check_type)


    def _getChecksProgressCore(self, user_key: str, check_type: str) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        state_key = self._checksStateKey(user_key, normalized_type)
        current = self.runtime_state.read_persisted("checks_progress", state_key)
        if not isinstance(current, dict) or not current:
            with self.runtime_state.lock("checks_progress"):
                current = self.runtime_state.memory("checks_progress").get(state_key, {})
        return self._normalizeChecksProgress(user_key, normalized_type, dict(current) if isinstance(current, dict) else {})

    def requestStopChecks(self, user_key: str, check_type: str) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        self._setChecksProgressMessage(
            user_key,
            normalized_type,
            "checks:progress_stopping",
            stop_requested=True,
        )
        return self.getChecksProgress(user_key, normalized_type)

    def _shouldStopChecks(self, user_key: str, check_type: str) -> bool:
        progress = self.getChecksProgress(user_key, check_type)
        return bool(progress.get("stop_requested"))

    @staticmethod
    def _cleanupActionOptions() -> set:
        return {
            "normalize_names",
            "standardize_face_frames",
            "recognition_build_profiles",
            "recognition_check_reference_outliers",
            "recognition_analyze_unknown_faces",
            "recognition_check_person_assignments",
        }

    @classmethod
    def _normalizeCleanupAction(cls, action: Any) -> str:
        normalized = str(action or "normalize_names").strip().lower()
        allowed = cls._cleanupActionOptions()
        return normalized if normalized in allowed else "normalize_names"

    @staticmethod
    def _normalizeCleanupTargets(targets: Any) -> List[str]:
        # Cleanup name normalization must never rewrite or merge Photos persons.
        allowed = {"ACD", "MICROSOFT", "MWG_REGIONS"}
        normalized: List[str] = []
        for item in list(targets or []):
            target = str(item or "").strip().upper()
            if target not in allowed or target in normalized:
                continue
            normalized.append(target)
        return normalized

    def _cleanupStateKey(self, user_key: str, action: Any) -> str:
        return f"{user_key}_{self._normalizeCleanupAction(action)}"

    def _normalizeCleanupProgress(self, user_key: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        normalized_action = self._normalizeCleanupAction(action or current.get("action"))
        current["action"] = normalized_action
        current["targets"] = self._normalizeCleanupTargets(current.get("targets"))
        return self.runtime_state.normalize_progress(
            current,
            operation="cleanup",
            action=normalized_action,
        )

    def _setCleanupProgress(self, user_key: str, **updates: Any) -> Dict[str, Any]:
        action = self._normalizeCleanupAction(updates.get("action"))
        state_key = self._cleanupStateKey(user_key, action)
        with self.runtime_state.lock("cleanup_progress"):
            current = dict(self.runtime_state.memory("cleanup_progress").get(state_key, {}))
            current.update(updates)
            current["action"] = action
            current["targets"] = self._normalizeCleanupTargets(current.get("targets"))
            current = self.runtime_state.stamp_progress(
                current,
                operation="cleanup",
                action=action,
                operation_discriminator=action,
            )
            self.runtime_state.memory("cleanup_progress")[state_key] = current
        self.runtime_state.persist("cleanup_progress", state_key, current)
        return current

    def _setCleanupProgressMessage(
        self,
        user_key: str,
        action: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
            "action": self._normalizeCleanupAction(action),
        }
        payload.update(updates)
        self._setCleanupProgress(user_key, **payload)

    def getCleanupProgress(self, user_key: str, action: str = "normalize_names") -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        state_key = self._cleanupStateKey(user_key, normalized_action)
        with self.runtime_state.lock("cleanup_progress"):
            current = self.runtime_state.memory("cleanup_progress").get(state_key, {})
        if not isinstance(current, dict) or not current:
            current = self.runtime_state.read_persisted("cleanup_progress", state_key)
        return self._normalizeCleanupProgress(user_key, normalized_action, dict(current) if isinstance(current, dict) else {})

    def requestStopCleanup(self, user_key: str, action: str = "normalize_names") -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        self._setCleanupProgressMessage(
            user_key,
            normalized_action,
            "cleanup:progress_stopping",
            stop_requested=True,
        )
        return self.getCleanupProgress(user_key, normalized_action)

    def _shouldStopCleanup(self, user_key: str, action: str) -> bool:
        progress = self.getCleanupProgress(user_key, action)
        return bool(progress.get("stop_requested"))

    def _buildChecksResumeCursor(
        self,
        *,
        path_index: int,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
        source_mode: str,
        check_type: str,
        save_only: bool,
        findings_count: int,
        resolved_count: int = 0,
        ignored_count: int = 0,
        metrics_trusted: bool = True,
        changed_since_days: int = 0,
    ) -> Dict[str, Any]:
        return self.checks_workflow.build_resume_cursor(
            path_index=path_index,
            pending_entries=pending_entries,
            source_mode=source_mode,
            check_type=check_type,
            save_only=save_only,
            findings_count=findings_count,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            metrics_trusted=metrics_trusted,
            changed_since_days=changed_since_days,
        )

    def _buildChecksScanPayload(
        self,
        *,
        check_type: str,
        save_only: bool,
        files_scanned: int,
        total_files: int,
        findings_count: int,
        path_index: int,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
        current_path: str = "",
        result: Optional[Dict[str, Any]] = None,
        message_key: str = "",
        message: str = "",
        message_params: Optional[Dict[str, Any]] = None,
        running: bool = False,
        finished: bool = True,
        stop_requested: bool = False,
        resolved_count: int = 0,
        ignored_count: int = 0,
        changed_since_days: int = 0,
    ) -> Dict[str, Any]:
        return self.checks_workflow.build_scan_payload(
            check_type=check_type,
            save_only=save_only,
            files_scanned=files_scanned,
            total_files=total_files,
            findings_count=findings_count,
            path_index=path_index,
            pending_entries=pending_entries,
            current_path=current_path,
            result=result,
            message_key=message_key,
            message=message,
            message_params=message_params,
            running=running,
            finished=finished,
            stop_requested=stop_requested,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            changed_since_days=changed_since_days,
        )

    def _countOpenChecksScanFindings(
        self,
        current_entry: Optional[Dict[str, Any]] = None,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        return self.checks_workflow.count_open_scan_findings(current_entry, pending_entries)

    def _markChecksEntriesManualReviewRequired(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.checks_workflow.mark_entries_manual_review_required(entries)

    def _currentChecksResultEntry(self, progress: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return self.checks_workflow.current_result_entry(progress)

    def _trustedChecksResumeCursor(
        self,
        current_progress: Optional[Dict[str, Any]],
        *,
        check_type: str,
        save_only: bool,
        advance_current_result: bool = False,
    ) -> Dict[str, Any]:
        return self.checks_workflow.trusted_resume_cursor(
            current_progress,
            check_type=check_type,
            save_only=save_only,
            advance_current_result=advance_current_result,
        )

    def _newChecksFindingsDebouncer(self) -> WriteDebouncer:
        return WriteDebouncer(
            self.CHECKS_FINDINGS_FLUSH_INTERVAL_SECONDS,
            self.CHECKS_FINDINGS_FLUSH_ENTRY_INTERVAL,
        )

    def _newChecksScanContext(self) -> ScanContext:
        return ScanContext(self.config.readMergedConfig())

    def _buildCheckEntriesForType(
        self,
        *,
        image_path: str,
        review_type: str,
        analysis: Optional[Dict[str, Any]] = None,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        normalized_type = str(review_type or "").strip().lower()
        if normalized_type == "dimension_issues":
            entry = self._buildDimensionMismatchReviewEntry(image_path, analysis)
            return [entry] if entry else []
        if normalized_type == "duplicate_faces":
            return self._excludeIgnoredChecksEntries(
                normalized_type,
                self._buildDuplicateFaceReviewEntries(image_path, analysis),
            )
        if normalized_type == "position_deviations":
            comparison_faces = photo_faces
            if comparison_faces is None and self._configuredAnalysisChecks().get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"):
                comparison_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                )
            return self._excludeIgnoredChecksEntries(
                normalized_type,
                self._buildPositionDeviationReviewEntries(image_path, analysis, comparison_faces),
            )
        if normalized_type == "name_conflicts":
            comparison_faces = photo_faces
            if comparison_faces is None and self._configuredAnalysisChecks().get("NAME_CONFLICTS_INCLUDE_PHOTOS"):
                comparison_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                )
            return self._excludeIgnoredChecksEntries(
                normalized_type,
                self._buildNameConflictReviewEntries(image_path, analysis, comparison_faces),
            )
        return []

    def _writeChecksFindings(
        self,
        *,
        check_type: str,
        status: str,
        shared_folder: str,
        source_mode: str,
        save_only: bool,
        entries: List[Dict[str, Any]],
    ) -> bool:
        return self.checks_workflow.write_findings(
            check_type=check_type,
            status=status,
            shared_folder=shared_folder,
            source_mode=source_mode,
            save_only=save_only,
            entries=entries,
        )

    def _resumeChecksSavedEntries(
        self,
        *,
        check_type: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.checks_workflow.resume_saved_entries(
            check_type=check_type,
            save_only=save_only,
            resume_cursor=resume_cursor,
        )

    def _appendUniqueChecksFindings(
        self,
        existing_entries: List[Dict[str, Any]],
        new_entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.checks_workflow.append_unique_findings(existing_entries, new_entries)

    def _writePersistedChecksFindingsStatus(self, *, check_type: str, status: str, save_only: bool) -> None:
        self.checks_workflow.write_persisted_findings_status(
            check_type=check_type,
            status=status,
            save_only=save_only,
        )

    def getChecksFindingEntries(self, *, check_type: str) -> Dict[str, Any]:
        return self.checks_workflow.get_finding_entries(check_type=check_type)

    def getChecksFindingsStatus(self) -> Dict[str, Any]:
        return self.checks_workflow.get_findings_status()

    def refreshChecksFindingEntries(
        self,
        *,
        check_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        return self.checks_workflow.refresh_finding_entries(
            check_type=check_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
        )

    def _refreshChecksFindingEntriesUnlocked(
        self,
        *,
        check_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        return self.checks_workflow._refresh_finding_entries_unlocked(
            check_type=check_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
        )

    def refreshChecksFindingEntriesForImage(
        self,
        *,
        check_type: str,
        image_path: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.checks_workflow.refresh_finding_entries_for_image(
            check_type=check_type,
            image_path=image_path,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )

    def _refreshChecksFindingEntriesForImageUnlocked(
        self,
        *,
        check_type: str,
        image_path: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.checks_workflow._refresh_finding_entries_for_image_unlocked(
            check_type=check_type,
            image_path=image_path,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )

    def refreshChecksScanProgressForImage(
        self,
        *,
        user_key: str,
        check_type: str,
        image_path: str,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
        resolved_delta: int = 0,
        ignored_delta: int = 0,
    ) -> Dict[str, Any]:
        return self.checks_workflow.refresh_scan_progress_for_image(
            user_key=user_key,
            check_type=check_type,
            image_path=image_path,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
            resolved_delta=resolved_delta,
            ignored_delta=ignored_delta,
        )

    def _getSuggestedNameConflictRename(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.checks_workflow.get_suggested_name_conflict_rename(item)

    def _getSuggestedDuplicateFaceDeletion(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.checks_workflow.get_suggested_duplicate_face_deletion(item)

    def _storedChecksFaceFromEntry(self, face: Any) -> Dict[str, Any]:
        return self.checks_workflow.stored_checks_face_from_entry(face)

    def _buildStoredChecksReviewItemFromEntry(self, entry: Any) -> Optional[Dict[str, Any]]:
        return self.checks_workflow.build_stored_checks_review_item_from_entry(entry)

    def _resolveChecksReviewEntry(self, *, entry: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return self.checks_workflow.resolve_checks_review_entry(entry=entry, **kwargs)

    def _resolveChecksReviewEntryCore(self, *, entry: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return self.checks_workflow.resolve_checks_review_entry_core(entry=entry, **kwargs)

    def _runFaceMatching(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        limit: int,
        offset: int,
        skip_face_ids: Optional[List[int]],
        skip_targets: Optional[List[str]],
        auto: bool,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.face_match_workflow._run_face_matching(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            action=action,
            limit=limit,
            offset=offset,
            skip_face_ids=skip_face_ids,
            skip_targets=skip_targets,
            auto=auto,
            save_only=save_only,
            resume_cursor=resume_cursor,
        )

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def _setFileAnalysisProgress(self, persist: bool = True, **updates: Any) -> None:
        with self.runtime_state.lock("file_analysis_progress"):
            current = dict(self.runtime_state.singleton("file_analysis_progress"))
            current.update(updates)
            current = self.runtime_state.stamp_progress(
                current,
                operation="file_analysis",
                action=current.get("action") or "file_analysis",
            )
            self.runtime_state.replace_singleton("file_analysis_progress", current)
        if persist:
            self.runtime_state.persist("file_analysis_progress", "default", current)

    def _normalizeFileAnalysisProgress(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        return self.runtime_state.normalize_progress(
            current,
            operation="file_analysis",
            action=current.get("action") or "file_analysis",
        )

    def _enrichFileAnalysisProgressWithFindings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        field_map = {
            "dimension_issues": ["files_with_mwg_dimension_mismatch", "files_with_dimension_issues"],
            "duplicate_faces": ["files_with_duplicate_faces"],
            "position_deviations": ["files_with_face_position_deviations"],
            "name_conflicts": ["files_with_name_conflicts"],
        }
        for finding_type, fields in field_map.items():
            status_reader = getattr(self.file_analysis, "readCheckFindingsStatus", None)
            findings = status_reader(finding_type) if callable(status_reader) else self.file_analysis.readCheckFindings(finding_type)
            if not isinstance(findings, dict):
                continue
            findings_count = int(findings.get("count") or 0)
            same_job = (
                not current.get("job_id")
                or not findings.get("job_id")
                or str(current.get("job_id")) == str(findings.get("job_id"))
            )
            if not same_job:
                continue
            for field in fields:
                if field not in current and findings_count >= 0:
                    current[field] = findings_count
        return current

    def getFileAnalysisProgress(self) -> Dict[str, Any]:
        worker = self.runtime_state.get_value("file_analysis_threads", "default")
        if worker and worker.is_alive():
            with self.runtime_state.lock("file_analysis_progress"):
                current = dict(self.runtime_state.singleton("file_analysis_progress"))
            if current:
                return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(current))
        current = self.runtime_state.read_persisted("file_analysis_progress", "default")
        if not isinstance(current, dict) or not current:
            with self.runtime_state.lock("file_analysis_progress"):
                current = dict(self.runtime_state.singleton("file_analysis_progress"))
        if current:
            return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(current))
        latest = self.file_analysis.readLatestResult()
        if not isinstance(latest, dict):
            return {}
        return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(latest))

    def getFaceMatchFindings(self) -> Dict[str, Any]:
        return self.face_match_workflow.get_findings()

    def getFaceMatchFindingsStatus(self) -> Dict[str, Any]:
        return self.face_match_workflow.get_findings_status()

    def _resumeFaceMatchSavedEntries(
        self,
        *,
        action: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.face_match_workflow.resume_saved_entries(
            action=action,
            save_only=save_only,
            resume_cursor=resume_cursor,
        )

    def _faceMatchFindingEntryToken(self, entry: Any) -> str:
        if not isinstance(entry, dict):
            return ""
        face = entry.get("face")
        if isinstance(face, dict) and face.get("face_id") not in (None, ""):
            return json.dumps(
                {
                    "action": str(entry.get("action") or "search_photo_face_in_file").strip().lower(),
                    "face_id": face.get("face_id"),
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        image_path = str(entry.get("image_path") or "").strip()
        metadata_face = entry.get("metadata_face")
        if image_path and isinstance(metadata_face, dict):
            return self._faceMatchTargetToken(image_path=image_path, face=metadata_face)
        return ""

    def _appendUniqueFaceMatchFinding(
        self,
        entries: List[Dict[str, Any]],
        entry: Dict[str, Any],
    ) -> bool:
        if self._isFaceMatchFindingSuppressed(entry):
            return False
        return self.face_match_workflow.append_unique_finding(entries, entry)

    def _isFaceMatchFindingSuppressed(self, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        repository = getattr(self, "face_suppressions", None)
        if repository is None:
            return False
        token = self._faceMatchFindingEntryToken(entry)
        if token and repository.is_suppressed(f"face-match:{token}"):
            return True
        face = entry.get("face") if isinstance(entry.get("face"), dict) else {}
        face_id = face.get("face_id")
        if face_id not in (None, "") and repository.is_suppressed(f"photos-face:{face_id}"):
            return True
        metadata_face = entry.get("metadata_face") if isinstance(entry.get("metadata_face"), dict) else {}
        normalized_name = NameMappingService._normalize_name_value(metadata_face.get("name"))
        return bool(
            normalized_name
            and repository.is_suppressed(f"metadata-name:{normalized_name}")
        )

    def _faceMatchSavedEntryFaceIds(self, entries: List[Dict[str, Any]]) -> List[int]:
        face_ids: List[int] = []
        seen = set()
        for entry in entries:
            face = entry.get("face") if isinstance(entry, dict) else None
            face_id = face.get("face_id") if isinstance(face, dict) else None
            try:
                normalized_face_id = int(face_id)
            except (TypeError, ValueError):
                continue
            if normalized_face_id not in seen:
                seen.add(normalized_face_id)
                face_ids.append(normalized_face_id)
        return face_ids

    def _writePersistedFaceMatchFindingsStatus(
        self,
        *,
        action: str,
        status: str,
        auto: bool,
        save_only: bool,
        transferred_count: int,
    ) -> None:
        self.face_match_workflow.write_persisted_findings_status(
            action=action,
            status=status,
            auto=auto,
            save_only=save_only,
            transferred_count=transferred_count,
        )

    def _faceMatchSavedEntryTargetTokens(self, entries: List[Dict[str, Any]]) -> List[str]:
        tokens: List[str] = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                continue
            token = self._faceMatchTargetToken(image_path=image_path, face=metadata_face)
            if token and token not in seen:
                seen.add(token)
                tokens.append(token)
        return tokens

    def requestStopFileAnalysis(self) -> Dict[str, Any]:
        self._setFileAnalysisProgress(stop_requested=True, message="Stopping file analysis...")
        return self.getFileAnalysisProgress()

    def _shouldStopFileAnalysis(self) -> bool:
        progress = self.getFileAnalysisProgress()
        return bool(progress.get("stop_requested"))

    def _persistFileAnalysisResult(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.file_analysis.writeLatestResult(payload)
        self._setFileAnalysisProgress(**payload)
        return payload

    def _writeFileAnalysisCheckFindings(
        self,
        *,
        finding_type: str,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        findings: List[Any],
    ) -> None:
        paths: List[str] = []
        entries: List[Dict[str, Any]] = []
        seen_paths = set()
        for finding in findings:
            if isinstance(finding, dict):
                entries.append(finding)
                image_path = str(finding.get("image_path") or "").strip()
                if image_path and image_path not in seen_paths:
                    seen_paths.add(image_path)
                    paths.append(image_path)
                continue
            image_path = str(finding or "").strip()
            if image_path and image_path not in seen_paths:
                seen_paths.add(image_path)
                paths.append(image_path)
        self.file_analysis.writeCheckFindings(
            finding_type,
            {
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": self._timestamp_now() if finished else "",
                "last_updated_at": self._timestamp_now(),
                "status": status,
                "shared_folder": shared_folder,
                "count": len(entries) if entries else len(paths),
                "paths": paths,
                "entries": entries,
            }
        )

    def _writeAllFileAnalysisCheckFindings(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        findings_by_type: Dict[str, List[Any]],
    ) -> None:
        for finding_type, findings in findings_by_type.items():
            self._writeFileAnalysisCheckFindings(
                finding_type=finding_type,
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status=status,
                finished=finished,
                findings=findings,
            )

    def _writeFaceMatchFindings(
        self,
        *,
        status: str,
        shared_folder: str,
        action: str,
        auto: bool,
        save_only: bool,
        transferred_count: int,
        entries: List[Dict[str, Any]],
        job_id: Optional[str] = None,
        started_at: Optional[str] = None,
        finished: bool = True,
    ) -> None:
        self.face_match_workflow.write_findings(
            status=status,
            shared_folder=shared_folder,
            action=action,
            auto=auto,
            save_only=save_only,
            transferred_count=transferred_count,
            entries=entries,
            job_id=job_id,
            started_at=started_at,
            finished=finished,
        )

    def _shouldFlushFaceMatchFindings(
        self,
        *,
        entries_count: int,
        last_flush_count: int,
        last_flush_at: float,
    ) -> bool:
        return self.face_match_workflow.should_flush_findings(
            entries_count=entries_count,
            last_flush_count=last_flush_count,
            last_flush_at=last_flush_at,
        )

    def _writeReverseFaceMatchCandidates(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        entries: List[Dict[str, Any]],
    ) -> None:
        self.file_analysis.writeCheckFindings(
            "face_match_candidates",
            {
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": self._timestamp_now() if finished else "",
                "last_updated_at": self._timestamp_now(),
                "status": status,
                "shared_folder": shared_folder,
                "count": len(entries),
                "entries": entries,
            }
        )

    def _getReverseFaceMatchCandidateEntries(self) -> List[Dict[str, Any]]:
        findings = self.file_analysis.readCheckFindings("face_match_candidates")
        entries = findings.get("entries") if isinstance(findings, dict) and isinstance(findings.get("entries"), list) else []
        normalized_entries: List[Dict[str, Any]] = []
        seen_tokens = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if self._isFaceMatchFindingSuppressed(entry):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                continue
            token = self._faceMatchTargetToken(image_path=image_path, face=metadata_face)
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            normalized_entries.append({
                "action": "search_file_face_in_sources",
                "image_path": image_path,
                "metadata_face": metadata_face,
            })
        return normalized_entries

    def _buildReverseFaceMatchCandidateEntry(self, *, image_path: str, metadata_face: MetadataFace) -> Dict[str, Any]:
        return {
            "action": "search_file_face_in_sources",
            "image_path": image_path,
            "metadata_face": metadata_face.to_dict(),
        }

    @staticmethod
    def _normalizeFaceMatchEntry(entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(entry or {})
        metadata_face = normalized.get("metadata_face")
        if hasattr(metadata_face, "to_dict"):
            normalized["metadata_face"] = metadata_face.to_dict()
        return normalized

    @staticmethod
    def _compactFaceMatchPersonForResponse(person: Any) -> Any:
        if not isinstance(person, dict):
            return person
        compact = {
            key: person.get(key)
            for key in ("id", "name", "display_name")
            if person.get(key) is not None
        }
        thumbnail = person.get("thumbnail")
        if isinstance(thumbnail, dict):
            compact["thumbnail"] = {
                key: thumbnail.get(key)
                for key in ("cache_key", "unit_id")
                if thumbnail.get(key) is not None
            }
        additional = person.get("additional")
        if isinstance(additional, dict):
            additional_thumbnail = additional.get("thumbnail")
            if isinstance(additional_thumbnail, dict):
                compact["additional"] = {
                    "thumbnail": {
                        key: additional_thumbnail.get(key)
                        for key in ("cache_key", "unit_id")
                        if additional_thumbnail.get(key) is not None
                    }
                }
        return compact

    @classmethod
    def _compactFaceMatchFindingEntryForResponse(cls, entry: Dict[str, Any]) -> Dict[str, Any]:
        compact = cls._normalizeFaceMatchEntry(entry)
        for key in (
            "lookup_debug",
            "debug",
            "resume_cursor",
            "candidate_persons",
            "known_persons",
            "person_candidates",
        ):
            compact.pop(key, None)
        compact["matched_person"] = cls._compactFaceMatchPersonForResponse(compact.get("matched_person"))
        return compact

    @classmethod
    def _compactFaceMatchFindingEntryForStorage(cls, entry: Dict[str, Any]) -> Dict[str, Any]:
        return cls._compactFaceMatchFindingEntryForResponse(entry)

    def _resolveStoredFaceMatchEntry(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        entry: Dict[str, Any],
        known_persons_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalizeFaceMatchEntry(entry)
        resolved = dict(normalized)
        action = str(resolved.get("action") or "search_photo_face_in_file").strip().lower()
        if action in {"search_file_face_in_sources", "mark_missing_photos_faces", "search_missing_faces_insightface"}:
            image_path = str(resolved.get("image_path") or "").strip()
            metadata_face = resolved.get("metadata_face")
            if action == "search_missing_faces_insightface":
                matched_person = resolved.get("matched_person") if isinstance(resolved.get("matched_person"), dict) else None
                resolved["source_name"] = str(
                    resolved.get("source_name")
                    or (matched_person.get("name") if isinstance(matched_person, dict) else "")
                    or ""
                ).strip()
                resolved["matched_person"] = matched_person
                resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
                resolved["name_mapping"] = None
                resolved["lookup_debug"] = {}
                return resolved
            if action == "mark_missing_photos_faces":
                source_name = str(resolved.get("source_name") or (metadata_face.get("name") if isinstance(metadata_face, dict) else "") or "").strip()
                matched_person, mapped_assignment, lookup_debug = self._lookupMatchedPersonBySourceName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    source_name=source_name,
                    known_persons_cache=known_persons_cache,
                )
                resolved["source_name"] = source_name
                resolved["matched_person"] = matched_person
                resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
                resolved["name_mapping"] = mapped_assignment
                resolved["lookup_debug"] = lookup_debug
                return resolved
            if image_path and isinstance(metadata_face, dict) and not str(resolved.get("source_name") or "").strip():
                payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
                target_face = self._findFaceBySignature(payload.faces, metadata_face)
                if not target_face or str(target_face.name or "").strip():
                    resolved["matched_person"] = None
                    resolved["matched_person_id"] = None
                    resolved["lookup_debug"] = {}
                    return resolved
                source_scope = self._fileFaceMatchSourceScope()
                use_photos = source_scope in {"both", "photos"}
                use_metadata = source_scope in {"both", "metadata"}
                photo_sources: List[Dict[str, Any]] = []
                if use_photos:
                    known_persons = known_persons_cache if isinstance(known_persons_cache, list) else self.photos.sortPersonsForFaceMatch(
                        self.photos.listFotoTeamPersonKnown(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            show_more=True,
                            show_hidden=False,
                            additional=["thumbnail"],
                        )
                    )
                    shared_folder = self.core.getSharedFolder(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        folder_name="photo",
                    )
                    if shared_folder:
                        for person in known_persons:
                            person_id = person.get("id")
                            try:
                                person_id_int = int(person_id)
                            except (TypeError, ValueError):
                                continue
                            images = self.photos.listFotoTeamItems(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                person_id=person_id_int,
                                additional=["thumbnail"],
                            )
                            for image in images:
                                image_id = image.get("id")
                                folder_id = image.get("folder_id")
                                filename = image.get("filename")
                                try:
                                    image_id_int = int(image_id)
                                    folder_id_int = int(folder_id)
                                except (TypeError, ValueError):
                                    continue
                                if not isinstance(filename, str) or not filename:
                                    continue
                                folder_payload = self.photos.getFotoTeamFolder(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    id_folder=folder_id_int,
                                )
                                folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                                folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                                if not isinstance(folder_name, str) or not folder_name:
                                    continue
                                photo_image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                                if photo_image_path != image_path:
                                    continue
                                faces = self.photos.list_faceFotoTeamItems(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    id_item=image_id_int,
                                )
                                for face in faces:
                                    face_name = str(face.get("face_name") or "").strip()
                                    face_id = face.get("face_id")
                                    if not face_name or face_id is None:
                                        continue
                                    photo_face = dict(face)
                                    photo_face["image"] = image
                                    photo_face["person"] = person
                                    photo_sources.append(photo_face)
                metadata_sources = [
                    face for face in payload.faces
                    if str(face.name or "").strip()
                ] if use_metadata else []
                matched_entry = self._matchFileFaceInSources(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    image_path=image_path,
                    target_face=target_face,
                    photo_sources=photo_sources,
                    metadata_sources=metadata_sources,
                    known_persons_cache=known_persons_cache,
                )
                if isinstance(matched_entry, dict):
                    resolved.update(matched_entry)
            source_name = str(resolved.get("source_name") or "").strip()
            if not source_name:
                source_face = resolved.get("source_face")
                if isinstance(source_face, dict):
                    source_name = str(source_face.get("name") or "").strip()
            matched_person = None
            lookup_debug: Dict[str, Any] = {}
            if source_name:
                matched_person = self.photos.findKnownPersonByName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    name=source_name,
                    known_persons=known_persons_cache,
                )
                lookup_debug = self.photos.debugKnownPersonLookup(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    name=source_name,
                    known_persons=known_persons_cache,
                )
            resolved["matched_person"] = matched_person
            resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
            resolved["lookup_debug"] = lookup_debug
            return resolved

        mapped_assignment = resolved.get("name_mapping")
        mapped_target_name = ""
        if isinstance(mapped_assignment, dict):
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()

        metadata_face = resolved.get("metadata_face")
        metadata_name = ""
        if isinstance(metadata_face, dict):
            metadata_name = str(metadata_face.get("name") or "").strip()

        match = resolved.get("match")
        match_name = ""
        if isinstance(match, dict):
            match_name = str(match.get("file_name") or "").strip()

        lookup_name = mapped_target_name or metadata_name or match_name
        if not lookup_name:
            resolved["matched_person"] = None
            resolved["matched_person_id"] = None
            resolved["lookup_debug"] = {}
            return resolved

        matched_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        lookup_debug = self.photos.debugKnownPersonLookup(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        resolved["matched_person"] = matched_person
        resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
        resolved["lookup_debug"] = lookup_debug
        return resolved

    def _persistFaceMatchFindingsEntries(
        self,
        *,
        findings: Dict[str, Any],
        entries: List[Dict[str, Any]],
        transferred_count: int,
    ) -> None:
        self.face_match_workflow.persist_findings_entries(
            findings=findings,
            entries=entries,
            transferred_count=transferred_count,
        )

    def _fileFaceMatchSourceScope(self) -> str:
        config = self.config.readMergedConfig()
        face_match_config = config.get("face_match") if isinstance(config.get("face_match"), dict) else {}
        value = str(face_match_config.get("FILE_MATCH_SOURCE_SCOPE") or "both").strip().lower()
        return value if value in {"both", "photos", "metadata"} else "both"

    def _matchFileFaceInSources(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        target_face: MetadataFace,
        photo_sources: List[Dict[str, Any]],
        metadata_sources: List[MetadataFace],
        known_persons_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        target_photo_face = PhotosFace(face_id=0, person_id=0, bbox=from_xmp(target_face))
        source_candidates: List[Dict[str, Any]] = []

        photo_file_faces: List[FileFace] = []
        photo_lookup: List[Dict[str, Any]] = []
        for photo_face in photo_sources:
            face_name = str(photo_face.get("face_name") or "").strip()
            if not face_name:
                continue
            photo_file_faces.append(
                FileFace(
                    name=face_name,
                    bbox=from_photos(photo_face),
                    source="photos",
                    source_format="PHOTOS",
                )
            )
            photo_lookup.append(photo_face)
        for match in self.face_matcher.match([target_photo_face], photo_file_faces):
            matched_photo = photo_lookup[match["file_face_index"]]
            matched_bbox = from_photos(matched_photo)
            source_candidates.append({
                **match,
                "source_type": "photos",
                "source_face": to_display_face({
                    "name": str(matched_photo.get("face_name") or ""),
                    "x": (matched_bbox.x1 + matched_bbox.x2) / 2,
                    "y": (matched_bbox.y1 + matched_bbox.y2) / 2,
                    "w": matched_bbox.x2 - matched_bbox.x1,
                    "h": matched_bbox.y2 - matched_bbox.y1,
                    "source": "photos",
                    "source_format": "PHOTOS",
                }),
                "matched_person": matched_photo.get("person"),
                "image": matched_photo.get("image"),
            })

        metadata_file_faces: List[FileFace] = []
        metadata_lookup: List[MetadataFace] = []
        for metadata_face in metadata_sources:
            if self._sameMetadataFaceCandidate(metadata_face, target_face):
                continue
            metadata_file_faces.append(
                FileFace(
                    name=str(metadata_face.name or ""),
                    bbox=from_xmp(metadata_face),
                    source=metadata_face.source,
                    source_format=metadata_face.source_format,
                )
            )
            metadata_lookup.append(metadata_face)
        for match in self.face_matcher.match([target_photo_face], metadata_file_faces):
            matched_metadata = metadata_lookup[match["file_face_index"]]
            source_candidates.append({
                **match,
                "source_type": "metadata",
                "source_face": to_display_face(matched_metadata),
                "matched_person": None,
                "image": None,
            })

        if not source_candidates:
            return None

        matched = max(source_candidates, key=self._preferredFaceMatchCandidate)
        source_face = matched.get("source_face") if isinstance(matched.get("source_face"), dict) else None
        source_name = str((source_face or {}).get("name") or matched.get("file_name") or "").strip()
        if not source_name:
            return None

        matched_person = matched.get("matched_person") if isinstance(matched.get("matched_person"), dict) else None
        if (
            isinstance(matched_person, dict)
            and self.photos._normalize_person_name(matched_person.get("name")) != self.photos._normalize_person_name(source_name)
        ):
            self._debugLog(
                "face_match_source_person_mismatch_ignored",
                image_path=image_path,
                source_name=source_name,
                matched_person_id=matched_person.get("id"),
                matched_person_name=matched_person.get("name"),
                source_type=str(matched.get("source_type") or ""),
            )
            matched_person = None
        if matched_person is None:
            matched_person = self.photos.findKnownPersonByName(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                name=source_name,
                known_persons=known_persons_cache,
            )

        return {
            "action": "search_file_face_in_sources",
            "searched": True,
            "person": matched_person if isinstance(matched_person, dict) else None,
            "image": matched.get("image") if isinstance(matched.get("image"), dict) else None,
            "face": source_face,
            "source_face": source_face,
            "source_name": source_name,
            "source_type": str(matched.get("source_type") or ""),
            "metadata_face": to_display_face(target_face),
            "image_path": image_path,
            "match": matched,
            "matched_person": matched_person,
            "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
        }

    def _lookupMatchedPersonBySourceName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        source_name: str,
        known_persons_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
        normalized_source_name = str(source_name or "").strip()
        if not normalized_source_name:
            return None, None, {}

        mapped_assignment = self.name_mappings.findNameMapping(normalized_source_name)
        lookup_name = normalized_source_name
        if mapped_assignment:
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
            if mapped_target_name:
                lookup_name = mapped_target_name

        matched_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        lookup_debug = self.photos.debugKnownPersonLookup(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        return matched_person, mapped_assignment, lookup_debug

    @staticmethod
    def _faceMatchTargetToken(*, image_path: str, face: Any) -> str:
        payload = face.to_dict() if hasattr(face, "to_dict") else (dict(face) if isinstance(face, dict) else {})
        return "|".join([
            str(image_path or "").strip(),
            str(payload.get("source_format") or "").strip().upper(),
            format_face_coordinate(payload.get("x")),
            format_face_coordinate(payload.get("y")),
            format_face_coordinate(payload.get("w")),
            format_face_coordinate(payload.get("h")),
        ])

    @staticmethod
    def _insightFaceDetectionToMetadataFace(detection: Dict[str, Any]) -> Optional[MetadataFace]:
        if not isinstance(detection, dict):
            return None
        bbox = detection.get("bbox") if isinstance(detection.get("bbox"), dict) else {}
        center = detection.get("center") if isinstance(detection.get("center"), dict) else {}
        x1 = bbox.get("x1")
        y1 = bbox.get("y1")
        x2 = bbox.get("x2")
        y2 = bbox.get("y2")
        center_x = center.get("x")
        center_y = center.get("y")
        try:
            x1 = float(x1)
            y1 = float(y1)
            x2 = float(x2)
            y2 = float(y2)
            center_x = float(center_x)
            center_y = float(center_y)
        except (TypeError, ValueError):
            return None
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            return None
        return MetadataFace.from_center_box(
            name="",
            x=max(0.0, min(1.0, center_x)),
            y=max(0.0, min(1.0, center_y)),
            w=max(0.0, min(1.0, width)),
            h=max(0.0, min(1.0, height)),
            source="insightface",
            source_format="INSIGHTFACE",
        )

    def _selectMissingPhotosFaceCandidate(
        self,
        *,
        candidate_faces: List[MetadataFace],
        existing_photos_faces: List[Dict[str, Any]],
        require_name: bool,
    ) -> Tuple[Optional[MetadataFace], Dict[str, int]]:
        faces_by_format: Dict[str, int] = {}
        for candidate_face in candidate_faces:
            source_format = str(candidate_face.source_format or "").strip().upper()
            if source_format:
                faces_by_format[source_format] = faces_by_format.get(source_format, 0) + 1
            if require_name and not str(candidate_face.name or "").strip():
                continue
            if self._findExistingPhotosFaceMatch(
                metadata_face=candidate_face,
                existing_faces=existing_photos_faces,
            ) is not None:
                continue
            return candidate_face, faces_by_format
        return None, faces_by_format

    @staticmethod
    def _preferredFaceMatchCandidate(candidate: Dict[str, Any]) -> Tuple[float, int]:
        source_type = str(candidate.get("source_type") or "").strip().lower()
        return (
            float(candidate.get("iou") or 0),
            1 if source_type == "photos" else 0,
        )

    def _storedFaceMatchEntryExists(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        entry: Dict[str, Any],
        image_faces_cache: Dict[int, List[Dict[str, Any]]],
        photos_lookup_cache: Optional[PhotosLookupCache] = None,
    ) -> bool:
        if not isinstance(entry, dict):
            return False
        action = str(entry.get("action") or "search_photo_face_in_file").strip().lower()
        if action == "search_file_face_in_sources":
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                return False
            payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
            existing = self._findFaceBySignature(payload.faces, metadata_face)
            return bool(existing and not str(existing.name or "").strip())
        if action == "search_missing_faces_insightface":
            image = entry.get("image")
            metadata_face = entry.get("metadata_face")
            if not isinstance(image, dict) or not isinstance(metadata_face, dict):
                return True
            try:
                image_id = int(image.get("id"))
            except (TypeError, ValueError):
                return True
            if image_id not in image_faces_cache:
                image_faces_cache[image_id] = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=image_id,
                )
            return self._findExistingPhotosFaceMatch(
                metadata_face=MetadataFace.from_dict(metadata_face),
                existing_faces=image_faces_cache[image_id],
            ) is None
        if action == "mark_missing_photos_faces":
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                return False
            payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
            existing = self._findFaceBySignature(payload.faces, metadata_face)
            if not existing or not str(existing.name or "").strip():
                return False

            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                return True
            item = self.photos.findFotoTeamItemByPath(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
                additional=["thumbnail"],
                lookup_cache=photos_lookup_cache,
            )
            item_id = item.get("id") if isinstance(item, dict) else None
            try:
                item_id_int = int(item_id)
            except (TypeError, ValueError):
                return True
            if item_id_int not in image_faces_cache:
                image_faces_cache[item_id_int] = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=item_id_int,
                )
            return self._findExistingPhotosFaceMatch(
                metadata_face=existing,
                existing_faces=image_faces_cache[item_id_int],
            ) is None
        image = entry.get("image")
        face = entry.get("face")
        if not isinstance(image, dict) or not isinstance(face, dict):
            return False
        try:
            image_id = int(image.get("id"))
            face_id = int(face.get("face_id"))
        except (TypeError, ValueError):
            return False

        if image_id not in image_faces_cache:
            try:
                image_faces_cache[image_id] = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=image_id,
                )
            except SessionManagerError:
                image_path = str(entry.get("image_path") or "").strip()
                shared_folder = self.core.getSharedFolder(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    folder_name="photo",
                )
                refreshed_item = self.photos.findFotoTeamItemByPath(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder or "",
                    image_path=image_path,
                    additional=["thumbnail"],
                    lookup_cache=None,
                ) if shared_folder and image_path else None
                try:
                    refreshed_image_id = int(refreshed_item.get("id")) if isinstance(refreshed_item, dict) else None
                except (TypeError, ValueError):
                    refreshed_image_id = None
                if refreshed_image_id is None or refreshed_image_id == image_id:
                    raise
                self._debugLog(
                    "face_match_findings_item_remapped",
                    action=action,
                    image_path=image_path,
                    previous_item_id=image_id,
                    refreshed_item_id=refreshed_image_id,
                    face_id=face_id,
                )
                image_id = refreshed_image_id
                entry["image"] = {
                    **image,
                    **refreshed_item,
                }
                image_faces_cache[image_id] = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=image_id,
                )

        face["item_id"] = image_id
        entry["face"] = face

        for image_face in image_faces_cache[image_id]:
            try:
                if int(image_face.get("face_id")) == face_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _pickReviewFace(faces: List[MetadataFace]) -> Optional[MetadataFace]:
        if not isinstance(faces, list):
            return None
        mwg_faces = [face for face in faces if isinstance(face, MetadataFace) and face.source_format == "MWG_REGIONS"]
        if not mwg_faces:
            return None
        named = [face for face in mwg_faces if str(face.name or "").strip()]
        return named[0] if named else mwg_faces[0]

    @staticmethod
    def _isSameFace(left: Any, right: Any) -> bool:
        if isinstance(left, MetadataFace):
            left = left.to_dict()
        if isinstance(right, MetadataFace):
            right = right.to_dict()
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        left_face_id = left.get("face_id")
        right_face_id = right.get("face_id")
        if left_face_id not in (None, "") and right_face_id not in (None, ""):
            try:
                return int(left_face_id) == int(right_face_id)
            except (TypeError, ValueError):
                return False
        keys = ("source_format", "source", "name", "x", "y", "w", "h", "orientation")
        return all(left.get(key) == right.get(key) for key in keys)

    @staticmethod
    def _faceSignature(face: Any) -> Dict[str, Any]:
        if isinstance(face, MetadataFace):
            payload = face.to_dict()
            for key in ("face_id", "person_id"):
                value = getattr(face, key, None)
                if value not in (None, ""):
                    payload[key] = value
            face = payload
        if not isinstance(face, dict):
            return {}
        payload = {
            "source_format": face.get("source_format"),
            "source": face.get("source"),
            "name": face.get("name"),
            "x": face.get("x"),
            "y": face.get("y"),
            "w": face.get("w"),
            "h": face.get("h"),
            "orientation": face.get("orientation"),
        }
        for key in ("face_id", "person_id"):
            value = face.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    def _findFaceBySignature(self, faces: List[MetadataFace], signature: Dict[str, Any]) -> Optional[MetadataFace]:
        if not isinstance(signature, dict):
            return None
        for face in faces:
            if self._isSameFace(face, signature):
                return face
        return None

    @staticmethod
    def _isChecksFacePairType(review_type: Any) -> bool:
        normalized_type = str(review_type or "").strip().lower()
        return normalized_type in {"name_conflicts", "duplicate_faces", "position_deviations"}

    @staticmethod
    def _isChecksIgnoreSupportedType(review_type: Any) -> bool:
        normalized_type = str(review_type or "").strip().lower()
        return normalized_type in {"name_conflicts", "duplicate_faces", "position_deviations"}

    @staticmethod
    def _faceIdentitySignature(face: Any) -> Dict[str, Any]:
        signature = ImgDataService._faceSignature(face)
        if not isinstance(signature, dict):
            return {}
        normalized: Dict[str, Any] = {}
        source_format = str(signature.get("source_format") or "").strip().upper()
        if source_format:
            normalized["source_format"] = source_format
        for key in ("x", "y", "w", "h"):
            value = signature.get(key)
            if value in (None, ""):
                continue
            try:
                normalized[key] = round_face_coordinate(value)
            except (TypeError, ValueError):
                normalized[key] = value
        orientation = signature.get("orientation")
        if orientation not in (None, ""):
            try:
                normalized["orientation"] = int(orientation)
            except (TypeError, ValueError):
                normalized["orientation"] = orientation
        for key in ("face_id", "person_id"):
            value = signature.get(key)
            if value not in (None, ""):
                normalized[key] = value
        return normalized

    @staticmethod
    def _faceIdentityToken(face: Any) -> str:
        signature = ImgDataService._faceIdentitySignature(face)
        if not signature:
            return ""
        return json.dumps(signature, sort_keys=True, ensure_ascii=True)

    def _checksConflictToken(self, entry: Any) -> str:
        if not isinstance(entry, dict):
            return ""
        left_token = self._faceIdentityToken(entry.get("left_face_signature"))
        right_token = self._faceIdentityToken(entry.get("right_face_signature"))
        if not left_token or not right_token:
            return ""
        return json.dumps(
            {
                "review_type": str(entry.get("review_type") or "").strip().lower(),
                "image_path": str(entry.get("image_path") or "").strip(),
                "pair": sorted([left_token, right_token]),
            },
            sort_keys=True,
            ensure_ascii=True,
        )

    def _checksEntryToken(self, entry: Any) -> str:
        if not isinstance(entry, dict):
            return ""
        review_type = str(entry.get("review_type") or "").strip().lower()
        if self._isChecksFacePairType(review_type):
            return self._checksConflictToken(entry)
        entry_id = str(entry.get("entry_id") or "").strip()
        image_path = str(entry.get("image_path") or "").strip()
        if entry_id:
            return json.dumps(
                {
                    "review_type": review_type,
                    "image_path": image_path,
                    "entry_id": entry_id,
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        if review_type and image_path:
            return json.dumps(
                {
                    "review_type": review_type,
                    "image_path": image_path,
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        return ""

    def _checksIgnoreListConfigKey(self, review_type: Any) -> str:
        normalized_type = str(review_type or "").strip().lower()
        return ConfigService.checksIgnoreEnabledKey(normalized_type)

    def _configuredChecksIgnoreSettings(self) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        review = config.get("review") if isinstance(config.get("review"), dict) else {}
        ignore_lists = review.get("CHECKS_IGNORE_LISTS") if isinstance(review.get("CHECKS_IGNORE_LISTS"), dict) else {}
        defaults = ConfigService.defaultConfig()["review"]["CHECKS_IGNORE_LISTS"]
        return {
            "DUPLICATE_FACES_ENABLED": bool(ignore_lists.get("DUPLICATE_FACES_ENABLED", defaults["DUPLICATE_FACES_ENABLED"])),
            "POSITION_DEVIATIONS_ENABLED": bool(ignore_lists.get("POSITION_DEVIATIONS_ENABLED", defaults["POSITION_DEVIATIONS_ENABLED"])),
            "NAME_CONFLICTS_ENABLED": bool(ignore_lists.get("NAME_CONFLICTS_ENABLED", defaults["NAME_CONFLICTS_ENABLED"])),
        }

    def _configuredChecksIgnoreTokens(self, review_type: Any) -> List[str]:
        normalized_type = str(review_type or "").strip().lower()
        if not self._isChecksIgnoreSupportedType(normalized_type):
            return []
        key = self._checksIgnoreListConfigKey(normalized_type)
        if not key:
            return []
        ignore_settings = self._configuredChecksIgnoreSettings()
        if not ignore_settings.get(key, True):
            return []
        legacy_tokens = self.config.readChecksIgnoreList(normalized_type)
        prefix = f"checks:{normalized_type}:"
        sql_tokens = [
            suppression_key[len(prefix):]
            for suppression_key in self.face_suppressions.list_keys(prefix)
            if suppression_key.startswith(prefix)
        ]
        return list(dict.fromkeys([*legacy_tokens, *sql_tokens]))

    def _excludeIgnoredChecksEntries(
        self,
        review_type: Any,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self._excludeChecksEntriesByTokens(entries, self._configuredChecksIgnoreTokens(review_type))

    def ignoreChecksEntry(self, *, entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized_entry = dict(entry or {})
        review_type = str(normalized_entry.get("review_type") or "").strip().lower()
        if not self._isChecksIgnoreSupportedType(review_type):
            return {"ignored": False, "reason": "unsupported_review_type"}

        token = self._checksEntryToken(normalized_entry)
        if not token:
            return {"ignored": False, "reason": "missing_entry_token"}

        key = self._checksIgnoreListConfigKey(review_type)
        ignore_settings = self._configuredChecksIgnoreSettings()
        if key and not ignore_settings.get(key, True):
            return {"ignored": False, "reason": "ignore_list_disabled"}
        saved_result = self.config.appendChecksIgnoreToken(review_type, token)
        sql_saved = self.face_suppressions.suppress(
            f"checks:{review_type}:{token}",
            "manual",
            scope="candidate",
            reason=f"Ignored {review_type} review entry",
        )
        return {
            "ignored": bool(saved_result.get("saved")) and sql_saved,
            "token": str(saved_result.get("token") or token),
            "review_type": review_type,
            "count": int(saved_result.get("count") or 0),
        }

    def clearChecksIgnoreList(self, review_type: Any) -> bool:
        normalized_type = str(review_type or "").strip().lower()
        cleared = self.config.clearChecksIgnoreList(normalized_type)
        if cleared:
            self.face_suppressions.disable_prefix(f"checks:{normalized_type}:")
        return cleared

    def getChecksIgnoreListsStatus(self) -> Dict[str, Dict[str, Any]]:
        statuses = self.config.getChecksIgnoreListsStatus()
        settings = self._configuredChecksIgnoreSettings()
        for review_type in list(statuses.keys()):
            enabled_key = self._checksIgnoreListConfigKey(review_type)
            statuses[review_type] = {
                **statuses[review_type],
                "enabled": bool(settings.get(enabled_key, True)),
            }
        return statuses

    def _excludeChecksEntriesByTokens(
        self,
        entries: List[Dict[str, Any]],
        excluded_tokens: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self.checks_workflow.exclude_checks_entries_by_tokens(entries, excluded_tokens)

    def _rebuildChecksEntriesForImageAfterMutation(
        self,
        *,
        image_path: str,
        review_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        excluded_tokens: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self.checks_workflow.rebuild_checks_entries_for_image_after_mutation(
            image_path=image_path,
            review_type=review_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            excluded_tokens=excluded_tokens,
        )

    def _buildCheckEntry(
        self,
        *,
        review_type: str,
        image_path: str,
        face_name: str = "",
        left_face: Optional[MetadataFace] = None,
        right_face: Optional[MetadataFace] = None,
    ) -> Dict[str, Any]:
        return {
            "review_type": review_type,
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": face_name,
            "left_face_signature": self._faceSignature(left_face or {}),
            "right_face_signature": self._faceSignature(right_face or {}),
        }

    @staticmethod
    def _hasFaceSignature(signature: Any) -> bool:
        return isinstance(signature, dict) and any(bool(signature.get(key)) for key in ("name", "source", "source_format", "bbox"))

    def _buildDimensionMismatchReviewEntry(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        if analysis.get("files_with_mwg_dimension_mismatch") != 1:
            return None

        mwg_faces = [face for face in payload.faces if face.source_format == "MWG_REGIONS"]
        if not mwg_faces:
            return None

        review_face = self._pickReviewFace(mwg_faces) or mwg_faces[0]
        return self._buildCheckEntry(
            review_type="dimension_issues",
            image_path=image_path,
            face_name=str(review_face.name or ""),
            left_face=review_face,
        )

    def _buildDimensionMismatchReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        if analysis.get("files_with_mwg_dimension_mismatch") != 1:
            return None

        mwg_faces = [face for face in payload.faces if face.source_format == "MWG_REGIONS"]
        reference_faces = [face for face in payload.faces if face.source_format != "MWG_REGIONS"]
        if not mwg_faces:
            return None

        review_face = self._findFaceBySignature(mwg_faces, (entry or {}).get("left_face_signature") or {})
        review_face = review_face or self._pickReviewFace(mwg_faces) or mwg_faces[0]
        applied_face = to_display_face(review_face)
        reference_face = self._findBestReferenceFace(review_face, reference_faces) or review_face

        return {
            "review_type": "dimension_issues",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "left_face": applied_face,
            "left_face_target": self._faceSignature(review_face),
            "right_face": to_display_face(reference_face),
            "right_face_target": self._faceSignature(reference_face),
            "left_alert_faces": [
                to_display_face(face) for face in mwg_faces
                if not self._isSameFace(face, review_face)
            ],
            "left_reference_faces": [to_display_face(face) for face in reference_faces],
            "right_alert_faces": [],
            "right_reference_faces": [],
            "face_name": str(review_face.name or ""),
            "left_name": str(review_face.name or ""),
            "right_name": str(reference_face.name or ""),
            "left_format": str(review_face.source_format or ""),
            "right_format": str(reference_face.source_format or ""),
            "image_dimensions": analysis.get("image_dimensions") if isinstance(analysis.get("image_dimensions"), dict) else {},
            "applied_to_dimensions": analysis.get("mwg_applied_to_dimensions") if isinstance(analysis.get("mwg_applied_to_dimensions"), dict) else {},
            "image_orientation": analysis.get("image_orientation"),
            "mwg_applied_to_dimensions_matches_current": analysis.get("mwg_applied_to_dimensions_matches_current"),
        }

    def _findBestReferenceFace(self, review_face: MetadataFace, candidates: List[MetadataFace]) -> Optional[MetadataFace]:
        review_name = str(review_face.name or "").strip().casefold()
        prioritized_candidates = candidates
        if review_name:
            same_name = [face for face in candidates if str(face.name or "").strip().casefold() == review_name]
            if same_name:
                prioritized_candidates = same_name

        for preferred_format in ("ACD", "PHOTOS", "MICROSOFT"):
            for face in prioritized_candidates:
                if str(face.source_format or "").strip().upper() == preferred_format:
                    return face
        return prioritized_candidates[0] if prioritized_candidates else None

    def _configuredReviewOptions(self) -> Dict[str, bool]:
        config = self.config.readMergedConfig()
        review_config = config.get("review") if isinstance(config.get("review"), dict) else {}
        review_options = review_config.get("OPTIONS") if isinstance(review_config.get("OPTIONS"), dict) else {}
        legacy_analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        legacy_checks = legacy_analysis.get("CHECKS") if isinstance(legacy_analysis.get("CHECKS"), dict) else {}
        default_options = ConfigService.defaultConfig()["review"]["OPTIONS"]
        return {
            "DUPLICATE_FACE_SUGGESTIONS": bool(
                review_options.get(
                    "DUPLICATE_FACE_SUGGESTIONS",
                    legacy_checks.get("DUPLICATE_FACE_SUGGESTIONS", default_options["DUPLICATE_FACE_SUGGESTIONS"]),
                )
            ),
        }

    def _buildDuplicateFaceReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        grouped: Dict[tuple, List[MetadataFace]] = {}
        for face in payload.faces:
            name = str(face.name or "").strip()
            source_format = str(face.source_format or "").strip()
            if not name or not source_format:
                continue
            grouped.setdefault((source_format, name.casefold()), []).append(face)

        entries: List[Dict[str, Any]] = []
        for (_, _), grouped_faces in grouped.items():
            self._raiseIfChecksStopRequested()
            if len(grouped_faces) < 2:
                continue
            for index in range(len(grouped_faces) - 1):
                self._raiseIfChecksStopRequested()
                left = grouped_faces[index]
                right = grouped_faces[index + 1]
                entries.append(
                    self._buildCheckEntry(
                        review_type="duplicate_faces",
                        image_path=image_path,
                        face_name=str(left.name or ""),
                        left_face=left,
                        right_face=right,
                    )
                )
        return entries

    def _buildDuplicateFaceReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        review_options = self._configuredReviewOptions()
        faces = payload.faces
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None

        left_state = "alert"
        right_state = "alert"
        if review_options.get("DUPLICATE_FACE_SUGGESTIONS", True):
            left_state, right_state = self._getDuplicateSuggestionStates(
                left_face=left,
                right_face=right,
                faces=faces,
            )
        left_state, right_state = self._applySingleSourceOfTruthSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )
        left_state, right_state = self._applyOrientationRiskSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )

        return {
            "review_type": "duplicate_faces",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _getDuplicateSuggestionStates(
        self,
        *,
        left_face: MetadataFace,
        right_face: MetadataFace,
        faces: List[MetadataFace],
    ) -> Tuple[str, str]:
        left_state = "alert"
        right_state = "alert"

        containment = self._duplicateContainmentSuggestion(left_face, right_face)
        if containment == "left":
            return "suggested", right_state
        if containment == "right":
            return left_state, "suggested"

        left_matches, left_safe_matches = self._duplicateSuggestionSupportStats(left_face, faces)
        right_matches, right_safe_matches = self._duplicateSuggestionSupportStats(right_face, faces)
        if left_matches > right_matches:
            return "suggested", right_state
        if right_matches > left_matches:
            return left_state, "suggested"
        if left_safe_matches > right_safe_matches:
            return "suggested", right_state
        if right_safe_matches > left_safe_matches:
            return left_state, "suggested"
        return left_state, right_state

    def _duplicateSuggestionSupportStats(self, candidate: MetadataFace, faces: List[MetadataFace]) -> Tuple[int, int]:
        candidate_name = str(candidate.name or "").strip().casefold()
        candidate_format = str(candidate.source_format or "").strip().upper()
        if not candidate_name or not candidate_format:
            return 0, 0

        normalized_candidate = to_display_face(candidate)
        matches = 0
        safe_matches = 0
        for face in faces:
            face_name = str(face.name or "").strip().casefold()
            face_format = str(face.source_format or "").strip().upper()
            if face_name != candidate_name or face_format == candidate_format:
                continue
            normalized_face = to_display_face(face)
            if self.files._boxesOverlapStrongly(normalized_candidate, normalized_face):
                matches += 1
                if not self._faceHasOrientationRisk(face):
                    safe_matches += 1
        return matches, safe_matches

    def _duplicateContainmentSuggestion(
        self,
        left_face: MetadataFace,
        right_face: MetadataFace,
    ) -> str:
        left_bbox = from_xmp(left_face)
        right_bbox = from_xmp(right_face)
        if self._boundingBoxContains(left_bbox, right_bbox) and left_bbox.area() > right_bbox.area():
            return "left"
        if self._boundingBoxContains(right_bbox, left_bbox) and right_bbox.area() > left_bbox.area():
            return "right"
        return ""

    @staticmethod
    def _boundingBoxContains(container: Any, inner: Any, *, epsilon: float = 1e-9) -> bool:
        try:
            return (
                float(container.x1) <= float(inner.x1) + epsilon and
                float(container.y1) <= float(inner.y1) + epsilon and
                float(container.x2) >= float(inner.x2) - epsilon and
                float(container.y2) >= float(inner.y2) - epsilon
            )
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _faceHasOrientationRisk(face: Optional[MetadataFace]) -> bool:
        if not isinstance(face, MetadataFace):
            return False
        source_format = str(face.source_format or "").strip().upper()
        if source_format not in {"MWG_REGIONS", "MICROSOFT"}:
            return False
        return face.orientation not in (None, 1)

    def _applyOrientationRiskSuggestion(
        self,
        *,
        left_state: str,
        right_state: str,
        left_face: Optional[MetadataFace],
        right_face: Optional[MetadataFace],
    ) -> Tuple[str, str]:
        if left_state == "suggested" or right_state == "suggested":
            return left_state, right_state

        left_risk = self._faceHasOrientationRisk(left_face)
        right_risk = self._faceHasOrientationRisk(right_face)
        if left_risk == right_risk:
            return left_state, right_state
        if left_risk:
            return left_state, "suggested"
        return "suggested", right_state

    @staticmethod
    def _faceMatchesSingleSourceOfTruth(face: Optional[MetadataFace], source_of_truth: str) -> bool:
        if not isinstance(face, MetadataFace) or not source_of_truth:
            return False
        if source_of_truth == "photos":
            return str(face.source_format or "").strip().upper() == "PHOTOS"
        parts = source_of_truth.split(":")
        if len(parts) != 3 or parts[0] != "metadata":
            return False
        requested_format = parts[1]
        requested_location = parts[2]
        face_format = str(face.source_format or "").strip().lower()
        if face_format == "photos":
            return False
        source = str(face.source or "").strip().lower()
        face_location = "sidecar" if source == "xmp_file" else "embedded"
        format_matches = requested_format == "any" or face_format == requested_format
        location_matches = requested_location == "any" or face_location == requested_location
        return format_matches and location_matches

    def _applySingleSourceOfTruthSuggestion(
        self,
        *,
        left_state: str,
        right_state: str,
        left_face: Optional[MetadataFace],
        right_face: Optional[MetadataFace],
    ) -> Tuple[str, str]:
        source_of_truth = str(self._configuredAnalysisChecks().get("SINGLE_SOURCE_OF_TRUTH") or "").strip().lower()
        if not source_of_truth:
            return left_state, right_state

        left_matches = self._faceMatchesSingleSourceOfTruth(left_face, source_of_truth)
        right_matches = self._faceMatchesSingleSourceOfTruth(right_face, source_of_truth)
        if left_matches == right_matches:
            return left_state, right_state
        if left_matches:
            return "suggested", "alert"
        return "alert", "suggested"

    def _getNameConflictSuggestionStates(
        self,
        left_name: str,
        right_name: str,
        *,
        left_face: Optional[MetadataFace] = None,
        right_face: Optional[MetadataFace] = None,
    ) -> Tuple[str, str]:
        left_state = "alert"
        right_state = "alert"

        normalized_left = self.name_mappings._normalize_name_value(left_name)
        normalized_right = self.name_mappings._normalize_name_value(right_name)
        if not normalized_left or not normalized_right:
            return self._applySingleSourceOfTruthSuggestion(
                left_state=left_state,
                right_state=right_state,
                left_face=left_face,
                right_face=right_face,
            )

        left_mapping = self.name_mappings.findNameMapping(left_name)
        if left_mapping and self.name_mappings._normalize_name_value(left_mapping.get("target_name")) == normalized_right:
            right_state = "suggested"
            return self._applySingleSourceOfTruthSuggestion(
                left_state=left_state,
                right_state=right_state,
                left_face=left_face,
                right_face=right_face,
            )

        right_mapping = self.name_mappings.findNameMapping(right_name)
        if right_mapping and self.name_mappings._normalize_name_value(right_mapping.get("target_name")) == normalized_left:
            left_state = "suggested"

        return self._applySingleSourceOfTruthSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left_face,
            right_face=right_face,
        )

    @staticmethod
    def _metadataFaceFromPhotoFace(face: Dict[str, Any]) -> Optional[MetadataFace]:
        if not isinstance(face, dict):
            return None
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
        top_left = bbox.get("top_left") if isinstance(bbox.get("top_left"), dict) else {}
        bottom_right = bbox.get("bottom_right") if isinstance(bbox.get("bottom_right"), dict) else {}
        try:
            left = float(top_left.get("x"))
            top = float(top_left.get("y"))
            right = float(bottom_right.get("x"))
            bottom = float(bottom_right.get("y"))
        except (TypeError, ValueError):
            return None
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        normalized_face = MetadataFace.from_center_box(
            name=str(face.get("face_name") or ""),
            x=left + (width / 2),
            y=top + (height / 2),
            w=width,
            h=height,
            source="photos",
            source_format="PHOTOS",
        )
        for key in ("face_id", "person_id"):
            value = face.get(key)
            if value not in (None, ""):
                setattr(normalized_face, key, value)
        return normalized_face

    def _loadPhotoFacesForImage(
        self,
        *,
        user_key: Optional[str],
        cookies: Optional[Dict[str, str]],
        base_url: str,
        shared_folder: str,
        image_path: str,
        photos_lookup_cache: Optional[PhotosLookupCache] = None,
    ) -> List[MetadataFace]:
        normalized_path = str(image_path or "").strip()
        if not user_key or not isinstance(cookies, dict) or not base_url or not normalized_path:
            return []
        resolved_shared_folder = str(shared_folder or "").strip()
        if not resolved_shared_folder:
            resolved_shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
        if not resolved_shared_folder:
            return []
        try:
            item = self.photos.findFotoTeamItemByPath(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=resolved_shared_folder,
                image_path=normalized_path,
                additional=["thumbnail"],
                lookup_cache=photos_lookup_cache,
            )
            item_id = item.get("id") if isinstance(item, dict) else None
            item_id_int = int(item_id)
        except (TypeError, ValueError):
            return []
        except Exception:
            return []

        try:
            raw_faces = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id_int,
            )
        except Exception:
            return []

        normalized_faces: List[MetadataFace] = []
        for face in raw_faces:
            mapped = self._metadataFaceFromPhotoFace(face)
            if mapped is not None:
                setattr(mapped, "item_id", item_id_int)
                normalized_faces.append(mapped)
        return normalized_faces

    def _loadPhotoFacesForImageWithOverride(
        self,
        *,
        user_key: Optional[str],
        cookies: Optional[Dict[str, str]],
        base_url: str,
        shared_folder: str,
        image_path: str,
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[MetadataFace]]:
        if not original_face_data or not replacement_face_data:
            return None
        if str(original_face_data.get("source_format") or "").strip().upper() != "PHOTOS":
            return None

        photo_faces = self._loadPhotoFacesForImage(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=image_path,
        )
        replacement_face = MetadataFace.from_dict(replacement_face_data)
        for key in ("face_id", "person_id"):
            value = replacement_face_data.get(key)
            if value not in (None, ""):
                setattr(replacement_face, key, value)

        original_signature = self._faceSignature(original_face_data)
        index_to_replace = None
        for index, face in enumerate(photo_faces):
            if self._isSameFace(face, original_signature):
                index_to_replace = index
                break
            face_signature = self._faceSignature(face)
            geometry_keys = ("source_format", "source", "x", "y", "w", "h", "orientation")
            if all(face_signature.get(key) == original_signature.get(key) for key in geometry_keys):
                index_to_replace = index
                break

        if index_to_replace is None:
            photo_faces.append(replacement_face)
        else:
            photo_faces[index_to_replace] = replacement_face
        return photo_faces

    def _buildPositionDeviationReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        entries: List[Dict[str, Any]] = []
        for index, left in enumerate(faces):
            self._raiseIfChecksStopRequested()
            left_name = str(left.name or "").strip().casefold()
            left_format = str(left.source_format or "").strip().upper()
            if not left_name or not left_format:
                continue
            normalized_left = to_display_face(left)
            for right in faces[index + 1:]:
                self._raiseIfChecksStopRequested()
                right_name = str(right.name or "").strip().casefold()
                right_format = str(right.source_format or "").strip().upper()
                if left_name != right_name or left_format == right_format:
                    continue
                normalized_right = to_display_face(right)
                if self.files._boxesOverlapStrongly(normalized_left, normalized_right):
                    continue
                entries.append(
                    self._buildCheckEntry(
                        review_type="position_deviations",
                        image_path=image_path,
                        face_name=str(left.name or ""),
                        left_face=left,
                        right_face=right,
                    )
                )
        return entries

    def _buildPositionDeviationReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        left_state, right_state = self._applySingleSourceOfTruthSuggestion(
            left_state="alert",
            right_state="alert",
            left_face=left,
            right_face=right,
        )
        return {
            "review_type": "position_deviations",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _buildNameConflictReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        analysis_checks = self._configuredAnalysisChecks()
        overlap_threshold = float(analysis_checks.get("NAME_CONFLICT_OVERLAP_THRESHOLD", 0.75))
        require_mutual_best_match = bool(analysis_checks.get("NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH", True))
        min_best_match_margin = float(analysis_checks.get("NAME_CONFLICT_MIN_BEST_MATCH_MARGIN", 0.05))
        normalized_faces = [to_display_face(face) for face in faces]
        best_matches: Dict[int, Tuple[int, float, float]] = {}
        if require_mutual_best_match:
            for index, left in enumerate(faces):
                self._raiseIfChecksStopRequested()
                left_name = str(left.name or "").strip()
                left_format = str(left.source_format or "").strip().upper()
                if not left_name or not left_format:
                    continue
                scored: List[Tuple[int, float]] = []
                for other_index, right in enumerate(faces):
                    self._raiseIfChecksStopRequested()
                    if index == other_index:
                        continue
                    right_name = str(right.name or "").strip()
                    right_format = str(right.source_format or "").strip().upper()
                    if not right_name or not right_format or left_format == right_format:
                        continue
                    score = self.files._faceOverlapScore(normalized_faces[index], normalized_faces[other_index])
                    if score > 0:
                        scored.append((other_index, score))
                scored.sort(key=lambda item: item[1], reverse=True)
                if scored:
                    best_score = scored[0][1]
                    second_score = scored[1][1] if len(scored) > 1 else 0.0
                    best_matches[index] = (scored[0][0], best_score, best_score - second_score)

        entries: List[Dict[str, Any]] = []
        seen_tokens = set()
        for index, left in enumerate(faces):
            self._raiseIfChecksStopRequested()
            left_name = str(left.name or "").strip()
            if not left_name:
                continue
            for other_index, right in enumerate(faces[index + 1:], start=index + 1):
                self._raiseIfChecksStopRequested()
                right_name = str(right.name or "").strip()
                if not right_name or left_name.casefold() == right_name.casefold():
                    continue
                score = self.files._faceOverlapScore(normalized_faces[index], normalized_faces[other_index])
                if score < overlap_threshold:
                    continue
                if require_mutual_best_match:
                    left_best = best_matches.get(index)
                    right_best = best_matches.get(other_index)
                    if not left_best or not right_best:
                        continue
                    if left_best[0] != other_index or right_best[0] != index:
                        continue
                    if left_best[2] < min_best_match_margin or right_best[2] < min_best_match_margin:
                        continue
                entry = self._buildCheckEntry(
                    review_type="name_conflicts",
                    image_path=image_path,
                    face_name=left_name,
                    left_face=left,
                    right_face=right,
                )
                token = self._checksEntryToken(entry)
                if token and token in seen_tokens:
                    continue
                if token:
                    seen_tokens.add(token)
                entries.append(entry)
        return entries

    def _buildNameConflictReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        left_name = str(left.name or "")
        right_name = str(right.name or "")
        left_state, right_state = self._getNameConflictSuggestionStates(
            left_name,
            right_name,
            left_face=left,
            right_face=right,
        )
        left_state, right_state = self._applyOrientationRiskSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )
        return {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": left_name,
            "left_name": left_name,
            "right_name": right_name,
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def searchNextChecksItem(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        changed_since_days: int = 0,
    ) -> Dict[str, Any]:
        return self.checks_workflow.search_next_item(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            check_type=check_type,
            save_only=save_only,
            resume_cursor=resume_cursor,
            auto_apply_suggested_names=auto_apply_suggested_names,
            auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
            changed_since_days=changed_since_days,
        )

    def getChecksReviewItem(
        self,
        *,
        entry: Dict[str, Any],
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Optional[Dict[str, Any]]:
        image_path = str(entry.get("image_path") or "").strip()
        review_type = str(entry.get("review_type") or "").strip().lower()
        if not image_path or not review_type:
            return None
        photo_faces: Optional[List[MetadataFace]] = None
        analysis_checks = self._configuredAnalysisChecks()
        if review_type == "position_deviations" and analysis_checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"):
            photo_faces = self._loadPhotoFacesForImage(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
            )
        elif review_type == "name_conflicts" and analysis_checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS"):
            photo_faces = self._loadPhotoFacesForImage(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
            )
        if review_type == "dimension_issues":
            if not self._hasFaceSignature(entry.get("left_face_signature")):
                return None
        elif review_type in {"duplicate_faces", "position_deviations", "name_conflicts"}:
            if not self._hasFaceSignature(entry.get("left_face_signature")) or not self._hasFaceSignature(entry.get("right_face_signature")):
                return None
        analysis = self.analyzeImageFaceMetadata(image_path)
        if review_type == "name_conflicts":
            expected_entry_token = self._checksEntryToken(entry)
            if expected_entry_token:
                current_entries = self._buildCheckEntriesForType(
                    image_path=image_path,
                    review_type=review_type,
                    analysis=analysis,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    photo_faces=photo_faces,
                )
                current_entry_tokens = {
                    self._checksEntryToken(candidate)
                    for candidate in current_entries
                    if isinstance(candidate, dict)
                }
                current_entry_tokens.discard("")
                if expected_entry_token not in current_entry_tokens:
                    return None
        if review_type == "dimension_issues":
            return self._buildDimensionMismatchReviewItem(image_path, analysis, entry)
        if review_type == "duplicate_faces":
            return self._buildDuplicateFaceReviewItem(image_path, analysis, entry)
        if review_type == "position_deviations":
            return self._buildPositionDeviationReviewItem(image_path, analysis, entry, photo_faces)
        if review_type == "name_conflicts":
            return self._buildNameConflictReviewItem(image_path, analysis, entry, photo_faces)
        return None

    @staticmethod
    def _incrementCounter(counter: Dict[str, int], key: str, amount: int = 1) -> None:
        normalized = str(key or "").strip()
        if not normalized:
            return
        counter[normalized] = counter.get(normalized, 0) + amount

    @staticmethod
    def _nonZeroCounters(counter: Dict[str, int]) -> Dict[str, int]:
        return {key: value for key, value in counter.items() if value > 0}

    def _buildFileAnalysisPayload(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        configured_extensions: List[str],
        status: str,
        phase: str,
        message: str,
        directories_read: int,
        files_seen_total: int,
        files_matched_total: int,
        files_analyzed: int,
        files_with_sidecar: int,
        files_with_embedded_xmp: int,
        files_with_face_metadata: int,
        files_with_mwg_applied_to_dimensions: int,
        files_with_mwg_dimension_mismatch: int,
        files_with_mwg_orientation_transform_risk: int,
        faces_total: int,
        faces_named: int,
        faces_unnamed: int,
        persons_distinct_names: set,
        files_with_duplicate_faces: Optional[int] = None,
        files_with_face_position_deviations: Optional[int] = None,
        files_with_dimension_issues: Optional[int] = None,
        files_with_name_conflicts: Optional[int] = None,
        focus_usages: Dict[str, int],
        extensions: Dict[str, int],
        formats: Dict[str, int],
        sources: Dict[str, int],
        current_path: str,
        running: bool,
        finished: bool,
        stopped: bool,
        stop_requested: bool,
        error: Optional[str] = None,
        io_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": self._timestamp_now() if finished else "",
            "last_updated_at": self._timestamp_now(),
            "status": status,
            "phase": phase,
            "message": message,
            "shared_folder": shared_folder,
            "configured_extensions": configured_extensions,
            "directories_read": directories_read,
            "files_seen_total": files_seen_total,
            "files_matched_total": files_matched_total,
            "files_analyzed": files_analyzed,
            "files_with_sidecar": files_with_sidecar,
            "files_with_embedded_xmp": files_with_embedded_xmp,
            "files_with_face_metadata": files_with_face_metadata,
            "files_with_mwg_applied_to_dimensions": files_with_mwg_applied_to_dimensions,
            "files_with_mwg_dimension_mismatch": files_with_mwg_dimension_mismatch,
            "files_with_mwg_orientation_transform_risk": files_with_mwg_orientation_transform_risk,
            "analysis_progress": {"current": files_analyzed, "total": files_matched_total},
            "faces_total": faces_total,
            "faces_named": faces_named,
            "faces_unnamed": faces_unnamed,
            "persons_distinct_by_name": len(persons_distinct_names),
            "files_with_duplicate_faces": files_with_duplicate_faces,
            "files_with_face_position_deviations": files_with_face_position_deviations,
            "files_with_dimension_issues": files_with_dimension_issues,
            "files_with_name_conflicts": files_with_name_conflicts,
            "focus_usages": self._nonZeroCounters(focus_usages),
            "running": running,
            "finished": finished,
            "stopped": stopped,
            "stop_requested": stop_requested,
            "current_path": current_path,
            "extensions": self._nonZeroCounters(extensions),
            "formats": self._nonZeroCounters(formats),
            "sources": self._nonZeroCounters(sources),
        }
        if isinstance(io_metrics, dict):
            payload["io_metrics"] = io_metrics
        if error:
            payload["error"] = error
        return payload

    @staticmethod
    def _normalizeChecksSingleSourceOfTruth(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "photos":
            return normalized
        metadata_formats = {"acd", "microsoft", "mwg_regions"}
        metadata_locations = {"any", "embedded", "sidecar"}
        if normalized.startswith("metadata:"):
            parts = normalized.split(":")
            if len(parts) == 3 and parts[1] in metadata_formats and parts[2] in metadata_locations:
                return normalized
        return ""

    def _configuredAnalysisChecks(self) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks = analysis.get("CHECKS") if isinstance(analysis.get("CHECKS"), dict) else {}
        defaults = ConfigService.defaultConfig()["analysis"]["CHECKS"]
        return {
            "DUPLICATE_FACES": bool(checks.get("DUPLICATE_FACES", defaults["DUPLICATE_FACES"])),
            "POSITION_DEVIATIONS": bool(checks.get("POSITION_DEVIATIONS", defaults["POSITION_DEVIATIONS"])),
            "POSITION_DEVIATIONS_INCLUDE_PHOTOS": bool(checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS", defaults["POSITION_DEVIATIONS_INCLUDE_PHOTOS"])),
            "DIMENSION_ISSUES": bool(checks.get("DIMENSION_ISSUES", defaults["DIMENSION_ISSUES"])),
            "NAME_CONFLICTS": bool(checks.get("NAME_CONFLICTS", defaults["NAME_CONFLICTS"])),
            "NAME_CONFLICTS_INCLUDE_PHOTOS": bool(checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS", defaults["NAME_CONFLICTS_INCLUDE_PHOTOS"])),
            "SINGLE_SOURCE_OF_TRUTH": self._normalizeChecksSingleSourceOfTruth(
                checks.get("SINGLE_SOURCE_OF_TRUTH", defaults["SINGLE_SOURCE_OF_TRUTH"])
            ),
        }

    def _runFileAnalysis(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        job_id: str,
    ) -> None:
        started_at = self._timestamp_now()
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        scan_context = ScanContext(self.config.readMergedConfig())
        configured_extensions = self.files.effectiveImageExtensions()
        analysis_checks = self._configuredAnalysisChecks()
        extension_counts: Dict[str, int] = {ext: 0 for ext in configured_extensions}
        source_counts: Dict[str, int] = {}
        format_counts: Dict[str, int] = {}
        focus_usage_counts: Dict[str, int] = {}
        matching_files: List[str] = []
        distinct_person_names = set()
        files_seen_total = 0
        files_matched_total = 0
        files_analyzed = 0
        files_with_sidecar = 0
        files_with_embedded_xmp = 0
        files_with_face_metadata = 0
        files_with_mwg_applied_to_dimensions = 0
        files_with_mwg_dimension_mismatch = 0
        files_with_mwg_orientation_transform_risk = 0
        faces_total = 0
        faces_named = 0
        faces_unnamed = 0
        directories_read = 0
        dimension_mismatch_paths: List[str] = []
        duplicate_faces_paths: List[str] = []
        position_deviation_paths: List[str] = []
        name_conflict_paths: List[str] = []
        dimension_mismatch_entries: List[Dict[str, Any]] = []
        duplicate_face_entries: List[Dict[str, Any]] = []
        position_deviation_entries: List[Dict[str, Any]] = []
        name_conflict_entries: List[Dict[str, Any]] = []
        reverse_face_match_entries: List[Dict[str, Any]] = []
        files_with_duplicate_faces: Optional[int] = None
        files_with_face_position_deviations: Optional[int] = None
        files_with_dimension_issues: Optional[int] = 0 if analysis_checks["DIMENSION_ISSUES"] else None
        files_with_name_conflicts: Optional[int] = 0 if analysis_checks["NAME_CONFLICTS"] else None

        if not shared_folder:
            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder="",
                status="failed",
                finished=True,
                findings_by_type={
                    "dimension_issues": [],
                    "duplicate_faces": [],
                    "position_deviations": [],
                    "name_conflicts": [],
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder="",
                status="failed",
                finished=True,
                entries=[],
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder="",
                    configured_extensions=configured_extensions,
                    status="failed",
                    phase="discovery",
                    message="Shared folder not found.",
                    directories_read=0,
                    files_seen_total=0,
                    files_matched_total=0,
                    files_analyzed=0,
                    files_with_sidecar=0,
                    files_with_embedded_xmp=0,
                    files_with_face_metadata=0,
                    files_with_mwg_applied_to_dimensions=0,
                    files_with_mwg_dimension_mismatch=0,
                    files_with_mwg_orientation_transform_risk=0,
                    faces_total=0,
                    faces_named=0,
                    faces_unnamed=0,
                    persons_distinct_names=set(),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages={},
                    extensions={},
                    formats={},
                    sources={},
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                    io_metrics=scan_context.io_metrics.snapshot() if scan_context.io_metrics else None,
                )
            )
            self.runtime_state.pop_value("file_analysis_threads", "default", None)
            return

        self._setFileAnalysisProgress(
            operation_id=f"file_analysis-{uuid4().hex}",
            running=True,
            finished=False,
            stopped=False,
            status="running",
            phase="discovery",
            message="Scanning files...",
            job_id=job_id,
            started_at=started_at,
            last_updated_at=started_at,
            shared_folder=shared_folder,
            configured_extensions=configured_extensions,
            directories_read=0,
            files_seen_total=0,
            files_matched_total=0,
            files_analyzed=0,
            files_with_sidecar=0,
            files_with_embedded_xmp=0,
            files_with_face_metadata=0,
            files_with_mwg_applied_to_dimensions=0,
            files_with_mwg_dimension_mismatch=0,
            files_with_mwg_orientation_transform_risk=0,
            analysis_progress={"current": 0, "total": 0},
            faces_total=0,
            faces_named=0,
            faces_unnamed=0,
            persons_distinct_by_name=0,
            files_with_duplicate_faces=files_with_duplicate_faces,
            files_with_face_position_deviations=files_with_face_position_deviations,
            files_with_dimension_issues=files_with_dimension_issues,
            files_with_name_conflicts=files_with_name_conflicts,
            current_path="",
            extensions={},
            focus_usages={},
            formats={},
            sources={},
        )
        self._writeAllFileAnalysisCheckFindings(
            job_id=job_id,
            started_at=started_at,
            shared_folder=shared_folder,
            status="running",
            finished=False,
            findings_by_type={
                "dimension_issues": [],
                "duplicate_faces": [],
                "position_deviations": [],
                "name_conflicts": [],
            },
        )
        self._writeReverseFaceMatchCandidates(
            job_id=job_id,
            started_at=started_at,
            shared_folder=shared_folder,
            status="running",
            finished=False,
            entries=[],
        )

        try:
            for dirpath, dirnames, filenames in os.walk(shared_folder):
                dirnames[:] = [dirname for dirname in dirnames if dirname != "@eaDir"]
                directories_read += 1
                self._setFileAnalysisProgress(
                    directories_read=directories_read,
                    current_path=str(dirpath),
                    last_updated_at=self._timestamp_now(),
                )
                if self._shouldStopFileAnalysis():
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        entries=reverse_face_match_entries,
                    )
                    self._persistFileAnalysisResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="stopped",
                            phase="discovery",
                            message=f"Discovery stopped. 0 of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=0,
                            files_with_sidecar=0,
                            files_with_embedded_xmp=0,
                            files_with_face_metadata=0,
                            files_with_mwg_applied_to_dimensions=0,
                            files_with_mwg_dimension_mismatch=0,
                            files_with_mwg_orientation_transform_risk=0,
                            faces_total=0,
                            faces_named=0,
                            faces_unnamed=0,
                            persons_distinct_names=set(),
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages={},
                            extensions=extension_counts,
                            formats={},
                            sources={},
                            current_path=str(dirpath),
                            running=False,
                            finished=True,
                            stopped=True,
                            stop_requested=False,
                        )
                    )
                    self.runtime_state.pop_value("file_analysis_threads", "default", None)
                    return
                for filename in filenames:
                    current_path = str(Path(dirpath) / filename)
                    if "@eaDir" in Path(current_path).parts:
                        continue
                    files_seen_total += 1
                    extension = Path(filename).suffix.lower().lstrip(".")
                    if extension in extension_counts:
                        files_matched_total += 1
                        extension_counts[extension] += 1
                        matching_files.append(current_path)
                    self._setFileAnalysisProgress(
                        files_seen_total=files_seen_total,
                        files_matched_total=files_matched_total,
                        current_path=current_path,
                        last_updated_at=self._timestamp_now(),
                        extensions=self._nonZeroCounters(extension_counts),
                    )
                    if self._shouldStopFileAnalysis():
                        self._writeAllFileAnalysisCheckFindings(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            status="stopped",
                            finished=True,
                            findings_by_type={
                                "dimension_issues": dimension_mismatch_entries,
                                "duplicate_faces": duplicate_face_entries,
                                "position_deviations": position_deviation_entries,
                                "name_conflicts": name_conflict_entries,
                            },
                        )
                        self._writeReverseFaceMatchCandidates(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            status="stopped",
                            finished=True,
                            entries=reverse_face_match_entries,
                        )
                        self._persistFileAnalysisResult(
                            self._buildFileAnalysisPayload(
                                job_id=job_id,
                                started_at=started_at,
                                shared_folder=shared_folder,
                                configured_extensions=configured_extensions,
                                status="stopped",
                                phase="discovery",
                                message=f"Discovery stopped. 0 of {files_matched_total} files analyzed.",
                                directories_read=directories_read,
                                files_seen_total=files_seen_total,
                                files_matched_total=files_matched_total,
                                files_analyzed=0,
                                files_with_sidecar=0,
                                files_with_embedded_xmp=0,
                                files_with_face_metadata=0,
                                files_with_mwg_applied_to_dimensions=0,
                                files_with_mwg_dimension_mismatch=0,
                                files_with_mwg_orientation_transform_risk=0,
                                faces_total=0,
                                faces_named=0,
                                faces_unnamed=0,
                                persons_distinct_names=set(),
                                files_with_duplicate_faces=files_with_duplicate_faces,
                                files_with_face_position_deviations=files_with_face_position_deviations,
                                files_with_dimension_issues=files_with_dimension_issues,
                                files_with_name_conflicts=files_with_name_conflicts,
                                focus_usages={},
                                extensions=extension_counts,
                                formats={},
                                sources={},
                                current_path=current_path,
                                running=False,
                                finished=True,
                                stopped=True,
                                stop_requested=False,
                            )
                        )
                        self.runtime_state.pop_value("file_analysis_threads", "default", None)
                        return

            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="running",
                    phase="analysis",
                    message=f"Analyzing face metadata in {files_matched_total} matching files...",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=0,
                    files_with_sidecar=0,
                    files_with_embedded_xmp=0,
                    files_with_face_metadata=0,
                    files_with_mwg_applied_to_dimensions=0,
                    files_with_mwg_dimension_mismatch=0,
                    files_with_mwg_orientation_transform_risk=0,
                    faces_total=0,
                    faces_named=0,
                    faces_unnamed=0,
                    persons_distinct_names=set(),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages={},
                    extensions=extension_counts,
                    formats={},
                    sources={},
                    current_path="",
                    running=True,
                    finished=False,
                    stopped=False,
                    stop_requested=self._shouldStopFileAnalysis(),
                )
            )

            for image_path in matching_files:
                if self._shouldStopFileAnalysis():
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        entries=reverse_face_match_entries,
                    )
                    self._persistFileAnalysisResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="stopped",
                            phase="analysis",
                            message=f"Analysis stopped. {files_analyzed} of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=files_analyzed,
                            files_with_sidecar=files_with_sidecar,
                            files_with_embedded_xmp=files_with_embedded_xmp,
                            files_with_face_metadata=files_with_face_metadata,
                            files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                            files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                            files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                            faces_total=faces_total,
                            faces_named=faces_named,
                            faces_unnamed=faces_unnamed,
                            persons_distinct_names=distinct_person_names,
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages=focus_usage_counts,
                            extensions=extension_counts,
                            formats=format_counts,
                            sources=source_counts,
                            current_path=image_path,
                            running=False,
                            finished=True,
                            stopped=True,
                            stop_requested=False,
                        )
                    )
                    self.runtime_state.pop_value("file_analysis_threads", "default", None)
                    return

                current_file_number = files_analyzed + 1
                self._setFileAnalysisProgress(
                    persist=False,
                    running=True,
                    finished=False,
                    stopped=False,
                    status="running",
                    phase="analysis",
                    analysis_stage="metadata",
                    message=f"Analyzing face metadata... {current_file_number} of {files_matched_total} files selected.",
                    current_path=image_path,
                    last_updated_at=self._timestamp_now(),
                    files_analyzed=files_analyzed,
                    analysis_progress={"current": files_analyzed, "total": files_matched_total},
                )
                def update_metadata_stage(stage: str) -> None:
                    self._setFileAnalysisProgress(
                        persist=False,
                        analysis_stage=stage,
                        message=f"Reading image metadata ({stage})... {current_file_number} of {files_matched_total} files selected.",
                        current_path=image_path,
                        last_updated_at=self._timestamp_now(),
                    )

                metadata_payload = self._readImageMetadata(
                    image_path,
                    include_unnamed_acd=True,
                    scan_context=scan_context,
                    progress_callback=update_metadata_stage,
                )
                include_photos_for_position_deviations = bool(analysis_checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"))
                include_photos_for_name_conflicts = bool(analysis_checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS"))
                include_photos_for_checks = include_photos_for_position_deviations or include_photos_for_name_conflicts
                if include_photos_for_checks:
                    self._setFileAnalysisProgress(
                        persist=False,
                        analysis_stage="photos_lookup",
                        message=f"Loading Photos comparison faces... {current_file_number} of {files_matched_total} files selected.",
                        current_path=image_path,
                        last_updated_at=self._timestamp_now(),
                    )
                photo_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                    photos_lookup_cache=scan_context.photos_lookup_cache,
                ) if include_photos_for_checks else []
                self._setFileAnalysisProgress(
                    persist=False,
                    analysis_stage="metadata_analysis",
                    message=f"Evaluating face metadata... {current_file_number} of {files_matched_total} files selected.",
                    current_path=image_path,
                    last_updated_at=self._timestamp_now(),
                )
                analysis = self.files.analyzeMetadata(
                    metadata_payload,
                    comparison_faces=[face.to_dict() for face in photo_faces],
                    include_position_deviation_comparison_faces=include_photos_for_position_deviations,
                    include_name_conflict_comparison_faces=include_photos_for_name_conflicts,
                )
                reverse_face_match_entries.extend(
                    self._buildReverseFaceMatchCandidateEntry(image_path=image_path, metadata_face=face)
                    for face in metadata_payload.faces
                    if not str(face.name or "").strip()
                )
                files_analyzed += 1
                if analysis.get("has_sidecar"):
                    files_with_sidecar += 1
                if str(analysis.get("xmp_source") or "").startswith("embedded_xmp_"):
                    files_with_embedded_xmp += 1
                if analysis.get("files_with_face_metadata"):
                    files_with_face_metadata += 1
                files_with_mwg_applied_to_dimensions += int(analysis.get("files_with_mwg_applied_to_dimensions") or 0)
                files_with_mwg_dimension_mismatch += int(analysis.get("files_with_mwg_dimension_mismatch") or 0)
                files_with_mwg_orientation_transform_risk += int(analysis.get("files_with_mwg_orientation_transform_risk") or 0)
                if analysis_checks["DIMENSION_ISSUES"]:
                    files_with_dimension_issues = files_with_mwg_dimension_mismatch
                if analysis_checks["DUPLICATE_FACES"]:
                    files_with_duplicate_faces = (files_with_duplicate_faces or 0) + int(analysis.get("files_with_duplicate_faces") or 0)
                    if analysis.get("files_with_duplicate_faces"):
                        duplicate_faces_paths.append(image_path)
                        duplicate_face_entries.extend(self._buildDuplicateFaceReviewEntries(image_path, analysis))
                if analysis_checks["POSITION_DEVIATIONS"]:
                    files_with_face_position_deviations = (files_with_face_position_deviations or 0) + int(analysis.get("files_with_face_position_deviations") or 0)
                    if analysis.get("files_with_face_position_deviations"):
                        position_deviation_paths.append(image_path)
                        position_deviation_entries.extend(self._buildPositionDeviationReviewEntries(image_path, analysis, photo_faces))
                if analysis_checks["NAME_CONFLICTS"]:
                    files_with_name_conflicts = (files_with_name_conflicts or 0) + int(analysis.get("files_with_name_conflicts") or 0)
                    if analysis.get("files_with_name_conflicts"):
                        name_conflict_paths.append(image_path)
                        name_conflict_entries.extend(self._buildNameConflictReviewEntries(image_path, analysis, photo_faces))
                if analysis.get("files_with_mwg_dimension_mismatch"):
                    dimension_mismatch_paths.append(image_path)
                    review_entry = self._buildDimensionMismatchReviewEntry(image_path, analysis)
                    if review_entry:
                        dimension_mismatch_entries.append(review_entry)
                    self._writeFileAnalysisCheckFindings(
                        finding_type="dimension_issues",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=dimension_mismatch_entries,
                    )
                if analysis.get("files_with_duplicate_faces"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="duplicate_faces",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=duplicate_face_entries,
                    )
                if analysis.get("files_with_face_position_deviations"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="position_deviations",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=position_deviation_entries,
                    )
                if analysis.get("files_with_name_conflicts"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="name_conflicts",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=name_conflict_entries,
                    )

                faces_total += int(analysis.get("faces_total") or 0)
                faces_named += int(analysis.get("faces_named") or 0)
                faces_unnamed += int(analysis.get("faces_unnamed") or 0)
                for key, value in (analysis.get("focus_usages") or {}).items():
                    self._incrementCounter(focus_usage_counts, str(key), int(value))

                for face in metadata_payload.faces:
                    name = str(face.name or "").strip()
                    if name:
                        distinct_person_names.add(name.casefold())
                    self._incrementCounter(source_counts, str(face.source or analysis.get("xmp_source") or "metadata"))
                    self._incrementCounter(format_counts, str(face.source_format or ""))

                self._setFileAnalysisProgress(
                    running=True,
                    finished=False,
                    stopped=False,
                    status="running",
                    phase="analysis",
                    analysis_stage="completed",
                    message=f"Analyzing face metadata... {files_analyzed} of {files_matched_total} files analyzed.",
                    current_path=image_path,
                    last_updated_at=self._timestamp_now(),
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    analysis_progress={"current": files_analyzed, "total": files_matched_total},
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_by_name=len(distinct_person_names),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=self._nonZeroCounters(focus_usage_counts),
                    formats=self._nonZeroCounters(format_counts),
                    sources=self._nonZeroCounters(source_counts),
                )

                if files_analyzed % 25 == 0:
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        entries=reverse_face_match_entries,
                    )
                    self.file_analysis.writeLatestResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="running",
                            phase="analysis",
                            message=f"Analyzing face metadata... {files_analyzed} of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=files_analyzed,
                            files_with_sidecar=files_with_sidecar,
                            files_with_embedded_xmp=files_with_embedded_xmp,
                            files_with_face_metadata=files_with_face_metadata,
                            files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                            files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                            files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                            faces_total=faces_total,
                            faces_named=faces_named,
                            faces_unnamed=faces_unnamed,
                            persons_distinct_names=distinct_person_names,
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages=focus_usage_counts,
                            extensions=extension_counts,
                            formats=format_counts,
                            sources=source_counts,
                            current_path=image_path,
                            running=True,
                            finished=False,
                            stopped=False,
                            stop_requested=self._shouldStopFileAnalysis(),
                        )
                    )

            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="finished",
                finished=True,
                findings_by_type={
                    "dimension_issues": dimension_mismatch_entries,
                    "duplicate_faces": duplicate_face_entries,
                    "position_deviations": position_deviation_entries,
                    "name_conflicts": name_conflict_entries,
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="finished",
                finished=True,
                entries=reverse_face_match_entries,
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="finished",
                    phase="analysis",
                    message=f"Analysis finished. {files_analyzed} of {files_matched_total} files analyzed.",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_names=distinct_person_names,
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=focus_usage_counts,
                    extensions=extension_counts,
                    formats=format_counts,
                    sources=source_counts,
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                )
            )
        except Exception as exc:
            failure_phase = "analysis" if files_matched_total else "discovery"
            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="failed",
                finished=True,
                findings_by_type={
                    "dimension_issues": dimension_mismatch_entries,
                    "duplicate_faces": duplicate_face_entries,
                    "position_deviations": position_deviation_entries,
                    "name_conflicts": name_conflict_entries,
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="failed",
                finished=True,
                entries=reverse_face_match_entries,
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="failed",
                    phase=failure_phase,
                    message="File analysis failed.",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_names=distinct_person_names,
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=focus_usage_counts,
                    extensions=extension_counts,
                    formats=format_counts,
                    sources=source_counts,
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                    error=str(exc),
                )
            )
        finally:
            self.runtime_state.pop_value("file_analysis_threads", "default", None)

    def startFileAnalysisDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        current = self.getFileAnalysisProgress()
        if current.get("running"):
            self._debugLog(
                "file_analysis_start_reused_running_progress",
                operation_id=current.get("operation_id"),
                status=current.get("status"),
                phase=current.get("phase"),
            )
            return current
        running_operation = self._runningOperationProgress(user_key, exclude_operation="file_analysis")
        if running_operation:
            self._debugLog(
                "file_analysis_start_blocked_by_running_operation",
                requested_operation="file_analysis",
                running_operation=running_operation.get("operation"),
                running_operation_id=running_operation.get("operation_id"),
                running_phase=running_operation.get("phase"),
            )
            return self._buildStartBlockedByRunningOperationPayload(
                running_operation,
                requested_operation="file_analysis",
            )

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        started_at = self._timestamp_now()
        self._debugLog("file_analysis_start", job_id=job_id)
        self._setFileAnalysisProgress(
            running=True,
            finished=False,
            stopped=False,
            stop_requested=False,
            status="running",
            phase="discovery",
            message="Starting file analysis...",
            job_id=job_id,
            started_at=started_at,
            finished_at="",
            last_updated_at=started_at,
            shared_folder="",
            configured_extensions=[],
            directories_read=0,
            files_seen_total=0,
            files_matched_total=0,
            files_analyzed=0,
            files_with_sidecar=0,
            files_with_embedded_xmp=0,
            files_with_face_metadata=0,
            files_with_mwg_applied_to_dimensions=0,
            files_with_mwg_dimension_mismatch=0,
            files_with_mwg_orientation_transform_risk=0,
            analysis_progress={"current": 0, "total": 0},
            faces_total=0,
            faces_named=0,
            faces_unnamed=0,
            persons_distinct_by_name=0,
            focus_usages={},
            current_path="",
            extensions={},
            formats={},
            sources={},
        )
        worker = Thread(
            target=self._runFileAnalysis,
            kwargs={
                "user_key": user_key,
                "cookies": cookies,
                "base_url": base_url,
                "job_id": job_id,
            },
            daemon=True,
        )
        self.runtime_state.set_value("file_analysis_threads", "default", worker)
        worker.start()
        return self.getFileAnalysisProgress()

    @staticmethod
    def _buildPhotoImagePath(shared_folder: str, folder_name: str, filename: str) -> str:
        folder_relative = folder_name.strip()
        if folder_relative.startswith("/"):
            folder_relative = folder_relative.lstrip("/")

        shared_folder_name = Path(shared_folder).name
        if shared_folder_name and folder_relative.startswith(f"{shared_folder_name}/"):
            folder_relative = folder_relative[len(shared_folder_name) + 1:]

        if folder_relative:
            return str(Path(shared_folder) / folder_relative / filename)
        return str(Path(shared_folder) / filename)

    def startFaceMatchingDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str = "search_photo_face_in_file",
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_from_progress: bool = False,
        recognize_persons: bool = False,
        skip_unknown_persons: bool = False,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.start_discovery(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            action=action,
            limit=limit,
            offset=offset,
            skip_face_ids=skip_face_ids,
            skip_targets=skip_targets,
            auto=auto,
            save_only=save_only,
            resume_from_progress=resume_from_progress,
            recognize_persons=recognize_persons,
            skip_unknown_persons=skip_unknown_persons,
        )

    def searchPhotoFaceInFile(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        known_persons_cache: Optional[List[Dict[str, Any]]] = None
        saved_entries = self._resumeFaceMatchSavedEntries(
            action="search_photo_face_in_file",
            save_only=save_only,
            resume_cursor=resume_cursor,
        )
        findings_job_id = f"face_match-{uuid4().hex}"
        findings_started_at = self._timestamp_now()
        last_findings_flush_count = len(saved_entries)
        last_findings_flush_at = monotonic()
        skip_face_ids_set = {
            int(face_id) for face_id in (skip_face_ids or [])
            if isinstance(face_id, int) or str(face_id).isdigit()
        }
        resume_skip_face_ids = resume_cursor.get("skip_face_ids") if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_face_ids"), list) else []
        skip_face_ids_set.update(
            int(face_id) for face_id in resume_skip_face_ids
            if isinstance(face_id, int) or str(face_id).isdigit()
        )
        skip_face_ids_set.update(self._faceMatchSavedEntryFaceIds(saved_entries))
        persons_read = int(resume_cursor.get("persons_read") or 0) if isinstance(resume_cursor, dict) else 0
        images_read = int(resume_cursor.get("images_read") or 0) if isinstance(resume_cursor, dict) else 0
        faces_read = int(resume_cursor.get("faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        target_faces_read = int(resume_cursor.get("target_faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        metadata_faces_read = int(resume_cursor.get("metadata_faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        findings_count = int(resume_cursor.get("findings_count") or 0) if isinstance(resume_cursor, dict) else 0
        if save_only:
            findings_count = len(saved_entries)
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        shared_folder = ""
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_photo_face_in_file",
            persons_read=persons_read,
            images_read=images_read,
            faces_read=faces_read,
            target_faces_read=target_faces_read,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=metadata_faces_read,
            transferred_count=transferred_count,
            findings_count=findings_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=list(skip_face_ids_set),
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                findings_count=findings_count,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
            ),
        )
        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action="search_photo_face_in_file",
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=saved_entries,
                        job_id=findings_job_id,
                        started_at=findings_started_at,
                    )
                return {
                    "searched": False,
                    "person": None,
                    "image": None,
                    "face": None,
                    "metadata_face": None,
                    "image_path": None,
                    "error": "shared_folder_not_found",
                }

            unknown_persons: List[Dict[str, Any]] = self.photos.sortPersonsForFaceMatch(
                self.photos.listFotoTeamPersonUnknown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    limit=limit,
                    offset=offset,
                    show_more=True,
                    show_hidden=False,
                )
            )
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_unknown_persons_loaded",
                message_params={"count": len(unknown_persons)},
                persons_total=len(unknown_persons),
            )

            for person in unknown_persons:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    if save_only:
                        self._writeFaceMatchFindings(
                            status="stopped",
                            shared_folder=shared_folder,
                            action="search_photo_face_in_file",
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                            job_id=findings_job_id,
                            started_at=findings_started_at,
                        )
                    return {
                        "searched": False,
                        "stopped": True,
                        "person": None,
                        "image": None,
                        "face": None,
                        "metadata_face": None,
                        "image_path": None,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "save_only": save_only,
                        "findings_count": findings_count,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=list(skip_face_ids_set),
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                        ),
                    }
                person_id = person.get("id")
                if person_id is None:
                    continue

                try:
                    person_id_int = int(person_id)
                except (TypeError, ValueError):
                    continue

                persons_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_person",
                    message_params={"current": persons_read, "total": len(unknown_persons)},
                    persons_read=persons_read,
                    current_person_id=person_id_int,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=list(skip_face_ids_set),
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                    ),
                )

                images = self.photos.listFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    person_id=person_id_int,
                    additional=['thumbnail'],
                )

                for image in images:
                    last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                        user_key=user_key,
                        base_url=base_url,
                        last_keepalive_at=last_keepalive_at,
                    )
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
                        if save_only:
                            self._writeFaceMatchFindings(
                                status="stopped",
                                shared_folder=shared_folder,
                                action="search_photo_face_in_file",
                                auto=auto,
                                save_only=save_only,
                                transferred_count=transferred_count,
                                entries=saved_entries,
                                job_id=findings_job_id,
                                started_at=findings_started_at,
                            )
                        return {
                            "searched": False,
                            "stopped": True,
                            "person": None,
                            "image": None,
                            "face": None,
                            "metadata_face": None,
                            "image_path": None,
                            "transferred_count": transferred_count,
                            "auto": auto,
                            "save_only": save_only,
                            "findings_count": findings_count,
                            "resume_cursor": self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        }
                    image_id = image.get("id")
                    if image_id is None:
                        continue

                    try:
                        image_id_int = int(image_id)
                    except (TypeError, ValueError):
                        continue

                    images_read += 1
                    self._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_checking_image",
                        message_params={"count": images_read},
                        images_read=images_read,
                        current_image_id=image_id_int,
                        resume_cursor=self._buildFaceMatchResumeCursor(
                            skip_face_ids=list(skip_face_ids_set),
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                        ),
                    )

                    faces = self.photos.list_faceFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        id_item=image_id_int
                    )
                    result_entry = None
                    for face in faces:
                        last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                            user_key=user_key,
                            base_url=base_url,
                            last_keepalive_at=last_keepalive_at,
                        )
                        if self._shouldStopFaceMatching(user_key):
                            final_message_key = "face_match:progress_stopped"
                            if save_only:
                                self._writeFaceMatchFindings(
                                    status="stopped",
                                    shared_folder=shared_folder,
                                    action="search_photo_face_in_file",
                                    auto=auto,
                                    save_only=save_only,
                                    transferred_count=transferred_count,
                                    entries=saved_entries,
                                    job_id=findings_job_id,
                                    started_at=findings_started_at,
                                )
                            return {
                                "searched": False,
                                "stopped": True,
                                "person": None,
                                "image": None,
                                "face": None,
                                "metadata_face": None,
                                "image_path": None,
                                "transferred_count": transferred_count,
                                "auto": auto,
                                "save_only": save_only,
                                "findings_count": findings_count,
                                "resume_cursor": self._buildFaceMatchResumeCursor(
                                    skip_face_ids=list(skip_face_ids_set),
                                    transferred_count=transferred_count,
                                    auto=auto,
                                    save_only=save_only,
                                ),
                            }
                        faces_read += 1
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_face",
                            message_params={"count": faces_read},
                            faces_read=faces_read,
                            current_face_id=face.get("face_id"),
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )
                        face_person_id = face.get("person_id")
                        face_id = face.get("face_id")
                        try:
                            face_person_id_int = int(face_person_id)
                            face_id_int = int(face_id)
                        except (TypeError, ValueError):
                            continue
                        if face_id_int in skip_face_ids_set:
                            continue
                        if face.get("face_name", "") != "":
                            continue
                        if face_person_id_int != person_id_int:
                            continue
                        skip_face_ids_set.add(face_id_int)

                        folder_id = image.get("folder_id")
                        filename = image.get("filename")
                        try:
                            folder_id_int = int(folder_id)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(filename, str) or not filename:
                            continue

                        folder_payload = self.photos.getFotoTeamFolder(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            id_folder=folder_id_int,
                        )
                        folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                        folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                        if not isinstance(folder_name, str) or not folder_name:
                            continue

                        image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                        metadata_payload = self._readImageMetadata(image_path)
                        metadata_faces = metadata_payload.faces
                        metadata_faces_read += len(metadata_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_metadata",
                            message_params={"count": images_read},
                            metadata_faces_read=metadata_faces_read,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )

                        photo_face = PhotosFace(
                            face_id=face_id_int,
                            person_id=person_id_int,
                            bbox=from_photos(face),
                        )
                        indexed_file_faces = [
                            (
                                metadata_index,
                                FileFace(
                                    name=metadata_face.name,
                                    bbox=from_xmp(metadata_face),
                                    source=metadata_face.source,
                                    source_format=metadata_face.source_format,
                                ),
                            )
                            for metadata_index, metadata_face in enumerate(metadata_faces)
                        ]
                        file_faces = [entry[1] for entry in indexed_file_faces]
                        if not file_faces:
                            continue

                        matches = self.face_matcher.match([photo_face], file_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_match_candidates",
                            message_params={"face": faces_read, "count": len(matches)},
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )
                        if not matches:
                            continue

                        matched = None
                        for candidate in matches:
                            match_name = str(candidate.get("file_name") or "").strip()
                            if match_name:
                                matched = candidate
                                break
                        if not matched:
                            final_message_key = "face_match:progress_only_unnamed_matches"
                            continue

                        file_face_index = matched.get("file_face_index")
                        if not isinstance(file_face_index, int) or file_face_index < 0 or file_face_index >= len(indexed_file_faces):
                            continue
                        metadata_face_index = indexed_file_faces[file_face_index][0]
                        matched_person = None
                        mapped_assignment = None
                        lookup_debug: Dict[str, Any] = {}
                        matched_name = str(matched.get("file_name") or "").strip()
                        if not matched_name:
                            continue
                        if matched_name:
                            if known_persons_cache is None:
                                known_persons_cache = self.photos.sortPersonsForFaceMatch(
                                    self.photos.listFotoTeamPersonKnown(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        additional=["thumbnail"],
                                    )
                                )
                            mapped_assignment = self.name_mappings.findNameMapping(matched_name)
                            if mapped_assignment:
                                mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
                                if mapped_target_name:
                                    matched_person = self.photos.findKnownPersonByName(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        name=mapped_target_name,
                                        known_persons=known_persons_cache,
                                    )
                            if matched_person is None:
                                matched_person = self.photos.findKnownPersonByName(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    name=matched_name,
                                    known_persons=known_persons_cache,
                                )
                            lookup_debug = self.photos.debugKnownPersonLookup(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                name=mapped_target_name if mapped_assignment and str(mapped_assignment.get("target_name") or "").strip() else matched_name,
                                known_persons=known_persons_cache,
                            )
                        final_message_key = "face_match:result_named_match"
                        final_message_params = {}
                        if matched_person:
                            final_message_key = "face_match:result_named_match_with_id"
                            final_message_params = {"id": matched_person.get("id")}

                        if auto and matched_person:
                            matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                            if matched_person_name:
                                result = self.resolveOrCreatePhotosPersonForExistingFace(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    image_path=image_path,
                                    face_id=face_id_int,
                                    person_name=str(matched_person_name),
                                    create_missing_person=False,
                                )
                                if result.get("updated"):
                                    transferred_count += 1
                                    final_message_key = "face_match:progress_auto_assigned"
                                    final_message_params = {"count": transferred_count}
                                    self._setFaceMatchingProgressMessage(
                                        user_key,
                                        final_message_key,
                                        message_params=final_message_params,
                                        transferred_count=transferred_count,
                                        resume_cursor=self._buildFaceMatchResumeCursor(
                                            skip_face_ids=list(skip_face_ids_set),
                                            transferred_count=transferred_count,
                                            auto=auto,
                                            save_only=save_only,
                                        ),
                                    )
                                    continue

                        result_entry = {
                            "searched": True,
                            "person": person,
                            "image": image,
                            "face": face,
                            "metadata_face": metadata_faces[metadata_face_index],
                            "image_path": image_path,
                            "match": matched,
                            "matched_person": matched_person,
                            "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                            "name_mapping": mapped_assignment,
                            "lookup_debug": lookup_debug,
                            "transferred_count": transferred_count,
                            "findings_count": findings_count + 1,
                            "auto": auto,
                            "resume_cursor": self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                findings_count=findings_count + 1,
                            ),
                        }
                    if result_entry is None:
                        continue
                    if save_only:
                        if self._appendUniqueFaceMatchFinding(saved_entries, result_entry):
                            findings_count = len(saved_entries)
                        skip_face_ids_set.add(face_id_int)
                        if self._shouldFlushFaceMatchFindings(
                            entries_count=len(saved_entries),
                            last_flush_count=last_findings_flush_count,
                            last_flush_at=last_findings_flush_at,
                        ):
                            self._writeFaceMatchFindings(
                                status="running",
                                shared_folder=shared_folder,
                                action="search_photo_face_in_file",
                                auto=auto,
                                save_only=save_only,
                                transferred_count=transferred_count,
                                entries=saved_entries,
                                job_id=findings_job_id,
                                started_at=findings_started_at,
                                finished=False,
                            )
                            last_findings_flush_count = len(saved_entries)
                            last_findings_flush_at = monotonic()
                        self._setFaceMatchingProgress(
                            user_key,
                            findings_count=findings_count,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                findings_count=findings_count,
                            ),
                        )
                        continue
                    if self._isFaceMatchFindingSuppressed(result_entry):
                        continue
                    findings_count += 1
                    return result_entry

            final_message_key = "face_match:result_no_match"
            final_message_params = {}
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="search_photo_face_in_file",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                    job_id=findings_job_id,
                    started_at=findings_started_at,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": findings_count,
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids_set),
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    findings_count=findings_count,
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids_set),
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    findings_count=findings_count,
                ),
            )

    def searchFileFaceInSources(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        saved_entries = self._resumeFaceMatchSavedEntries(
            action="search_file_face_in_sources",
            save_only=save_only,
            resume_cursor=resume_cursor,
        )
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        findings_count = int(resume_cursor.get("findings_count") or 0) if isinstance(resume_cursor, dict) else 0
        path_index = int(resume_cursor.get("path_index") or 0) if isinstance(resume_cursor, dict) else 0
        skip_target_tokens = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_targets"), list):
            for token in resume_cursor.get("skip_targets") or []:
                normalized = str(token or "").strip()
                if normalized and normalized not in skip_target_tokens:
                    skip_target_tokens.append(normalized)
        for token in self._faceMatchSavedEntryTargetTokens(saved_entries):
            if token not in skip_target_tokens:
                skip_target_tokens.append(token)
        if save_only:
            findings_count = len(saved_entries)
        last_findings_flush_count = len(saved_entries)
        last_findings_flush_at = monotonic()

        source_scope = self._fileFaceMatchSourceScope()
        use_photos = source_scope in {"both", "photos"}
        use_metadata = source_scope in {"both", "metadata"}
        persons_read = 0
        images_read = path_index
        faces_read = 0
        target_faces_read = 0
        metadata_faces_read = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_file_face_in_sources",
            persons_read=0,
            images_read=0,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=transferred_count,
            findings_count=findings_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=[],
                skip_targets=skip_target_tokens,
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                action="search_file_face_in_sources",
                findings_count=findings_count,
            ),
        )

        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action="search_file_face_in_sources",
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=saved_entries,
                    )
                return {
                    "searched": False,
                    "error": "shared_folder_not_found",
                    "source_scope": source_scope,
                }

            photo_faces_by_path: Dict[str, List[Dict[str, Any]]] = {}
            known_persons_cache: Optional[List[Dict[str, Any]]] = None
            if use_photos:
                known_persons = self.photos.sortPersonsForFaceMatch(
                    self.photos.listFotoTeamPersonKnown(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        show_more=True,
                        show_hidden=False,
                        additional=["thumbnail"],
                    )
                )
                known_persons_cache = known_persons
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_known_persons_loaded",
                    message_params={"count": len(known_persons)},
                    persons_read=persons_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    )
                seen_image_ids: Dict[int, str] = {}
                for person in known_persons:
                    last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                        user_key=user_key,
                        base_url=base_url,
                        last_keepalive_at=last_keepalive_at,
                    )
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
                        if save_only:
                            self._writeFaceMatchFindings(
                                status="stopped",
                                shared_folder=shared_folder,
                                action="search_file_face_in_sources",
                                auto=auto,
                                save_only=save_only,
                                transferred_count=transferred_count,
                                entries=saved_entries,
                            )
                        return {
                            "searched": False,
                            "stopped": True,
                            "transferred_count": transferred_count,
                            "auto": auto,
                            "save_only": save_only,
                            "findings_count": findings_count,
                            "resume_cursor": self._buildFaceMatchResumeCursor(
                                skip_face_ids=[],
                                skip_targets=skip_target_tokens,
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                action="search_file_face_in_sources",
                            ),
                        }
                    person_id = person.get("id")
                    if person_id is None:
                        continue
                    try:
                        person_id_int = int(person_id)
                    except (TypeError, ValueError):
                        continue
                    persons_read += 1
                    self._setFaceMatchingProgress(
                        user_key,
                        persons_read=persons_read,
                        faces_read=faces_read,
                        target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    )
                    images = self.photos.listFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        person_id=person_id_int,
                        additional=["thumbnail"],
                    )
                    for image in images:
                        image_id = image.get("id")
                        folder_id = image.get("folder_id")
                        filename = image.get("filename")
                        try:
                            image_id_int = int(image_id)
                            folder_id_int = int(folder_id)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(filename, str) or not filename:
                            continue
                        if image_id_int in seen_image_ids:
                            image_path = seen_image_ids[image_id_int]
                        else:
                            folder_payload = self.photos.getFotoTeamFolder(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                id_folder=folder_id_int,
                            )
                            folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                            folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                            if not isinstance(folder_name, str) or not folder_name:
                                continue
                            image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                            seen_image_ids[image_id_int] = image_path
                        if image_path not in photo_faces_by_path:
                            photo_faces_by_path[image_path] = []
                        faces = self.photos.list_faceFotoTeamItems(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            id_item=image_id_int,
                        )
                        for face in faces:
                            face_name = str(face.get("face_name") or "").strip()
                            face_id = face.get("face_id")
                            if not face_name or face_id is None:
                                continue
                            try:
                                face_id_int = int(face_id)
                                face_person_id_int = int(face.get("person_id"))
                            except (TypeError, ValueError):
                                continue
                            if face_person_id_int != person_id_int:
                                self._debugLog(
                                    "face_match_photo_source_face_skipped_person_mismatch",
                                    image_id=image_id_int,
                                    face_id=face_id_int,
                                    face_name=face_name,
                                    face_person_id=face_person_id_int,
                                    album_person_id=person_id_int,
                                )
                                continue
                            if any(int(existing.get("face_id")) == face_id_int for existing in photo_faces_by_path[image_path] if existing.get("face_id") is not None):
                                continue
                            face_record = dict(face)
                            face_record["image"] = image
                            face_record["person"] = person
                            photo_faces_by_path[image_path].append(face_record)
                            faces_read += 1
                        self._setFaceMatchingProgress(
                            user_key,
                            persons_read=persons_read,
                            faces_read=faces_read,
                            target_faces_read=target_faces_read,
                            metadata_faces_read=metadata_faces_read,
                        )

            reverse_candidates = self._getReverseFaceMatchCandidateEntries()
            candidate_entries_by_path: Dict[str, List[Dict[str, Any]]] = {}
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_listing_files",
                message_params={"path": shared_folder},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                    findings_count=findings_count,
                ),
            )
            if reverse_candidates:
                for entry in reverse_candidates:
                    image_path = str(entry.get("image_path") or "").strip()
                    if not image_path:
                        continue
                    candidate_entries_by_path.setdefault(image_path, []).append(entry)
                candidate_paths = list(candidate_entries_by_path.keys())
            else:
                candidate_paths = self.files.listImageFiles(shared_folder)
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_files_listed",
                message_params={"count": len(candidate_paths)},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                total_images=len(candidate_paths),
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                    findings_count=findings_count,
                ),
            )
            for image_path in candidate_paths:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    if save_only:
                        self._writeFaceMatchFindings(
                            status="stopped",
                            shared_folder=shared_folder,
                            action="search_file_face_in_sources",
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                        )
                    return {
                        "searched": False,
                        "stopped": True,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "save_only": save_only,
                        "findings_count": findings_count,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="search_file_face_in_sources",
                        ),
                    }

                images_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_file",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="search_file_face_in_sources",
                    ),
                )

                metadata_payload = self._readImageMetadata(image_path)
                metadata_faces = metadata_payload.faces
                metadata_faces_read += len(metadata_faces)
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_metadata",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="search_file_face_in_sources",
                    ),
                )
                candidate_entries = candidate_entries_by_path.get(image_path, [])
                if candidate_entries:
                    unnamed_targets = []
                    for candidate_entry in candidate_entries:
                        signature = candidate_entry.get("metadata_face")
                        if not isinstance(signature, dict):
                            continue
                        existing_face = self._findFaceBySignature(metadata_faces, signature)
                        if not existing_face or str(existing_face.name or "").strip():
                            continue
                        unnamed_targets.append(existing_face)
                else:
                    unnamed_targets = [face for face in metadata_faces if not str(face.name or "").strip()]
                if not unnamed_targets:
                    continue

                metadata_sources = [
                    face for face in metadata_faces
                    if str(face.name or "").strip()
                ] if use_metadata else []
                photo_sources = photo_faces_by_path.get(image_path, []) if use_photos else []

                for target_face in unnamed_targets:
                    target_faces_read += 1
                    target_token = self._faceMatchTargetToken(image_path=image_path, face=target_face)
                    if target_token in skip_target_tokens:
                        self._setFaceMatchingProgress(
                            user_key,
                            target_faces_read=target_faces_read,
                        )
                        continue

                    matched_entry = self._matchFileFaceInSources(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        image_path=image_path,
                        target_face=target_face,
                        photo_sources=photo_sources,
                        metadata_sources=metadata_sources,
                        known_persons_cache=known_persons_cache,
                    )
                    self._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_match_candidates",
                        message_params={"face": images_read, "count": 1 if matched_entry else 0},
                        images_read=images_read,
                        faces_read=faces_read,
                        target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    )
                    if not matched_entry:
                        continue
                    source_name = str(matched_entry.get("source_name") or "").strip()
                    final_message_key = "face_match:result_named_source_match"
                    final_message_params = {}
                    matched_person = matched_entry.get("matched_person") if isinstance(matched_entry.get("matched_person"), dict) else None
                    if matched_person and matched_person.get("id") is not None:
                        final_message_key = "face_match:result_named_source_match_with_id"
                        final_message_params = {"id": matched_person.get("id")}

                    result_entry = dict(matched_entry)
                    result_entry.update({
                        "transferred_count": transferred_count,
                        "findings_count": findings_count + 1,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens + [target_token],
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="search_file_face_in_sources",
                            findings_count=findings_count + 1,
                        ),
                    })

                    if auto:
                        update_result = self.replaceMetadataFaceName(
                            image_path=image_path,
                            face_data=target_face.to_dict(),
                            new_name=source_name,
                        )
                        if update_result.get("updated"):
                            transferred_count += 1
                            skip_target_tokens.append(target_token)
                            final_message_key = "face_match:progress_auto_metadata_assigned"
                            final_message_params = {"count": transferred_count}
                            self._setFaceMatchingProgressMessage(
                                user_key,
                                final_message_key,
                                message_params=final_message_params,
                                transferred_count=transferred_count,
                                resume_cursor=self._buildFaceMatchResumeCursor(
                                    skip_face_ids=[],
                                    skip_targets=skip_target_tokens,
                                    transferred_count=transferred_count,
                                    auto=auto,
                                    save_only=save_only,
                                    action="search_file_face_in_sources",
                                    findings_count=findings_count,
                                ),
                            )
                            continue

                    findings_count += 1
                    if save_only:
                        self._appendUniqueFaceMatchFinding(saved_entries, result_entry)
                        findings_count = len(saved_entries)
                        skip_target_tokens.append(target_token)
                        if self._shouldFlushFaceMatchFindings(
                            entries_count=len(saved_entries),
                            last_flush_count=last_findings_flush_count,
                            last_flush_at=last_findings_flush_at,
                        ):
                            self._writeFaceMatchFindings(
                                status="running",
                                shared_folder=shared_folder,
                                action="search_file_face_in_sources",
                                auto=auto,
                                save_only=save_only,
                                transferred_count=transferred_count,
                                entries=saved_entries,
                                finished=False,
                            )
                            last_findings_flush_count = len(saved_entries)
                            last_findings_flush_at = monotonic()
                        self._setFaceMatchingProgress(
                            user_key,
                            findings_count=findings_count,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=[],
                                skip_targets=skip_target_tokens,
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                action="search_file_face_in_sources",
                                findings_count=findings_count,
                            ),
                        )
                        continue
                    if self._isFaceMatchFindingSuppressed(result_entry):
                        continue
                    return result_entry

            final_message_key = "face_match:result_no_match"
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_metadata_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="search_file_face_in_sources",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": findings_count,
                "source_scope": source_scope,
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                    findings_count=findings_count,
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                    findings_count=findings_count,
                ),
            )

    def searchMissingPhotosFaces(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        saved_entries = self._resumeFaceMatchSavedEntries(
            action="mark_missing_photos_faces",
            save_only=save_only,
            resume_cursor=resume_cursor,
        )
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        findings_count = int(resume_cursor.get("findings_count") or 0) if isinstance(resume_cursor, dict) else 0
        path_index = int(resume_cursor.get("path_index") or 0) if isinstance(resume_cursor, dict) else 0
        skip_target_tokens = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_targets"), list):
            for token in resume_cursor.get("skip_targets") or []:
                normalized = str(token or "").strip()
                if normalized and normalized not in skip_target_tokens:
                    skip_target_tokens.append(normalized)
        for token in self._faceMatchSavedEntryTargetTokens(saved_entries):
            if token not in skip_target_tokens:
                skip_target_tokens.append(token)
        if save_only:
            findings_count = max(findings_count, len(saved_entries))
        last_findings_flush_count = len(saved_entries)
        last_findings_flush_at = monotonic()

        persons_read = 0
        images_read = path_index
        faces_read = 0
        target_faces_read = 0
        metadata_faces_read = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        known_persons_cache: Optional[List[Dict[str, Any]]] = None

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="mark_missing_photos_faces",
            persons_read=0,
            images_read=images_read,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=transferred_count,
            findings_count=findings_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=[],
                skip_targets=skip_target_tokens,
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                action="mark_missing_photos_faces",
                findings_count=findings_count,
                path_index=path_index,
            ),
        )

        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action="mark_missing_photos_faces",
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=saved_entries,
                    )
                return {
                    "searched": False,
                    "error": "shared_folder_not_found",
                }
            photos_lookup_cache = PhotosLookupCache()

            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_listing_files",
                message_params={"path": shared_folder},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                    findings_count=findings_count,
                    path_index=path_index,
                ),
            )
            candidate_paths = self.files.listImageFiles(shared_folder)
            path_index = min(max(0, path_index), len(candidate_paths))
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_files_listed",
                message_params={"count": len(candidate_paths)},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                total_images=len(candidate_paths),
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                    findings_count=findings_count,
                    path_index=path_index,
                ),
            )
            for image_path in candidate_paths[path_index:]:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    if save_only:
                        self._writeFaceMatchFindings(
                            status="stopped",
                            shared_folder=shared_folder,
                            action="mark_missing_photos_faces",
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                        )
                    return {
                        "searched": False,
                        "stopped": True,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "save_only": save_only,
                        "findings_count": findings_count,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="mark_missing_photos_faces",
                            findings_count=findings_count,
                            path_index=images_read,
                        ),
                    }

                images_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_file",
                    message_params={"count": images_read, "total": len(candidate_paths)},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                        findings_count=findings_count,
                        path_index=images_read,
                    ),
                )

                metadata_payload = self._readImageMetadata(image_path)
                metadata_faces = metadata_payload.faces
                metadata_faces_read += len(metadata_faces)
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_metadata",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                        findings_count=findings_count,
                        path_index=images_read,
                    ),
                )

                if not any(str(face.name or "").strip() for face in metadata_faces):
                    continue

                item = self.photos.findFotoTeamItemByPath(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                    additional=["thumbnail"],
                    lookup_cache=photos_lookup_cache,
                )
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id is None:
                    continue
                try:
                    item_id_int = int(item_id)
                except (TypeError, ValueError):
                    continue

                photo_faces = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=item_id_int,
                )
                faces_read += len(photo_faces)
                self._setFaceMatchingProgress(
                    user_key,
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    current_image_id=item_id_int,
                )
                photo_file_faces = [
                    FileFace(
                        name=str(face.get("face_name") or ""),
                        bbox=from_photos(face),
                        source="photos",
                        source_format="PHOTOS",
                    )
                    for face in photo_faces
                    if isinstance(face, dict) and isinstance(face.get("bbox"), dict)
                ]
                target_face, metadata_faces_by_format = self._selectMissingPhotosFaceCandidate(
                    candidate_faces=metadata_faces,
                    existing_photos_faces=photo_faces,
                    require_name=True,
                )
                if target_face is None:
                    continue

                target_faces_read += 1
                target_token = self._faceMatchTargetToken(image_path=image_path, face=target_face)
                if target_token in skip_target_tokens:
                    continue
                if known_persons_cache is None:
                    known_persons_cache = self.photos.sortPersonsForFaceMatch(
                        self.photos.listFotoTeamPersonKnown(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            additional=["thumbnail"],
                        )
                    )

                source_name = str(target_face.name or "").strip()
                matched_person, mapped_assignment, lookup_debug = self._lookupMatchedPersonBySourceName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    source_name=source_name,
                    known_persons_cache=known_persons_cache,
                )

                result_entry = {
                    "action": "mark_missing_photos_faces",
                    "searched": True,
                    "person": matched_person if isinstance(matched_person, dict) else None,
                    "image": item if isinstance(item, dict) else None,
                    "face": to_display_face(target_face),
                    "source_face": to_display_face(target_face),
                    "source_name": source_name,
                    "source_type": "metadata_face",
                    "metadata_face": to_display_face(target_face),
                    "image_path": image_path,
                    "match": {
                        "source_type": "metadata_face",
                        "source": target_face.source,
                        "source_format": target_face.source_format,
                        "file_name": source_name,
                        "iou": 1.0,
                        "photos_faces_count": len(photo_faces),
                        "metadata_faces_by_format": metadata_faces_by_format,
                    },
                    "matched_person": matched_person,
                    "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                    "name_mapping": mapped_assignment,
                    "lookup_debug": lookup_debug,
                    "add_new_faces_to_photos": True,
                    "transferred_count": transferred_count,
                    "findings_count": findings_count + 1,
                    "auto": auto,
                    "resume_cursor": self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens + [target_token],
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                        findings_count=findings_count + 1,
                        path_index=images_read,
                    ),
                }

                if auto and matched_person and matched_person.get("id") is not None:
                    result = self.resolveOrCreatePhotosPersonForMetadataFace(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        image_path=image_path,
                        metadata_face=target_face.to_dict(),
                        person_name=source_name,
                        create_missing_person=False,
                    )
                    if result.get("updated"):
                        transferred_count += 1
                        skip_target_tokens.append(target_token)
                        final_message_key = "face_match:progress_auto_assigned"
                        final_message_params = {"count": transferred_count}
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            final_message_key,
                            message_params=final_message_params,
                            transferred_count=transferred_count,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=[],
                                skip_targets=skip_target_tokens,
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                action="mark_missing_photos_faces",
                                findings_count=findings_count,
                                path_index=images_read,
                            ),
                        )
                        continue

                findings_count += 1
                if save_only:
                    self._appendUniqueFaceMatchFinding(saved_entries, result_entry)
                    findings_count = len(saved_entries)
                    skip_target_tokens.append(target_token)
                    if self._shouldFlushFaceMatchFindings(
                        entries_count=len(saved_entries),
                        last_flush_count=last_findings_flush_count,
                        last_flush_at=last_findings_flush_at,
                    ):
                        self._writeFaceMatchFindings(
                            status="running",
                            shared_folder=shared_folder,
                            action="mark_missing_photos_faces",
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                            finished=False,
                        )
                        last_findings_flush_count = len(saved_entries)
                        last_findings_flush_at = monotonic()
                    self._setFaceMatchingProgress(
                        user_key,
                        findings_count=findings_count,
                        resume_cursor=self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="mark_missing_photos_faces",
                            findings_count=findings_count,
                            path_index=images_read,
                        ),
                    )
                    continue
                if self._isFaceMatchFindingSuppressed(result_entry):
                    continue
                return result_entry

            final_message_key = "face_match:result_no_match"
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="mark_missing_photos_faces",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": findings_count,
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                    findings_count=findings_count,
                    path_index=images_read,
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                    findings_count=findings_count,
                    path_index=images_read,
                ),
            )

    def searchMissingPhotosFacesWithInsightFace(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        recognize_persons: bool = False,
        skip_unknown_persons: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        action = "search_missing_faces_insightface"
        saved_entries = self._resumeFaceMatchSavedEntries(
            action=action,
            save_only=save_only,
            resume_cursor=resume_cursor,
        )
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        findings_count = int(resume_cursor.get("findings_count") or 0) if isinstance(resume_cursor, dict) else 0
        path_index = int(resume_cursor.get("path_index") or 0) if isinstance(resume_cursor, dict) else 0
        skip_target_tokens = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_targets"), list):
            for token in resume_cursor.get("skip_targets") or []:
                normalized = str(token or "").strip()
                if normalized and normalized not in skip_target_tokens:
                    skip_target_tokens.append(normalized)
        for token in self._faceMatchSavedEntryTargetTokens(saved_entries):
            if token not in skip_target_tokens:
                skip_target_tokens.append(token)
        if save_only:
            findings_count = len(saved_entries)
        last_findings_flush_count = len(saved_entries)
        last_findings_flush_at = monotonic()

        persons_read = 0
        images_read = int(resume_cursor.get("images_read") or path_index) if isinstance(resume_cursor, dict) else 0
        faces_read = int(resume_cursor.get("faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        target_faces_read = int(resume_cursor.get("target_faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        metadata_faces_read = int(resume_cursor.get("metadata_faces_read") or 0) if isinstance(resume_cursor, dict) else 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        shared_folder = ""

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action=action,
            persons_read=0,
            images_read=images_read,
            faces_read=faces_read,
            target_faces_read=target_faces_read,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=metadata_faces_read,
            transferred_count=transferred_count,
            findings_count=findings_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=[],
                skip_targets=skip_target_tokens,
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                action=action,
                recognize_persons=bool(recognize_persons),
                skip_unknown_persons=bool(skip_unknown_persons),
                findings_count=findings_count,
                path_index=path_index,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
            ),
        )

        try:
            if not self.pipPackagesStatus().get("packages", {}).get("INSIGHTFACE", {}).get("installed"):
                final_message_key = "face_match:progress_insightface_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action=action,
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=saved_entries,
                    )
                return {
                    "searched": False,
                    "error": "insightface_not_installed",
                    "transferred_count": transferred_count,
                    "auto": auto,
                    "save_only": save_only,
                    "findings_count": findings_count,
                }

            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action=action,
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=saved_entries,
                    )
                return {
                    "searched": False,
                    "error": "shared_folder_not_found",
                }
            photos_lookup_cache = PhotosLookupCache()

            detector = (
                InsightFaceEmbedder(
                    model_name=self._configuredInsightFaceModelName(),
                    model_root=self._configuredInsightFaceModelRoot(),
                    max_image_edge=self._recognitionImageMaxEdge(),
                )
                if recognize_persons else
                InsightFaceDetector(
                    model_name=self._configuredInsightFaceModelName(),
                    model_root=self._configuredInsightFaceModelRoot(),
                )
            )
            recognition_profiles = []
            if recognize_persons:
                profiles_payload = self.face_recognition.profiles({})
                profile_entries = profiles_payload.get("profiles") if isinstance(profiles_payload, dict) else []
                recognition_profiles = [
                    profile for profile in (profile_entries if isinstance(profile_entries, list) else [])
                    if profile.get("centroid_embedding")
                ]
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_listing_files",
                message_params={"path": shared_folder},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                    recognize_persons=bool(recognize_persons),
                    skip_unknown_persons=bool(skip_unknown_persons),
                    findings_count=findings_count,
                    path_index=path_index,
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                ),
            )
            candidate_paths = self._getFaceMatchCandidatePaths(
                user_key=user_key,
                action=action,
                shared_folder=shared_folder,
                use_cache=bool(resume_cursor),
            )
            path_index = min(max(0, path_index), len(candidate_paths))
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_files_listed",
                message_params={"count": len(candidate_paths)},
                total_images=len(candidate_paths),
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                    recognize_persons=bool(recognize_persons),
                    skip_unknown_persons=bool(skip_unknown_persons),
                    findings_count=findings_count,
                    path_index=path_index,
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                ),
            )

            for index, image_path in enumerate(candidate_paths[path_index:], start=path_index):
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    if save_only:
                        self._writeFaceMatchFindings(
                            status="stopped",
                            shared_folder=shared_folder,
                            action=action,
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                        )
                    return {
                        "searched": False,
                        "stopped": True,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "save_only": save_only,
                        "findings_count": findings_count,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action=action,
                            recognize_persons=bool(recognize_persons),
                            skip_unknown_persons=bool(skip_unknown_persons),
                            findings_count=findings_count,
                        ),
                    }

                images_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_file",
                    message_params={"count": images_read, "total": len(candidate_paths)},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action=action,
                        recognize_persons=bool(recognize_persons),
                        skip_unknown_persons=bool(skip_unknown_persons),
                        findings_count=findings_count,
                    ),
                )

                raw_detections = (
                    detector.detect_and_embed(Path(image_path))
                    if recognize_persons
                    else detector.detect(Path(image_path))
                )
                detected_pairs = [
                    (face, detection) for detection in raw_detections
                    for face in [self._insightFaceDetectionToMetadataFace(detection)]
                    if face is not None
                ]
                detected_faces = [face for face, _detection in detected_pairs]
                metadata_faces_read += len(detected_faces)
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_insightface",
                    message_params={"count": images_read, "faces": len(detected_faces)},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action=action,
                        recognize_persons=bool(recognize_persons),
                        skip_unknown_persons=bool(skip_unknown_persons),
                        findings_count=findings_count,
                    ),
                )
                if not detected_faces:
                    continue

                item = self.photos.findFotoTeamItemByPath(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                    additional=["thumbnail"],
                    lookup_cache=photos_lookup_cache,
                )
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id is None:
                    continue
                try:
                    item_id_int = int(item_id)
                except (TypeError, ValueError):
                    continue

                photo_faces = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=item_id_int,
                )
                faces_read += len(photo_faces)
                target_face, faces_by_format = self._selectMissingPhotosFaceCandidate(
                    candidate_faces=detected_faces,
                    existing_photos_faces=photo_faces,
                    require_name=False,
                )
                self._setFaceMatchingProgress(
                    user_key,
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    current_image_id=item_id_int,
                )
                if target_face is None:
                    continue
                target_detection = next(
                    (
                        detection for face, detection in detected_pairs
                        if self._faceMatchTargetToken(image_path=image_path, face=face)
                        == self._faceMatchTargetToken(image_path=image_path, face=target_face)
                    ),
                    {},
                )
                matched_person = None
                recognition_score = None
                if recognize_persons and recognition_profiles and isinstance(target_detection, dict) and target_detection.get("embedding"):
                    scored_profiles = sorted(
                        [
                            (
                                self.face_recognition._similarity(
                                    target_detection.get("embedding") or [],
                                    profile.get("centroid_embedding") or [],
                                ),
                                profile,
                            )
                            for profile in recognition_profiles
                        ],
                        key=lambda item: item[0],
                        reverse=True,
                    )
                    if scored_profiles:
                        recognition_score, best_profile = scored_profiles[0]
                        recognition_options = self.face_recognition.normalize_options({})
                        if recognition_score >= recognition_options["review_score"]:
                            matched_person = {
                                "id": best_profile.get("person_id"),
                                "name": best_profile.get("person_name"),
                                "thumbnail": (best_profile.get("medoid") or {}).get("thumbnail"),
                            }
                            target_face.name = str(best_profile.get("person_name") or "")

                target_faces_read += 1
                target_token = self._faceMatchTargetToken(image_path=image_path, face=target_face)
                if target_token in skip_target_tokens:
                    continue
                if recognize_persons and skip_unknown_persons and not isinstance(matched_person, dict):
                    skip_target_tokens.append(target_token)
                    self._setFaceMatchingProgress(
                        user_key,
                        findings_count=findings_count,
                        resume_cursor=self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action=action,
                            recognize_persons=bool(recognize_persons),
                            skip_unknown_persons=True,
                            findings_count=findings_count,
                            path_index=images_read,
                            images_read=images_read,
                            faces_read=faces_read,
                            target_faces_read=target_faces_read,
                            metadata_faces_read=metadata_faces_read,
                        ),
                    )
                    continue

                result_entry = {
                    "action": action,
                    "searched": True,
                    "person": None,
                    "image": item if isinstance(item, dict) else None,
                    "face": to_display_face(target_face),
                    "source_face": to_display_face(target_face),
                    "source_name": str(target_face.name or ""),
                    "source_type": "insightface_detection",
                    "metadata_face": to_display_face(target_face),
                    "image_path": image_path,
                    "match": {
                        "source_type": "insightface_detection",
                        "source": target_face.source,
                        "source_format": target_face.source_format,
                        "file_name": "",
                        "iou": 1.0,
                        "photos_faces_count": len(photo_faces),
                        "metadata_faces_by_format": faces_by_format,
                    },
                    "matched_person": matched_person,
                    "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                    "recognition_score": recognition_score,
                    "recognition_enabled": bool(recognize_persons),
                    "name_mapping": None,
                    "lookup_debug": {},
                    "add_new_faces_to_photos": True,
                    "transferred_count": transferred_count,
                    "findings_count": findings_count + 1,
                    "auto": auto,
                    "resume_cursor": self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens + [target_token],
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action=action,
                        recognize_persons=bool(recognize_persons),
                        skip_unknown_persons=bool(skip_unknown_persons),
                        findings_count=findings_count + 1,
                        path_index=images_read,
                        images_read=images_read,
                        faces_read=faces_read,
                        target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    ),
                }

                if save_only:
                    if self._appendUniqueFaceMatchFinding(saved_entries, result_entry):
                        findings_count = len(saved_entries)
                    skip_target_tokens.append(target_token)
                    if self._shouldFlushFaceMatchFindings(
                        entries_count=len(saved_entries),
                        last_flush_count=last_findings_flush_count,
                        last_flush_at=last_findings_flush_at,
                    ):
                        self._writeFaceMatchFindings(
                            status="running",
                            shared_folder=shared_folder,
                            action=action,
                            auto=auto,
                            save_only=save_only,
                            transferred_count=transferred_count,
                            entries=saved_entries,
                            finished=False,
                        )
                        last_findings_flush_count = len(saved_entries)
                        last_findings_flush_at = monotonic()
                    self._setFaceMatchingProgress(
                        user_key,
                        findings_count=findings_count,
                        resume_cursor=self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action=action,
                            recognize_persons=bool(recognize_persons),
                            skip_unknown_persons=bool(skip_unknown_persons),
                            findings_count=findings_count,
                            path_index=images_read,
                            images_read=images_read,
                            faces_read=faces_read,
                            target_faces_read=target_faces_read,
                            metadata_faces_read=metadata_faces_read,
                        ),
                    )
                    continue
                if self._isFaceMatchFindingSuppressed(result_entry):
                    continue
                findings_count += 1
                self._setFaceMatchingProgress(
                    user_key,
                    result=result_entry,
                    findings_count=findings_count,
                    resume_cursor=result_entry.get("resume_cursor"),
                )
                return result_entry

            final_message_key = "face_match:result_no_match"
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": findings_count}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action=action,
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": findings_count,
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                    recognize_persons=bool(recognize_persons),
                    skip_unknown_persons=bool(skip_unknown_persons),
                    findings_count=findings_count,
                ),
            }
        except FaceDetectorUnavailable as exc:
            final_message_key = "face_match:progress_insightface_unavailable"
            final_message_params = {"error": str(exc)}
            if save_only:
                self._writeFaceMatchFindings(
                    status="failed",
                    shared_folder=shared_folder,
                    action=action,
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": False,
                "error": str(exc),
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": findings_count,
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                findings_count=findings_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                    recognize_persons=bool(recognize_persons),
                    skip_unknown_persons=bool(skip_unknown_persons),
                    findings_count=findings_count,
                ),
            )

    def list_files(self, *, base_path: str, pattern: str = "*") -> Dict[str, object]:
        if pattern == "__configured_images__":
            files = self.files.listImageFiles(base_path=base_path)
        else:
            files = self.files.list_files(base_path=base_path, pattern=pattern)
        return {"count": len(files), "files": files}

    def getFaceMatchFindingEntries(
        self,
        *,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
        action: str = "",
        auto: bool = False,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.get_finding_entries(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            action=action,
            auto=auto,
            refresh=refresh,
        )

    def getFaceMatchFindingEntriesLocked(
        self,
        *,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
        action: str = "",
        auto: bool = False,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.get_finding_entries_locked(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            action=action,
            auto=auto,
            refresh=refresh,
        )

    def removeFaceMatchFindingMetadataEntry(
        self,
        *,
        image_path: str,
        metadata_face: Dict[str, Any],
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.remove_metadata_entry(
            image_path=image_path,
            metadata_face=metadata_face,
            increment_transferred_count=increment_transferred_count,
        )

    def _removeFaceMatchFindingMetadataEntryUnlocked(
        self,
        *,
        image_path: str,
        metadata_face: Dict[str, Any],
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.remove_metadata_entry_unlocked(
            image_path=image_path,
            metadata_face=metadata_face,
            increment_transferred_count=increment_transferred_count,
        )

    def removeFaceMatchFindingEntry(
        self,
        *,
        face_id: int,
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.remove_entry(
            face_id=face_id,
            increment_transferred_count=increment_transferred_count,
        )

    def _removeFaceMatchFindingEntryUnlocked(
        self,
        *,
        face_id: int,
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        return self.face_match_workflow.remove_entry_unlocked(
            face_id=face_id,
            increment_transferred_count=increment_transferred_count,
        )

    def read_file_text(self, *, path: str, max_bytes: int = 1024 * 1024) -> Dict[str, object]:
        return self.files.read_text(path=path, max_bytes=max_bytes)

    def getSharedFolder(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        folder_name: str = "photo",
    ) -> Optional[str]:
        return self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name=folder_name,
        )


    def _resolvePhotosPersonLookupName(self, person_name: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        requested_name = str(person_name or "").strip()
        lookup_name = requested_name
        mapped_assignment = self.name_mappings.findNameMapping(requested_name)
        if isinstance(mapped_assignment, dict):
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
            if mapped_target_name:
                lookup_name = mapped_target_name
        else:
            mapped_assignment = None
        return requested_name, lookup_name, mapped_assignment

    def resolveOrCreatePhotosPersonForExistingFace(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_id: int,
        person_name: str,
        item_id: Optional[int] = None,
        create_missing_person: bool = False,
    ) -> Dict[str, Any]:
        requested_name, lookup_name, mapped_assignment = self._resolvePhotosPersonLookupName(person_name)
        if not lookup_name:
            return {
                "updated": False,
                "warning": "checks:warning_target_person_not_found",
                "operation": "photos_lookup",
                "details": {"requested_name": requested_name, "lookup_name": lookup_name},
            }

        target_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
        )
        if isinstance(target_person, dict):
            try:
                target_person_id = int(target_person.get("id"))
            except (TypeError, ValueError):
                target_person_id = None
            if target_person_id is not None:
                resolved_name = str(target_person.get("name") or lookup_name)
                assign_result = self.assignMatchedFaceToKnownPerson(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    face_id=int(face_id),
                    person_id=target_person_id,
                    person_name=resolved_name,
                    item_id=item_id,
                    image_path=image_path,
                )
                return {
                    "updated": True,
                    "warning": "",
                    "operation": "photos_assign",
                    "assign_result": assign_result,
                    "create_result": None,
                    "target_person": {"id": target_person_id, "name": resolved_name},
                    "resolved_name": resolved_name,
                    "requested_name": requested_name,
                    "name_mapping": mapped_assignment,
                }

        if create_missing_person:
            create_result = self.createMatchedFaceAsPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=int(face_id),
                person_name=lookup_name,
                item_id=item_id,
                image_path=image_path,
            )
            created_person_id = self._extractPersonId(create_result)
            if created_person_id is None:
                return {
                    "updated": False,
                    "warning": "checks:warning_target_person_create_failed",
                    "operation": "photos_create",
                    "create_result": create_result,
                    "details": {"requested_name": requested_name, "lookup_name": lookup_name},
                    "resolved_name": lookup_name,
                    "name_mapping": mapped_assignment,
                }
            return {
                "updated": True,
                "warning": "",
                "operation": "photos_create",
                "create_result": create_result,
                "assign_result": None,
                "target_person": {"id": int(created_person_id), "name": lookup_name},
                "resolved_name": lookup_name,
                "requested_name": requested_name,
                "name_mapping": mapped_assignment,
            }

        return {
            "updated": False,
            "warning": "checks:warning_target_person_not_found",
            "operation": "photos_lookup",
            "details": {"requested_name": requested_name, "lookup_name": lookup_name},
            "resolved_name": lookup_name,
            "name_mapping": mapped_assignment,
        }

    def resolveOrCreatePhotosPersonForMetadataFace(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        metadata_face: Dict[str, Any],
        person_name: str,
        create_missing_person: bool = False,
    ) -> Dict[str, Any]:
        requested_name, lookup_name, mapped_assignment = self._resolvePhotosPersonLookupName(person_name)
        if not lookup_name:
            return {
                "updated": False,
                "warning": "checks:warning_target_person_not_found",
                "operation": "photos_lookup",
                "details": {"requested_name": requested_name, "lookup_name": lookup_name},
            }

        target_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
        )
        if isinstance(target_person, dict):
            try:
                target_person_id = int(target_person.get("id"))
            except (TypeError, ValueError):
                target_person_id = None
            if target_person_id is not None:
                resolved_name = str(target_person.get("name") or lookup_name)
                add_result = self.addMatchedMetadataFaceToPhotos(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    image_path=image_path,
                    metadata_face=metadata_face,
                    person_id=target_person_id,
                )
                face_id = add_result.get("face_id") if isinstance(add_result, dict) else None
                if face_id is None:
                    raise ValueError("photos_face_create_failed")
                if self._metadataFaceAddAlreadyAssignedToPerson(add_result, target_person_id):
                    assign_result = {
                        "skipped": True,
                        "reason": "already_assigned_by_add_face",
                        "person_id": target_person_id,
                    }
                else:
                    assign_result = self.assignMatchedFaceToKnownPerson(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        face_id=int(face_id),
                        person_id=target_person_id,
                        person_name=resolved_name,
                        item_id=add_result.get("item_id") if isinstance(add_result, dict) and add_result.get("item_id") is not None else None,
                        image_path=image_path,
                    )
                return {
                    "updated": True,
                    "warning": "",
                    "operation": "photos_add_assign",
                    "add_result": add_result,
                    "assign_result": assign_result,
                    "create_result": None,
                    "target_person": {"id": target_person_id, "name": resolved_name},
                    "face_id": int(face_id),
                    "resolved_name": resolved_name,
                    "requested_name": requested_name,
                    "name_mapping": mapped_assignment,
                }

        if create_missing_person:
            create_result = self.createMetadataFaceAsPhotosPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                image_path=image_path,
                metadata_face=metadata_face,
                person_name=lookup_name,
            )
            created_person_id = self._extractPersonId(create_result)
            if created_person_id is None and isinstance(create_result, dict):
                try:
                    created_person_id = int(create_result.get("person_id"))
                except (TypeError, ValueError):
                    created_person_id = None
            if created_person_id is None:
                return {
                    "updated": False,
                    "warning": "checks:warning_target_person_create_failed",
                    "operation": "photos_create_from_metadata",
                    "create_result": create_result,
                    "details": {"requested_name": requested_name, "lookup_name": lookup_name},
                    "resolved_name": lookup_name,
                    "name_mapping": mapped_assignment,
                }
            return {
                "updated": True,
                "warning": "",
                "operation": "photos_create_from_metadata",
                "create_result": create_result,
                "target_person": {"id": int(created_person_id), "name": lookup_name},
                "face_id": create_result.get("face_id") if isinstance(create_result, dict) else None,
                "resolved_name": lookup_name,
                "requested_name": requested_name,
                "name_mapping": mapped_assignment,
            }

        return {
            "updated": False,
            "warning": "checks:warning_target_person_not_found",
            "operation": "photos_lookup",
            "details": {"requested_name": requested_name, "lookup_name": lookup_name},
            "resolved_name": lookup_name,
            "name_mapping": mapped_assignment,
        }

    def applyPhotoFaceMatchAssignment(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
        save_mapping: bool = False,
        source_name: Any = "",
    ) -> Dict[str, Any]:
        return self.face_match_mutations.apply_photo_face_assignment(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=person_id,
            person_name=person_name,
            save_mapping=save_mapping,
            source_name=source_name,
        )

    def applyPhotoFaceMatchPersonCreation(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
        save_mapping: bool = False,
        source_name: Any = "",
    ) -> Dict[str, Any]:
        return self.face_match_mutations.apply_photo_face_person_creation(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_name=person_name,
            save_mapping=save_mapping,
            source_name=source_name,
        )

    def assignMatchedFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
        item_id: Optional[int] = None,
        image_path: str = "",
    ) -> Dict[str, Any]:
        started = monotonic()
        with self._writeOperationLock(
            self._photosFaceWriteLockKey(face_id),
            phase="photos_face_assign",
            context={
                "face_id": face_id,
                "item_id": item_id,
                "image_path": str(image_path or "").strip(),
                "person_id": person_id,
                "person_name": person_name,
            },
        ):
            before_face = None
            if item_id is not None:
                precheck_started = monotonic()
                before_face = self._validatePhotosFaceOnItem(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=int(item_id),
                    face_id=int(face_id),
                    phase="photos_face_assign_precheck",
                    image_path=image_path,
                )
                self._debugLog(
                    "photos_face_assign_phase",
                    phase="precheck",
                    duration_ms=round((monotonic() - precheck_started) * 1000, 2),
                    face_id=face_id,
                    item_id=item_id,
                )
            api_started = monotonic()
            result = self.photos.assignFaceToPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=face_id,
                person_id=person_id,
                person_name=person_name,
            )
            self._debugLog(
                "photos_face_assign_phase",
                phase="photos_api_assign",
                duration_ms=round((monotonic() - api_started) * 1000, 2),
                face_id=face_id,
                person_id=person_id,
                success=bool(result.get("success", True)) if isinstance(result, dict) else None,
            )
            if item_id is not None:
                postcheck_started = monotonic()
                self._validatePhotosFaceOnItem(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=int(item_id),
                    face_id=int(face_id),
                    phase="photos_face_assign_postcheck",
                    image_path=image_path,
                    expected_person_id=int(person_id),
                    before=before_face,
                )
                self._debugLog(
                    "photos_face_assign_phase",
                    phase="postcheck",
                    duration_ms=round((monotonic() - postcheck_started) * 1000, 2),
                    face_id=face_id,
                    item_id=item_id,
                    person_id=person_id,
                )
            self._debugLog(
                "photos_face_assign_end",
                duration_ms=round((monotonic() - started) * 1000, 2),
                face_id=face_id,
                person_id=person_id,
                item_id=item_id,
            )
            return result

    def assignChecksFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_data: Dict[str, Any],
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        source_format = str(face_data.get("source_format") or "").strip().upper()
        if source_format == "PHOTOS":
            face_id = face_data.get("face_id")
            if face_id is None:
                raise ValueError("photos_face_id_missing")
            return {
                "updated": True,
                "metadata_result": None,
                "add_result": None,
                "assign_result": self.assignMatchedFaceToKnownPerson(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    face_id=int(face_id),
                    person_id=person_id,
                    person_name=person_name,
                    item_id=face_data.get("item_id") if face_data.get("item_id") is not None else None,
                    image_path=image_path,
                ),
            }

        metadata_result = self.replaceMetadataFaceName(
            image_path=image_path,
            face_data=face_data,
            new_name=person_name,
        )
        if not metadata_result.get("updated"):
            return {
                "updated": False,
                "warning": metadata_result.get("warning"),
                "metadata_result": metadata_result,
                "add_result": None,
                "assign_result": None,
            }

        add_result = self.addMatchedMetadataFaceToPhotos(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path=image_path,
            metadata_face=face_data,
            person_id=person_id,
        )
        face_id = add_result.get("face_id")
        if face_id is None:
            raise ValueError("photos_face_create_failed")
        assign_result = self.assignMatchedFaceToKnownPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=int(face_id),
            person_id=person_id,
            person_name=person_name,
            item_id=add_result.get("item_id") if add_result.get("item_id") is not None else None,
            image_path=image_path,
        )
        return {
            "updated": True,
            "warning": "",
            "metadata_result": metadata_result,
            "add_result": add_result,
            "assign_result": assign_result,
        }

    def assignMetadataFaceToKnownPhotosPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        metadata_face: Dict[str, Any],
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        add_result = self.addMatchedMetadataFaceToPhotos(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path=image_path,
            metadata_face=metadata_face,
            person_id=person_id,
        )
        face_id = add_result.get("face_id")
        if face_id is None:
            raise ValueError("photos_face_create_failed")
        if self._metadataFaceAddAlreadyAssignedToPerson(add_result, person_id):
            assign_result = {
                "skipped": True,
                "reason": "already_assigned_by_add_face",
                "person_id": int(person_id),
            }
        else:
            assign_result = self.assignMatchedFaceToKnownPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=int(face_id),
                person_id=person_id,
                person_name=person_name,
                item_id=add_result.get("item_id") if isinstance(add_result, dict) and add_result.get("item_id") is not None else None,
                image_path=image_path,
            )
        return {
            "image_path": image_path,
            "person_id": int(person_id),
            "person_name": person_name,
            "face_id": int(face_id),
            "add_result": add_result,
            "assign_result": assign_result,
        }

    @staticmethod
    def _metadataFaceAddAlreadyAssignedToPerson(add_result: Any, person_id: Any) -> bool:
        if not isinstance(add_result, dict) or not bool(add_result.get("created")):
            return False
        try:
            added_person_id = int(add_result.get("person_id"))
            expected_person_id = int(person_id)
        except (TypeError, ValueError):
            return False
        return added_person_id == expected_person_id

    def createMetadataFaceAsPhotosPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        metadata_face: Dict[str, Any],
        person_name: str,
    ) -> Dict[str, Any]:
        normalized_person_name = str(person_name or "").strip()
        if not normalized_person_name:
            raise ValueError("invalid_person_name")
        add_result = self.addMatchedMetadataFaceToPhotos(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path=image_path,
            metadata_face=metadata_face,
            person_name=normalized_person_name,
        )
        face_id = add_result.get("face_id")
        if face_id is None:
            raise ValueError("photos_face_create_failed")
        return {
            "image_path": image_path,
            "person_name": normalized_person_name,
            "face_id": int(face_id),
            "person_id": add_result.get("person_id"),
            "add_result": add_result,
            "create_result": None,
        }

    def replaceChecksFaceName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_data: Dict[str, Any],
        new_name: str,
        create_missing_person: bool = False,
    ) -> Dict[str, Any]:
        source_format = str(face_data.get("source_format") or "").strip().upper()
        replacement_name = str(new_name or "").strip()
        if source_format != "PHOTOS":
            result = self.replaceMetadataFaceName(
                image_path=image_path,
                face_data=face_data,
                new_name=replacement_name,
            )
            result["operation"] = "metadata_write"
            return result

        face_id = face_data.get("face_id")
        try:
            face_id = int(face_id)
        except (TypeError, ValueError):
            return {
                "updated": False,
                "warning": "checks:warning_photos_face_id_missing",
            }

        return self.resolveOrCreatePhotosPersonForExistingFace(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path=image_path,
            face_id=int(face_id),
            person_name=replacement_name,
            item_id=face_data.get("item_id") if face_data.get("item_id") is not None else None,
            create_missing_person=create_missing_person,
        )

    @staticmethod
    def _metadataFaceToPhotosBoundingBox(face: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        normalized_face = to_display_face(face if isinstance(face, dict) else {})
        left = float(normalized_face.get("x") or 0) - (float(normalized_face.get("w") or 0) / 2)
        top = float(normalized_face.get("y") or 0) - (float(normalized_face.get("h") or 0) / 2)
        right = left + float(normalized_face.get("w") or 0)
        bottom = top + float(normalized_face.get("h") or 0)
        return {
            "top_left": {
                "x": max(0.0, min(1.0, left)),
                "y": max(0.0, min(1.0, top)),
            },
            "bottom_right": {
                "x": max(0.0, min(1.0, right)),
                "y": max(0.0, min(1.0, bottom)),
            },
        }

    def _requestMissingPhotosItemReindex(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
    ) -> Dict[str, Any]:
        normalized_path = str(image_path or "").strip()
        photos_config = self.config.readMergedConfig().get("photos", {})
        if not isinstance(photos_config, dict) or not bool(photos_config.get("REINDEX_MISSING_ITEMS", False)):
            return {"status": "disabled", "requested": False, "path": normalized_path}
        if not normalized_path or not os.path.isfile(normalized_path):
            return {"status": "skipped", "requested": False, "reason": "file_not_found", "path": normalized_path}
        try:
            result = self.photos.indexFotoTeamPaths(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                paths=[normalized_path],
                index_type="basic",
            )
        except Exception as exc:
            self._debugLog(
                "photos_missing_item_reindex_failed",
                image_path=normalized_path,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return {
                "status": "failed",
                "requested": True,
                "path": normalized_path,
                "type": "basic",
                "error": str(exc),
            }
        self.photos_lookup_cache = PhotosLookupCache()
        self._debugLog("photos_missing_item_reindex_submitted", image_path=normalized_path, index_type="basic")
        return {
            "status": "submitted",
            "requested": True,
            "path": normalized_path,
            "type": "basic",
            "result": result,
        }

    def addMatchedMetadataFaceToPhotos(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        metadata_face: Dict[str, Any],
        person_id: Optional[int] = None,
        person_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        if not shared_folder:
            raise ValueError("shared_folder_not_found")

        item = self.photos.findFotoTeamItemByPath(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=image_path,
            additional=["thumbnail"],
            lookup_cache=self.photos_lookup_cache,
        )
        if not isinstance(item, dict) or item.get("id") is None:
            reindex = self._requestMissingPhotosItemReindex(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                image_path=image_path,
            )
            raise ImgDataOperationError(
                "photos_item_not_found_for_image",
                {
                    "reason": "photos_item_not_found_for_image",
                    "image_path": str(image_path or "").strip(),
                    "reindex": reindex,
                },
            )

        item_id = int(item.get("id"))
        metadata_face_obj = MetadataFace.from_dict(metadata_face)
        with self._writeOperationLock(
            self._photosItemWriteLockKey(item_id),
            phase="photos_face_create_from_metadata",
            context={
                "image_path": str(image_path or "").strip(),
                "item_id": item_id,
                "person_id": int(person_id) if person_id is not None else None,
                "person_name": str(person_name or "").strip(),
                "metadata_face_name": str(metadata_face_obj.name or "").strip(),
                "metadata_face_source_format": str(metadata_face_obj.source_format or "").strip().upper(),
            },
        ):
            existing_faces = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id,
            )
            matched_existing = self._findExistingPhotosFaceMatch(
                metadata_face=metadata_face_obj,
                existing_faces=existing_faces,
            )
            if matched_existing is not None:
                return {
                    "created": False,
                    "face_id": int(matched_existing.get("face_id")),
                    "item_id": item_id,
                    "item": item,
                    "duplicate": True,
                    "existing_match": matched_existing,
                }

            face_id_temp = f"{item_id}-{int(monotonic() * 1000)}"
            add_result = self.photos.addFaceToItem(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id,
                face_bbox=self._metadataFaceToPhotosBoundingBox(metadata_face),
                face_id_temp=face_id_temp,
                person_id=int(person_id) if person_id is not None else None,
                person_name=str(person_name or "").strip() if person_id is None else None,
            )
            created_face_id = self._extractCreatedPhotosFaceId(
                add_result=add_result,
                face_id_temp=face_id_temp,
            )
            if created_face_id is None:
                created_face = self._findCreatedPhotosFaceAfterAdd(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=item_id,
                    metadata_face=metadata_face_obj,
                    before_faces=existing_faces,
                )
                if created_face is not None:
                    try:
                        created_face_id = int(created_face.get("face_id"))
                    except (TypeError, ValueError):
                        created_face_id = None
            if created_face_id is None:
                raise ImgDataOperationError(
                    "photos_face_create_failed",
                    {
                        "reason": "photos_face_create_returned_no_id",
                        "image_path": str(image_path or "").strip(),
                        "item_id": item_id,
                        "person_id": int(person_id) if person_id is not None else None,
                        "person_name": str(person_name or "").strip(),
                        "person_name_required_in_photos": bool(str(person_name or "").strip()),
                        "metadata_face_name": str(metadata_face_obj.name or "").strip(),
                        "metadata_face_source_format": str(metadata_face_obj.source_format or "").strip().upper(),
                        "face_id_temp": face_id_temp,
                        "add_result": add_result,
                        "readback_attempted": True,
                        "readback_found_face": False,
                    },
                )
        created_person_id = None
        if person_id is not None:
            created_person_id = int(person_id)
        elif str(person_name or "").strip():
            created_face = self._findCreatedPhotosFaceAfterAdd(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                item_id=item_id,
                metadata_face=metadata_face_obj,
                before_faces=[],
                attempts=1,
                delay_seconds=0.0,
            )
            if isinstance(created_face, dict):
                try:
                    created_person_id = int(created_face.get("person_id"))
                except (TypeError, ValueError):
                    created_person_id = None
        return {
            "created": True,
            "face_id": created_face_id,
            "person_id": created_person_id,
            "person_name": str(person_name or "").strip(),
            "item_id": item_id,
            "item": item,
            "result": add_result,
        }

    @staticmethod
    def _extractCreatedPhotosFaceId(
        *,
        add_result: Dict[str, Any],
        face_id_temp: str,
    ) -> Optional[int]:
        for entry in add_result.get("list", []) if isinstance(add_result.get("list"), list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("face_id_temp") or "") != face_id_temp:
                continue
            try:
                return int(entry.get("face_id"))
            except (TypeError, ValueError):
                return None
        return None

    def _findCreatedPhotosFaceAfterAdd(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        item_id: int,
        metadata_face: MetadataFace,
        before_faces: List[Dict[str, Any]],
        attempts: int = 3,
        delay_seconds: float = 0.25,
    ) -> Optional[Dict[str, Any]]:
        before_ids = set()
        for face in before_faces if isinstance(before_faces, list) else []:
            try:
                before_ids.add(int(face.get("face_id")))
            except (TypeError, ValueError):
                continue

        for attempt in range(max(1, int(attempts))):
            current_faces = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=int(item_id),
            )
            candidates = []
            for face in current_faces if isinstance(current_faces, list) else []:
                if not isinstance(face, dict) or not isinstance(face.get("bbox"), dict):
                    continue
                try:
                    face_id = int(face.get("face_id"))
                except (TypeError, ValueError):
                    continue
                if face_id in before_ids:
                    continue
                score = self._photosOverlapScore(from_xmp(metadata_face), from_photos(face))
                if score >= 0.5:
                    candidates.append((score, face))
            if candidates:
                candidates.sort(key=lambda entry: entry[0], reverse=True)
                return candidates[0][1]
            if attempt + 1 < max(1, int(attempts)):
                sleep(max(0.0, float(delay_seconds)))
        return None

    def _findExistingPhotosFaceMatch(
        self,
        *,
        metadata_face: MetadataFace,
        existing_faces: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        candidate_face = PhotosFace(
            face_id=0,
            person_id=0,
            bbox=from_xmp(metadata_face),
        )
        existing_file_faces: List[FileFace] = []
        existing_lookup: List[Dict[str, Any]] = []
        for existing_face in existing_faces:
            if not isinstance(existing_face, dict) or not isinstance(existing_face.get("bbox"), dict):
                continue
            existing_file_faces.append(
                FileFace(
                    name=str(existing_face.get("face_name") or ""),
                    bbox=from_photos(existing_face),
                    source="photos",
                    source_format="PHOTOS",
                )
            )
            existing_lookup.append(existing_face)
        if not existing_file_faces:
            return None

        existing_matches = self.face_matcher.match([candidate_face], existing_file_faces)
        if not existing_matches:
            candidate_bbox = from_xmp(metadata_face)
            overlap_matches: List[Tuple[float, Dict[str, Any]]] = []
            for existing_face in existing_lookup:
                overlap_score = self._photosOverlapScore(
                    candidate_bbox,
                    from_photos(existing_face),
                )
                if overlap_score >= 0.5:
                    overlap_matches.append((overlap_score, existing_face))
            if not overlap_matches:
                return None
            overlap_matches.sort(key=lambda entry: entry[0], reverse=True)
            return overlap_matches[0][1]

        matched_existing = max(existing_matches, key=lambda match: float(match.get("iou") or 0))
        return existing_lookup[matched_existing["file_face_index"]]

    @staticmethod
    def _photosOverlapScore(left: Any, right: Any) -> float:
        try:
            overlap_width = min(float(left.x2), float(right.x2)) - max(float(left.x1), float(right.x1))
            overlap_height = min(float(left.y2), float(right.y2)) - max(float(left.y1), float(right.y1))
        except (AttributeError, TypeError, ValueError):
            return 0.0
        if overlap_width <= 0 or overlap_height <= 0:
            return 0.0

        overlap_area = overlap_width * overlap_height
        left_area = max(0.0, float(left.x2) - float(left.x1)) * max(0.0, float(left.y2) - float(left.y1))
        right_area = max(0.0, float(right.x2) - float(right.x1)) * max(0.0, float(right.y2) - float(right.y1))
        smaller_area = min(left_area, right_area)
        if smaller_area <= 0:
            return 0.0
        return overlap_area / smaller_area

    def createMatchedFaceAsPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
        item_id: Optional[int] = None,
        image_path: str = "",
    ) -> Dict[str, Any]:
        with self._writeOperationLock(
            self._photosFaceWriteLockKey(face_id),
            phase="photos_person_create_from_face",
            context={
                "face_id": face_id,
                "item_id": item_id,
                "image_path": str(image_path or "").strip(),
                "person_name": person_name,
            },
        ):
            before_face = None
            if item_id is not None:
                before_face = self._validatePhotosFaceOnItem(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=int(item_id),
                    face_id=int(face_id),
                    phase="photos_person_create_from_face_precheck",
                    image_path=image_path,
                )
            result = self.photos.createPersonFromFace(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=face_id,
                person_name=person_name,
            )
            created_face = None
            if item_id is not None:
                created_face = self._validatePhotosFaceOnItem(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    item_id=int(item_id),
                    face_id=int(face_id),
                    phase="photos_person_create_from_face_postcheck",
                    image_path=image_path,
                    expected_person_id=self._extractPersonId(result),
                    before=before_face,
                )
            created_person_id = self._resolveCreatedPersonId(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                person_name=person_name,
                create_result=result,
                created_face=created_face,
            )
            if created_person_id is not None and isinstance(result, dict) and result.get("person_id") is None:
                result = {
                    **result,
                    "person_id": int(created_person_id),
                }
            return result

    def _listAllPhotoItemsForPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: int,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        offset = 0
        page_size = 200
        while True:
            page = self.photos.listFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                person_id=person_id,
                offset=offset,
                limit=page_size,
            )
            if not page:
                break
            items.extend([item for item in page if isinstance(item, dict)])
            if len(page) < page_size:
                break
            offset += page_size
        return items

    def _collectPhotoFaceIdsForPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: int,
    ) -> List[int]:
        face_ids: List[int] = []
        seen = set()
        for item in self._listAllPhotoItemsForPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            person_id=person_id,
        ):
            try:
                item_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            for face in self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id,
            ):
                try:
                    face_id = int(face.get("face_id"))
                    current_person_id = int(face.get("person_id"))
                except (TypeError, ValueError):
                    continue
                if current_person_id != int(person_id) or face_id in seen:
                    continue
                seen.add(face_id)
                face_ids.append(face_id)
        return face_ids

    @staticmethod
    def _extractPersonId(person_payload: Dict[str, Any]) -> Optional[int]:
        if not isinstance(person_payload, dict):
            return None
        candidates = [person_payload]
        if isinstance(person_payload.get("person"), dict):
            candidates.append(person_payload.get("person"))
        if isinstance(person_payload.get("list"), list):
            candidates.extend(item for item in person_payload.get("list") if isinstance(item, dict))
        for candidate in candidates:
            for key in ("id", "person_id"):
                try:
                    return int(candidate.get(key))
                except (TypeError, ValueError):
                    continue
        return None

    def _resolveCreatedPersonId(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_name: str,
        create_result: Dict[str, Any],
        created_face: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        person_id = self._extractPersonId(create_result)
        if person_id is not None:
            return person_id

        person_id = self._extractPersonId(created_face or {})
        if person_id is not None:
            return person_id

        created_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=person_name,
        )
        return self._extractPersonId(created_person or {})

    def _normalizePhotosPersonByMapping(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person: Dict[str, Any],
        known_persons: List[Dict[str, Any]],
        mapping_lookup: Dict[str, str],
    ) -> Dict[str, Any]:
        source_name = str(person.get("name") or "").strip()
        source_key = NameMappingService._normalize_name_value(source_name)
        target_name = str(mapping_lookup.get(source_key) or "").strip()
        if not source_name or not target_name:
            return {"updated": False, "faces_reassigned": 0}
        if NameMappingService._normalize_name_value(target_name) == source_key:
            return {"updated": False, "faces_reassigned": 0}

        try:
            source_person_id = int(person.get("id"))
        except (TypeError, ValueError):
            return {"updated": False, "faces_reassigned": 0}

        face_ids = self._collectPhotoFaceIdsForPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            person_id=source_person_id,
        )
        if not face_ids:
            return {"updated": False, "faces_reassigned": 0}

        target_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=target_name,
            known_persons=known_persons,
        )
        if target_person is not None:
            try:
                target_person_id = int(target_person.get("id"))
            except (TypeError, ValueError):
                target_person_id = None
        else:
            target_person_id = None

        if target_person_id is None:
            created_assignment = self.resolveOrCreatePhotosPersonForExistingFace(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                image_path="",
                face_id=face_ids[0],
                person_name=target_name,
                create_missing_person=True,
            )
            created_target_person = created_assignment.get("target_person") if isinstance(created_assignment, dict) else None
            if isinstance(created_target_person, dict):
                try:
                    target_person_id = int(created_target_person.get("id"))
                except (TypeError, ValueError):
                    target_person_id = None
            if target_person_id is None:
                return {"updated": False, "faces_reassigned": 0, "error": "photos_person_create_failed"}

            known_persons.append({"id": target_person_id, "name": target_name})
            remaining_face_ids = face_ids[1:]
            reassigned = 1
        else:
            remaining_face_ids = face_ids
            reassigned = 0

        for face_id in remaining_face_ids:
            self.assignMatchedFaceToKnownPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=int(face_id),
                person_id=int(target_person_id),
                person_name=target_name,
            )
            reassigned += 1

        return {
            "updated": reassigned > 0,
            "faces_reassigned": reassigned,
            "source_person_id": source_person_id,
            "target_person_id": int(target_person_id),
            "source_name": source_name,
            "target_name": target_name,
        }

    def startCleanupRun(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        targets: List[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        normalized_targets = self._normalizeCleanupTargets(targets)
        current = self.getCleanupProgress(user_key, normalized_action)
        state_key = self._cleanupStateKey(user_key, normalized_action)
        if current.get("running"):
            return current
        for candidate_action in self._cleanupActionOptions():
            if candidate_action == normalized_action:
                continue
            candidate_progress = self.getCleanupProgress(user_key, candidate_action)
            if self._isBlockingRunningProgress(candidate_progress):
                return self._buildStartBlockedByRunningOperationPayload(
                    candidate_progress,
                    requested_operation="cleanup",
                )
        running_operation = self._runningOperationProgress(user_key, exclude_operation="cleanup")
        if running_operation:
            return self._buildStartBlockedByRunningOperationPayload(
                running_operation,
                requested_operation="cleanup",
            )
        if normalized_action == FaceFrameStandardizationService.ACTION:
            return self.face_frame_standardization.start(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                options=options,
            )
        if normalized_action in FaceRecognitionService.ACTIONS:
            return self.face_recognition.start(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                action=normalized_action,
                options=options,
            )

        self._setCleanupProgressMessage(
            user_key,
            normalized_action,
            "cleanup:status_preparing",
            operation_id=f"cleanup-{normalized_action}-{uuid4().hex}",
            running=True,
            finished=False,
            stop_requested=False,
            targets=normalized_targets,
            mappings_count=len(self.name_mappings.readNameMappings()),
            persons_total=0,
            persons_scanned=0,
            persons_updated=0,
            faces_reassigned=0,
            files_scanned=0,
            files_updated=0,
            metadata_faces_updated=0,
            current_path="",
            current_name="",
            warning="",
        )

        worker = Thread(
            target=self._runCleanupNameNormalization,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "action": normalized_action,
                "targets": normalized_targets,
            },
            daemon=True,
        )
        self.runtime_state.values("cleanup_threads")[state_key] = worker
        worker.start()
        return self.getCleanupProgress(user_key, normalized_action)

    def _runCleanupNameNormalization(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        targets: List[str],
    ) -> None:
        normalized_action = self._normalizeCleanupAction(action)
        normalized_targets = self._normalizeCleanupTargets(targets)
        mappings = self.name_mappings.readNameMappings()
        mapping_lookup = self._normalizedNameMappingTable(mappings)
        if not mapping_lookup:
            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_no_mappings",
                running=False,
                finished=True,
                targets=normalized_targets,
                mappings_count=0,
            )
            return

        persons_scanned = 0
        persons_total = 0
        persons_updated = 0
        faces_reassigned = 0
        files_scanned = 0
        files_updated = 0
        metadata_faces_updated = 0
        warning = ""

        try:
            if "PHOTOS" in normalized_targets:
                known_persons = self.photos.listFotoTeamPersonKnown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    show_more=True,
                    show_hidden=False,
                )
                persons_total = len(known_persons)
                for person in list(known_persons):
                    if self._shouldStopCleanup(user_key, normalized_action):
                        self._setCleanupProgressMessage(
                            user_key,
                            normalized_action,
                            "cleanup:progress_stopped",
                            running=False,
                            finished=True,
                            stop_requested=True,
                            targets=normalized_targets,
                            mappings_count=len(mapping_lookup),
                            persons_total=persons_total,
                            persons_scanned=persons_scanned,
                            persons_updated=persons_updated,
                            faces_reassigned=faces_reassigned,
                            files_scanned=files_scanned,
                            files_updated=files_updated,
                            metadata_faces_updated=metadata_faces_updated,
                        )
                        return
                    persons_scanned += 1
                    current_name = str(person.get("name") or "").strip()
                    self._setCleanupProgressMessage(
                        user_key,
                        normalized_action,
                        "cleanup:progress_checking_person",
                        message_params={"count": persons_scanned, "name": current_name},
                        running=True,
                        finished=False,
                        targets=normalized_targets,
                        mappings_count=len(mapping_lookup),
                        persons_total=persons_total,
                        persons_scanned=persons_scanned,
                        persons_updated=persons_updated,
                        faces_reassigned=faces_reassigned,
                        files_scanned=files_scanned,
                        files_updated=files_updated,
                        metadata_faces_updated=metadata_faces_updated,
                        current_name=current_name,
                    )
                    result = self._normalizePhotosPersonByMapping(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        person=person,
                        known_persons=known_persons,
                        mapping_lookup=mapping_lookup,
                    )
                    if result.get("updated"):
                        persons_updated += 1
                        faces_reassigned += int(result.get("faces_reassigned") or 0)

            metadata_targets = [target for target in normalized_targets if target in {"ACD", "MICROSOFT", "MWG_REGIONS"}]
            if metadata_targets:
                if not self.exiftool_handler.isAvailable():
                    warning = "cleanup:warning_exiftool_required"
                else:
                    shared_folder = self.core.getSharedFolder(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        folder_name="photo",
                    )
                    candidate_paths = self.files.listImageFiles(shared_folder) if shared_folder else []
                    total_files = len(candidate_paths)
                    for image_path in candidate_paths:
                        if self._shouldStopCleanup(user_key, normalized_action):
                            self._setCleanupProgressMessage(
                                user_key,
                                normalized_action,
                                "cleanup:progress_stopped",
                                running=False,
                                finished=True,
                                stop_requested=True,
                                targets=normalized_targets,
                                mappings_count=len(mapping_lookup),
                                persons_total=persons_total,
                                persons_scanned=persons_scanned,
                                persons_updated=persons_updated,
                                faces_reassigned=faces_reassigned,
                                files_scanned=files_scanned,
                                files_updated=files_updated,
                                metadata_faces_updated=metadata_faces_updated,
                                total_files=total_files,
                            )
                            return
                        files_scanned += 1
                        self._setCleanupProgressMessage(
                            user_key,
                            normalized_action,
                            "cleanup:progress_checking_file",
                            message_params={"count": files_scanned, "total": total_files},
                            running=True,
                            finished=False,
                            targets=normalized_targets,
                            mappings_count=len(mapping_lookup),
                            persons_total=persons_total,
                            persons_scanned=persons_scanned,
                            persons_updated=persons_updated,
                            faces_reassigned=faces_reassigned,
                            files_scanned=files_scanned,
                            files_updated=files_updated,
                            metadata_faces_updated=metadata_faces_updated,
                            total_files=total_files,
                            current_path=image_path,
                            warning=warning,
                        )
                        result = self.normalizeMetadataFaceNamesFromMappings(
                            image_path=image_path,
                            target_formats=metadata_targets,
                            mapping_lookup=mapping_lookup,
                            should_stop=lambda: self._shouldStopCleanup(user_key, normalized_action),
                        )
                        if result.get("stopped"):
                            self._setCleanupProgressMessage(
                                user_key,
                                normalized_action,
                                "cleanup:progress_stopped",
                                running=False,
                                finished=True,
                                stop_requested=True,
                                targets=normalized_targets,
                                mappings_count=len(mapping_lookup),
                                persons_total=persons_total,
                                persons_scanned=persons_scanned,
                                persons_updated=persons_updated,
                                faces_reassigned=faces_reassigned,
                                files_scanned=files_scanned,
                                files_updated=files_updated,
                                metadata_faces_updated=metadata_faces_updated,
                                total_files=total_files,
                                current_path=image_path,
                                warning=warning,
                            )
                            return
                        if result.get("updated"):
                            files_updated += 1
                            metadata_faces_updated += int(result.get("updated_faces") or 0)

            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_finished",
                running=False,
                finished=True,
                stop_requested=False,
                targets=normalized_targets,
                mappings_count=len(mapping_lookup),
                persons_total=persons_total,
                persons_scanned=persons_scanned,
                persons_updated=persons_updated,
                faces_reassigned=faces_reassigned,
                files_scanned=files_scanned,
                files_updated=files_updated,
                metadata_faces_updated=metadata_faces_updated,
                warning=warning,
            )
        except Exception as exc:
            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_failed",
                running=False,
                finished=True,
                stop_requested=False,
                targets=normalized_targets,
                mappings_count=len(mapping_lookup),
                persons_total=persons_total,
                persons_scanned=persons_scanned,
                persons_updated=persons_updated,
                faces_reassigned=faces_reassigned,
                files_scanned=files_scanned,
                files_updated=files_updated,
                metadata_faces_updated=metadata_faces_updated,
                error=str(exc),
            )
        finally:
            self.runtime_state.values("cleanup_threads").pop(self._cleanupStateKey(user_key, normalized_action), None)

    def suggestPersonsByName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name_prefix: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.photos.suggestFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name_prefix=name_prefix,
            additional=["thumbnail"],
            limit=limit,
        )

    def saveNameMapping(
        self,
        *,
        source_name: str,
        target_name: str,
    ) -> bool:
        return self.name_mappings.saveNameMapping(
            source_name=source_name,
            target_name=target_name,
        )

    def listNameMappingsPage(self, *, search: str = "", page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        return self.name_mappings.listNameMappingsPage(
            search=search,
            page=page,
            page_size=page_size,
        )

    def deleteNameMapping(self, mapping_id: int) -> bool:
        return self.name_mappings.deleteNameMapping(mapping_id)

    def clearNameMappings(self) -> int:
        return self.name_mappings.clearNameMappings()

    def updateNameMappingTarget(self, mapping_id: int, target_name: str) -> bool:
        return self.name_mappings.updateNameMappingTarget(mapping_id, target_name)

    def getRuntimeConfig(self) -> Dict[str, Any]:
        return self.config.readMergedConfig()

    def saveRuntimeConfig(self, config: Dict[str, Any]) -> bool:
        return self.config.writeConfig(config)

    def setDebugLogger(self, logger: Optional[Callable[..., None]]) -> None:
        self._debug_logger = logger if callable(logger) else None

    def _debugLog(self, event: str, **fields: Any) -> None:
        logger = self._debug_logger
        if not callable(logger):
            return
        try:
            logger(event, **fields)
        except Exception:
            pass

    def _defaultInsightFaceModelRoot(self) -> Path:
        return (self.config._config_path.parent / "insightface_models").resolve()

    def _insightFaceConfig(self) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        pip_packages = config.get("pip_packages") if isinstance(config.get("pip_packages"), dict) else {}
        package_config = pip_packages.get("INSIGHTFACE") if isinstance(pip_packages.get("INSIGHTFACE"), dict) else {}
        return package_config

    def _configuredInsightFaceModelRoot(self) -> Path:
        package_config = self._insightFaceConfig()
        configured_root = str(package_config.get("MODEL_ROOT") or "").strip()
        if configured_root:
            return Path(configured_root).expanduser().resolve()
        return self._defaultInsightFaceModelRoot()

    def _configuredInsightFaceModelName(self, model_status: Optional[Dict[str, Any]] = None) -> str:
        package_config = self._insightFaceConfig()
        configured_name = str(package_config.get("MODEL_NAME") or "").strip()
        if configured_name:
            return configured_name
        status = model_status if isinstance(model_status, dict) else InsightFaceDetector.available_models(self._configuredInsightFaceModelRoot())
        models = status.get("models") if isinstance(status.get("models"), list) else []
        installed_names = {
            str(item.get("name") or "").strip()
            for item in models
            if isinstance(item, dict) and bool(item.get("installed"))
        }
        return sorted(installed_names)[0] if installed_names else ""

    def _recognitionImageMaxEdge(self) -> int:
        try:
            files = self.config.readMergedConfig().get("files", {})
            return max(0, min(20000, int(files.get("RECOGNITION_IMAGE_MAX_EDGE", 4096))))
        except Exception:
            return 4096

    @staticmethod
    def _sanitizeInsightFaceModelName(value: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in {"_", "-", "."} else "_"
            for ch in str(value or "").strip()
        ).strip("._")

    @staticmethod
    def _safeZipRelativeParts(member_name: str) -> Optional[List[str]]:
        normalized = str(member_name or "").replace("\\", "/").strip("/")
        if not normalized:
            return None
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            return None
        return parts

    def _deriveInsightFaceModelArchiveLayout(
        self,
        archive: zipfile.ZipFile,
        *,
        archive_name: str,
    ) -> Dict[str, Any]:
        file_entries = []
        top_level_parts = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = self._safeZipRelativeParts(info.filename)
            if not parts or parts[0].startswith("__MACOSX"):
                continue
            file_entries.append((info, parts))
            top_level_parts.append(parts[0])
        if not file_entries:
            raise ValueError("insightface_model_archive_empty")

        unique_top_levels = {part for part in top_level_parts if part}
        common_prefix = top_level_parts[0] if len(unique_top_levels) == 1 else ""
        model_name_source = common_prefix or Path(str(archive_name or "").strip()).stem
        model_name = self._sanitizeInsightFaceModelName(model_name_source)
        if not model_name:
            raise ValueError("insightface_model_name_invalid")

        normalized_entries = []
        for info, parts in file_entries:
            relative_parts = parts[1:] if common_prefix and len(parts) > 1 else parts
            if common_prefix and len(parts) == 1:
                continue
            if not relative_parts:
                continue
            normalized_entries.append((info, relative_parts))
        if not normalized_entries:
            raise ValueError("insightface_model_archive_empty")

        return {
            "model_name": model_name,
            "entries": normalized_entries,
        }

    def installInsightFaceModelArchive(
        self,
        *,
        archive_name: str,
        archive_bytes: bytes,
    ) -> Dict[str, Any]:
        if not archive_bytes:
            raise ValueError("insightface_model_archive_empty")

        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                layout = self._deriveInsightFaceModelArchiveLayout(archive, archive_name=archive_name)
                model_name = str(layout["model_name"])
                entries = list(layout["entries"])
                model_root = self._configuredInsightFaceModelRoot()
                model_store = InsightFaceDetector.model_store_dir(model_root)
                model_store.mkdir(parents=True, exist_ok=True)
                target_dir = model_store / model_name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                try:
                    for info, relative_parts in entries:
                        destination = target_dir.joinpath(*relative_parts)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info, "r") as source_handle, destination.open("wb") as target_handle:
                            shutil.copyfileobj(source_handle, target_handle)
                    onnx_files = sorted(path.name for path in target_dir.rglob("*.onnx") if path.is_file())
                    if not onnx_files:
                        raise ValueError("insightface_model_archive_has_no_onnx")
                except Exception:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    raise
        except zipfile.BadZipFile as exc:
            raise ValueError("insightface_model_archive_invalid_zip") from exc

        model_status = InsightFaceDetector.available_models(model_root)
        return {
            "root": str(model_root),
            "model_name": model_name,
            "model_status": model_status,
        }

    def deleteInsightFaceModel(
        self,
        *,
        model_name: str,
    ) -> Dict[str, Any]:
        normalized_name = self._sanitizeInsightFaceModelName(model_name)
        if not normalized_name:
            raise ValueError("insightface_model_name_invalid")
        model_root = self._configuredInsightFaceModelRoot()
        target_dir = InsightFaceDetector.model_store_dir(model_root) / normalized_name
        deleted = False
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
            deleted = True
        model_status = InsightFaceDetector.available_models(model_root)
        return {
            "root": str(model_root),
            "model_name": normalized_name,
            "deleted": deleted,
            "model_status": model_status,
        }

    def pipPackagesStatus(self) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        configured_packages = config.get("pip_packages") if isinstance(config.get("pip_packages"), dict) else {}
        status_file = self.config._config_path.parent / "pip_packages_status.json"
        try:
            install_status_payload = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            install_status_payload = {}
        install_status_packages = (
            install_status_payload.get("packages")
            if isinstance(install_status_payload, dict) and isinstance(install_status_payload.get("packages"), dict)
            else {}
        )
        package_specs = {
            "INSIGHTFACE": {
                "label": "InsightFace",
                "requirements_file": "requirements-optional-insightface.txt",
                "modules": [
                    {"package": "insightface", "module": "insightface.app"},
                    {"package": "onnxruntime", "module": "onnxruntime"},
                    {"package": "opencv-python-headless", "module": "cv2"},
                    {"package": "Pillow", "module": "PIL.Image"},
                    {"package": "pillow-heif", "module": "pillow_heif"},
                ],
                "conflicts": ["opencv-python", "opencv-contrib-python", "opencv-contrib-python-headless"],
            },
        }
        result: Dict[str, Any] = {}
        for key, spec in package_specs.items():
            configured = configured_packages.get(key) if isinstance(configured_packages.get(key), dict) else {}
            modules: List[Dict[str, Any]] = []
            installed = True
            for module_spec in spec["modules"]:
                package_name = str(module_spec["package"])
                module_name = str(module_spec["module"])
                import_error = ""
                found = False
                version = ""
                try:
                    version = importlib_metadata.version(package_name)
                except Exception:
                    version = ""
                spec_found = False
                try:
                    spec_found = importlib.util.find_spec(module_name) is not None
                except Exception as exc:
                    import_error = str(exc)
                if spec_found:
                    try:
                        importlib.import_module(module_name)
                        found = True
                    except importlib_metadata.PackageNotFoundError:
                        version = ""
                    except Exception as exc:
                        import_error = str(exc)
                installed = installed and found
                module_status = {
                    "package": package_name,
                    "module": module_name,
                    "installed": found,
                    "version": version,
                }
                if import_error:
                    module_status["import_error"] = import_error
                modules.append(module_status)
            result[key] = {
                "label": spec["label"],
                "enabled": bool(configured.get("ENABLED", False)),
                "install_on_start": bool(configured.get("INSTALL_ON_START", True)),
                "requirements_file": str(configured.get("REQUIREMENTS_FILE") or spec["requirements_file"]),
                "wheelhouse_enabled": True if key == "INSIGHTFACE" else bool(configured.get("WHEELHOUSE_ENABLED", False)),
                "wheelhouse_manifest_url": str(configured.get("WHEELHOUSE_MANIFEST_URL") or "").strip(),
                "wheelhouse_target": str(configured.get("WHEELHOUSE_TARGET") or "").strip(),
                "installed": installed,
                "install_status": install_status_packages.get(key) if isinstance(install_status_packages.get(key), dict) else {},
                "modules": modules,
                "conflicts": [
                    {"package": package_name, "version": version}
                    for package_name in spec.get("conflicts", [])
                    for version in [self._installedPythonPackageVersion(str(package_name))]
                    if version
                ],
            }
            if key == "INSIGHTFACE":
                model_root = self._configuredInsightFaceModelRoot()
                model_status = InsightFaceDetector.available_models(model_root)
                active_model_name = self._configuredInsightFaceModelName(model_status)
                result[key]["model_root_configured"] = str(configured.get("MODEL_ROOT") or "").strip()
                result[key]["model_name_configured"] = str(configured.get("MODEL_NAME") or "").strip()
                result[key]["model_status"] = model_status
                result[key]["active_model_name"] = active_model_name
                result[key]["status_blocks"] = self._insightFaceStatusBlocks()
        return {
            "packages": result,
            "status_file": str(status_file),
        }

    def pipWheelhousePackages(self, *, package_key: str = "INSIGHTFACE") -> Dict[str, Any]:
        package_key = self._normalizePipPackageKey(package_key)
        spec = self._pipPackageRuntimeSpec(package_key)
        manifest = self._downloadAndValidatePipWheelhouseManifest(spec)
        packages = []
        for entry in manifest.get("packages", []):
            if not isinstance(entry, dict):
                continue
            package_name = str(entry.get("name") or "").strip()
            if not package_name:
                continue
            installed_version = self._installedPythonPackageVersion(package_name)
            packages.append({
                "name": package_name,
                "file": str(entry.get("file") or "").strip(),
                "sha256": str(entry.get("sha256") or "").strip(),
                "size": int(entry.get("size") or 0),
                "installed": bool(installed_version),
                "installed_version": installed_version,
            })
        packages.sort(key=lambda item: item["name"])
        return {
            "package_key": package_key,
            "manifest_url": spec["manifest_url"],
            "target": spec["target"],
            "requirements_file": spec["requirements_file"],
            "packages": packages,
        }

    def installPipWheelhousePackage(self, *, package_key: str = "INSIGHTFACE", package_name: str, reinstall: bool = False) -> Dict[str, Any]:
        package_key = self._normalizePipPackageKey(package_key)
        selected_name = self._normalizePipPackageName(package_name)
        if not selected_name:
            raise ValueError("pip_package_name_required")
        spec = self._pipPackageRuntimeSpec(package_key)
        manifest = self._downloadAndValidatePipWheelhouseManifest(spec)
        package_entries = [
            entry for entry in manifest.get("packages", [])
            if isinstance(entry, dict) and self._normalizePipPackageName(entry.get("name")) == selected_name
        ]
        if not package_entries:
            raise ValueError("pip_package_not_in_wheelhouse")

        package_var = self.config._config_path.parent
        package_var.mkdir(parents=True, exist_ok=True)
        output_path = package_var / f"pip_manual_install_{package_key}_{selected_name}.log"
        pip_command = [sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--no-index"]
        if reinstall:
            pip_command.append("--force-reinstall")

        with tempfile.TemporaryDirectory(prefix=f"pip_{package_key}_{selected_name}_", dir=str(package_var)) as tmpdir:
            wheel_dir = Path(tmpdir)
            self._downloadPipWheelhouseAssets(manifest, spec["manifest_url"], wheel_dir)
            command = [*pip_command, "--find-links", str(wheel_dir), selected_name]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
            output = str(result.stdout or "")
            output_path.write_text(output, encoding="utf-8")

        status = "success" if result.returncode == 0 else "failed"
        message = "pip install completed" if result.returncode == 0 else (output[-900:].replace("\n", " ").strip() or "pip install failed")
        self._writePipPackageInstallStatus(package_key, spec["requirements_file"], status, message)
        return {
            "package_key": package_key,
            "package_name": selected_name,
            "reinstall": bool(reinstall),
            "status": status,
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "message": message,
            "output_path": str(output_path),
        }

    @staticmethod
    def _normalizePipPackageName(value: Any) -> str:
        return str(value or "").strip().lower().replace("_", "-")

    @staticmethod
    def _normalizePipPackageKey(value: Any) -> str:
        normalized = str(value or "INSIGHTFACE").strip().upper()
        if normalized not in {"INSIGHTFACE"}:
            raise ValueError("unsupported_pip_package")
        return normalized

    def _pipPackageRuntimeSpec(self, package_key: str) -> Dict[str, str]:
        package_key = self._normalizePipPackageKey(package_key)
        config = self.config.readMergedConfig()
        configured_packages = config.get("pip_packages") if isinstance(config.get("pip_packages"), dict) else {}
        configured = configured_packages.get(package_key) if isinstance(configured_packages.get(package_key), dict) else {}
        default_requirements = "requirements-optional-insightface.txt"
        manifest_url = str(configured.get("WHEELHOUSE_MANIFEST_URL") or "").strip()
        target = str(configured.get("WHEELHOUSE_TARGET") or "").strip()
        requirements_file = str(configured.get("REQUIREMENTS_FILE") or default_requirements).strip()
        if not manifest_url:
            raise ValueError("pip_wheelhouse_manifest_url_missing")
        if not target:
            raise ValueError("pip_wheelhouse_target_missing")
        if not requirements_file or "/" in requirements_file or "\\" in requirements_file:
            raise ValueError("pip_requirements_file_invalid")
        return {
            "package_key": package_key,
            "manifest_url": manifest_url,
            "target": target,
            "requirements_file": requirements_file,
        }

    def _downloadAndValidatePipWheelhouseManifest(self, spec: Dict[str, str]) -> Dict[str, Any]:
        with urllib.request.urlopen(spec["manifest_url"], timeout=60) as response:
            manifest_bytes = response.read()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("pip_wheelhouse_manifest_invalid")
        if str(manifest.get("target") or "").strip() != spec["target"]:
            raise ValueError("pip_wheelhouse_target_mismatch")
        manifest_requirements = str(manifest.get("requirements_file") or "").strip()
        compatible_requirements = {spec["requirements_file"]}
        if spec["package_key"] == "INSIGHTFACE":
            compatible_requirements.add("requirements-runtime-insightface.txt")
        if manifest_requirements not in compatible_requirements:
            raise ValueError("pip_wheelhouse_requirements_mismatch")
        packages = manifest.get("packages")
        if not isinstance(packages, list) or not packages:
            raise ValueError("pip_wheelhouse_manifest_packages_missing")
        return manifest

    @staticmethod
    def _downloadPipWheelhouseAssets(manifest: Dict[str, Any], manifest_url: str, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        base_url = manifest_url.rsplit("/", 1)[0].rstrip("/")
        for entry in manifest.get("packages", []):
            if not isinstance(entry, dict):
                raise ValueError("pip_wheelhouse_package_invalid")
            filename = str(entry.get("file") or "").strip()
            expected_hash = str(entry.get("sha256") or "").strip().lower()
            if not filename or not expected_hash:
                raise ValueError("pip_wheelhouse_package_incomplete")
            destination = target_dir / filename
            with urllib.request.urlopen(f"{base_url}/{filename}", timeout=180) as response:
                destination.write_bytes(response.read())
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if digest != expected_hash:
                raise ValueError("pip_wheelhouse_package_hash_mismatch")

    def _writePipPackageInstallStatus(self, package_key: str, requirements_file: str, status: str, message: str) -> None:
        status_path = self.config._config_path.parent / "pip_packages_status.json"
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        packages = payload.get("packages") if isinstance(payload.get("packages"), dict) else {}
        packages[package_key] = {
            "status": status,
            "success": status == "success",
            "requirements_file": requirements_file,
            "message": message,
            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
        }
        payload["packages"] = packages
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _generatedFaceRecognitionProfilesCount(self) -> int:
        try:
            profiles = self.face_recognition.profiles().get("profiles", [])
        except Exception:
            return 0
        return len(profiles) if isinstance(profiles, list) else 0

    def _insightFaceStatusBlocks(self) -> List[Dict[str, Any]]:
        return [{
            "key": "generated_face_profiles",
            "label_key": "status:pip_generated_face_profiles",
            "fallback_label": "Generated person profiles",
            "value": self._generatedFaceRecognitionProfilesCount(),
        }]

    @staticmethod
    def _installedPythonPackageVersion(package_name: str) -> str:
        try:
            return importlib_metadata.version(package_name)
        except Exception:
            return ""
