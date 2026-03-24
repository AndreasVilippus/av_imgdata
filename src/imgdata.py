#!/usr/bin/env python3
import os
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

from api.session_manager import SessionManager
from handler.core_handler import CoreHandler
from handler.file_handler import FileHandler
from handler.photos_handler import PhotosHandler
from models.file_face import FileFace
from models.photos_face import PhotosFace
from services.bbox_normalizer import from_photos, from_xmp, normalize_xmp_face
from services.config_service import ConfigService
from services.face_matcher import FaceMatcher
from services.file_analysis_service import FileAnalysisService
from services.name_mapping_service import NameMappingService


class ImgDataService:
    """Orchestrates business use-cases across Photos and file handlers."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.config = ConfigService()
        self.core = CoreHandler(session_manager)
        self.photos = PhotosHandler(session_manager, self.config)
        self.files = FileHandler(self.config)
        self.name_mappings = NameMappingService()
        self.face_matcher = FaceMatcher()
        self.file_analysis = FileAnalysisService()
        self._face_matching_progress: Dict[str, Dict[str, Any]] = {}
        self._face_matching_progress_lock = Lock()
        self._file_analysis_progress: Dict[str, Any] = {}
        self._file_analysis_progress_lock = Lock()
        self._file_analysis_thread: Optional[Thread] = None

    def update_session_context(
        self,
        *,
        user_key: str,
        base_url: str,
        kk_message: Optional[str] = None,
        synotoken: Optional[str] = None,
        account: Optional[str] = None,
    ) -> None:
        self.session_manager.update_context(
            user_key,
            base_url=base_url,
            kk_message=kk_message,
            synotoken=synotoken,
            account=account,
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

    def _setFaceMatchingProgress(self, user_key: str, **updates: Any) -> None:
        with self._face_matching_progress_lock:
            current = dict(self._face_matching_progress.get(user_key, {}))
            current.update(updates)
            self._face_matching_progress[user_key] = current

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

    def getFaceMatchingProgress(self, user_key: str) -> Dict[str, Any]:
        with self._face_matching_progress_lock:
            current = self._face_matching_progress.get(user_key, {})
            return dict(current) if isinstance(current, dict) else {}

    def requestStopFaceMatching(self, user_key: str) -> Dict[str, Any]:
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:progress_stopping",
            stop_requested=True,
        )
        return self.getFaceMatchingProgress(user_key)

    def _shouldStopFaceMatching(self, user_key: str) -> bool:
        progress = self.getFaceMatchingProgress(user_key)
        return bool(progress.get("stop_requested"))

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def _setFileAnalysisProgress(self, **updates: Any) -> None:
        with self._file_analysis_progress_lock:
            current = dict(self._file_analysis_progress)
            current.update(updates)
            self._file_analysis_progress = current

    def _normalizeFileAnalysisProgress(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        worker_alive = bool(self._file_analysis_thread and self._file_analysis_thread.is_alive())
        if current.get("running") and not worker_alive:
            current["running"] = False
            current["finished"] = True
            current["stopped"] = bool(current.get("stopped")) or current.get("status") != "finished"
            current["stop_requested"] = False
            if current.get("status") == "running":
                current["status"] = "stopped"
            if not current.get("finished_at"):
                current["finished_at"] = current.get("last_updated_at") or self._timestamp_now()
            if not current.get("message"):
                current["message"] = "Last file analysis is no longer running."
        return current

    def _enrichFileAnalysisProgressWithFindings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        findings = self.file_analysis.readDimensionMismatchFindings()
        if not isinstance(findings, dict):
            return current

        findings_count = int(findings.get("count") or 0)
        same_job = (
            not current.get("job_id")
            or not findings.get("job_id")
            or str(current.get("job_id")) == str(findings.get("job_id"))
        )
        if same_job and "files_with_mwg_dimension_mismatch" not in current and findings_count > 0:
            current["files_with_mwg_dimension_mismatch"] = findings_count
        return current

    def getFileAnalysisProgress(self) -> Dict[str, Any]:
        with self._file_analysis_progress_lock:
            current = dict(self._file_analysis_progress)
        if current:
            return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(current))
        latest = self.file_analysis.readLatestResult()
        if not isinstance(latest, dict):
            return {}
        return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(latest))

    def getFileAnalysisDimensionMismatchFindings(self) -> Dict[str, Any]:
        findings = self.file_analysis.readDimensionMismatchFindings()
        return findings if isinstance(findings, dict) else {}

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

    def _writeFileAnalysisDimensionMismatchFindings(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        findings: List[str],
    ) -> None:
        self.file_analysis.writeDimensionMismatchFindings(
            {
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": self._timestamp_now() if finished else "",
                "last_updated_at": self._timestamp_now(),
                "status": status,
                "shared_folder": shared_folder,
                "count": len(findings),
                "paths": list(findings),
            }
        )

    @staticmethod
    def _pickReviewFace(faces: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(faces, list):
            return None
        mwg_faces = [face for face in faces if isinstance(face, dict) and str(face.get("source_format") or "") == "MWG_REGIONS"]
        if not mwg_faces:
            return None
        named = [face for face in mwg_faces if str(face.get("name") or "").strip()]
        return dict(named[0] if named else mwg_faces[0])

    def _buildDimensionMismatchReviewItem(self, image_path: str) -> Optional[Dict[str, Any]]:
        analysis = self.files.analyzeImageFaceMetadata(image_path)
        if analysis.get("files_with_mwg_dimension_mismatch") != 1:
            return None

        review_face = self._pickReviewFace(analysis.get("faces") if isinstance(analysis.get("faces"), list) else [])
        if not review_face:
            return None

        applied_face = normalize_xmp_face(review_face)
        raw_face = dict(review_face)
        raw_face.pop("orientation", None)

        return {
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "raw_face": raw_face,
            "applied_face": applied_face,
            "face_name": str(review_face.get("name") or ""),
            "image_dimensions": analysis.get("image_dimensions") if isinstance(analysis.get("image_dimensions"), dict) else {},
            "applied_to_dimensions": analysis.get("mwg_applied_to_dimensions") if isinstance(analysis.get("mwg_applied_to_dimensions"), dict) else {},
            "image_orientation": analysis.get("image_orientation"),
            "mwg_applied_to_dimensions_matches_current": analysis.get("mwg_applied_to_dimensions_matches_current"),
        }

    def startDimensionMismatchCheck(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        source_mode: str,
    ) -> Dict[str, Any]:
        source_mode_normalized = str(source_mode or "findings").strip().lower()
        if source_mode_normalized not in {"findings", "scan"}:
            source_mode_normalized = "findings"

        if source_mode_normalized == "findings":
            findings_payload = self.getFileAnalysisDimensionMismatchFindings()
            paths = findings_payload.get("paths") if isinstance(findings_payload.get("paths"), list) else []
            mismatch_paths = [str(path) for path in paths if isinstance(path, str) and path]
        else:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            mismatch_paths = []
            if shared_folder:
                for image_path in self.files.listImageFiles(shared_folder):
                    analysis = self.files.analyzeImageFaceMetadata(image_path)
                    if analysis.get("files_with_mwg_dimension_mismatch") == 1:
                        mismatch_paths.append(image_path)

        items = []
        for image_path in mismatch_paths:
            item = self._buildDimensionMismatchReviewItem(image_path)
            if item:
                items.append(item)

        return {
            "source_mode": source_mode_normalized,
            "count": len(items),
            "items": items,
        }

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
        if error:
            payload["error"] = error
        return payload

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
        configured_extensions = self.files.configuredImageExtensions()
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

        if not shared_folder:
            self._writeFileAnalysisDimensionMismatchFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder="",
                status="failed",
                finished=True,
                findings=[],
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
                    focus_usages={},
                    extensions={},
                    formats={},
                    sources={},
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                )
            )
            self._file_analysis_thread = None
            return

        self._setFileAnalysisProgress(
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
            current_path="",
            extensions={},
            focus_usages={},
            formats={},
            sources={},
        )
        self._writeFileAnalysisDimensionMismatchFindings(
            job_id=job_id,
            started_at=started_at,
            shared_folder=shared_folder,
            status="running",
            finished=False,
            findings=[],
        )

        try:
            for dirpath, _, filenames in os.walk(shared_folder):
                directories_read += 1
                self._setFileAnalysisProgress(
                    directories_read=directories_read,
                    current_path=str(dirpath),
                    last_updated_at=self._timestamp_now(),
                )
                if self._shouldStopFileAnalysis():
                    self._writeFileAnalysisDimensionMismatchFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings=dimension_mismatch_paths,
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
                    self.file_analysis.writeDimensionMismatchFindings(
                        {
                            "job_id": job_id,
                            "status": "stopped",
                            "shared_folder": shared_folder,
                            "count": len(dimension_mismatch_paths),
                            "paths": dimension_mismatch_paths,
                        }
                    )
                    self._file_analysis_thread = None
                    return
                for filename in filenames:
                    current_path = str(Path(dirpath) / filename)
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
                        self._writeFileAnalysisDimensionMismatchFindings(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            status="stopped",
                            finished=True,
                            findings=dimension_mismatch_paths,
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
                        self._file_analysis_thread = None
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
                    self._writeFileAnalysisDimensionMismatchFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings=dimension_mismatch_paths,
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
                    self.file_analysis.writeDimensionMismatchFindings(
                        {
                            "job_id": job_id,
                            "status": "stopped",
                            "shared_folder": shared_folder,
                            "count": len(dimension_mismatch_paths),
                            "paths": dimension_mismatch_paths,
                        }
                    )
                    self._file_analysis_thread = None
                    return

                analysis = self.files.analyzeImageFaceMetadata(image_path)
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
                if analysis.get("files_with_mwg_dimension_mismatch"):
                    dimension_mismatch_paths.append(image_path)
                    self._writeFileAnalysisDimensionMismatchFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=dimension_mismatch_paths,
                    )

                faces_total += int(analysis.get("faces_total") or 0)
                faces_named += int(analysis.get("faces_named") or 0)
                faces_unnamed += int(analysis.get("faces_unnamed") or 0)
                for key, value in (analysis.get("focus_usages") or {}).items():
                    self._incrementCounter(focus_usage_counts, str(key), int(value))

                faces = analysis.get("faces") if isinstance(analysis.get("faces"), list) else []
                for face in faces:
                    name = str(face.get("name") or "").strip()
                    if name:
                        distinct_person_names.add(name.casefold())
                    self._incrementCounter(source_counts, str(face.get("source") or analysis.get("xmp_source") or "metadata"))
                    self._incrementCounter(format_counts, str(face.get("source_format") or face.get("format") or ""))

                self._setFileAnalysisProgress(
                    running=True,
                    finished=False,
                    stopped=False,
                    status="running",
                    phase="analysis",
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
                    focus_usages=self._nonZeroCounters(focus_usage_counts),
                    formats=self._nonZeroCounters(format_counts),
                    sources=self._nonZeroCounters(source_counts),
                )

                if files_analyzed % 25 == 0:
                    self._writeFileAnalysisDimensionMismatchFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=dimension_mismatch_paths,
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

            self._writeFileAnalysisDimensionMismatchFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="finished",
                finished=True,
                findings=dimension_mismatch_paths,
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
            self.file_analysis.writeDimensionMismatchFindings(
                {
                    "job_id": job_id,
                    "status": "finished",
                    "shared_folder": shared_folder,
                    "count": len(dimension_mismatch_paths),
                    "paths": dimension_mismatch_paths,
                }
            )
        except Exception as exc:
            self.file_analysis.writeDimensionMismatchFindings(
                {
                    "job_id": job_id,
                    "status": "failed",
                    "shared_folder": shared_folder,
                    "count": len(dimension_mismatch_paths),
                    "paths": dimension_mismatch_paths,
                }
            )
            failure_phase = "analysis" if files_matched_total else "discovery"
            self._writeFileAnalysisDimensionMismatchFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="failed",
                finished=True,
                findings=dimension_mismatch_paths,
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
            self._file_analysis_thread = None

    def startFileAnalysisDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        current = self.getFileAnalysisProgress()
        if current.get("running"):
            return current

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        started_at = self._timestamp_now()
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
        self._file_analysis_thread = worker
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
    ) -> Dict[str, Any]:
        known_persons_cache: Optional[List[Dict[str, Any]]] = None
        skip_face_ids_set = {
            int(face_id) for face_id in (skip_face_ids or [])
            if isinstance(face_id, int) or str(face_id).isdigit()
        }
        persons_read = 0
        images_read = 0
        faces_read = 0
        metadata_faces_read = 0
        transferred_count = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_photo_face_in_file",
            persons_read=0,
            images_read=0,
            faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=0,
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
                return {
                    "searched": False,
                    "person": None,
                    "image": None,
                    "face": None,
                    "metadata_face": None,
                    "image_path": None,
                    "error": "shared_folder_not_found",
                }

            unknown_persons: List[Dict[str, Any]] = self.photos.listFotoTeamPersonUnknown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                limit=limit,
                offset=offset,
                show_more=True,
                show_hidden=False,
            )
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_unknown_persons_loaded",
                message_params={"count": len(unknown_persons)},
                persons_total=len(unknown_persons),
            )

            for person in unknown_persons:
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
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
                )

                images = self.photos.listFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    person_id=person_id_int,
                    additional=['thumbnail'],
                )

                for image in images:
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
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
                    )

                    faces = self.photos.list_faceFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        id_item=image_id_int
                    )
                    for face in faces:
                        if self._shouldStopFaceMatching(user_key):
                            final_message_key = "face_match:progress_stopped"
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
                            }
                        faces_read += 1
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_face",
                            message_params={"count": faces_read},
                            faces_read=faces_read,
                            current_face_id=face.get("face_id"),
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
                        metadata_faces = self.files.readAllPersonsFromImage(image_path)
                        metadata_faces_read += len(metadata_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_metadata",
                            message_params={"count": images_read},
                            metadata_faces_read=metadata_faces_read,
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
                                    name=str(metadata_face.get("name") or ""),
                                    bbox=from_xmp(metadata_face),
                                    source=str(metadata_face.get("source") or "metadata"),
                                    source_format=str(metadata_face.get("source_format") or metadata_face.get("format") or ""),
                                ),
                            )
                            for metadata_index, metadata_face in enumerate(metadata_faces)
                            if isinstance(metadata_face, dict)
                        ]
                        file_faces = [entry[1] for entry in indexed_file_faces]
                        if not file_faces:
                            continue

                        matches = self.face_matcher.match([photo_face], file_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_match_candidates",
                            message_params={"face": faces_read, "count": len(matches)},
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
                        matched_name = str(matched.get("file_name") or "").strip()
                        if matched_name:
                            if known_persons_cache is None:
                                known_persons_cache = self.photos.listFotoTeamPersonKnown(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    additional=["thumbnail"],
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
                        final_message_key = "face_match:result_named_match"
                        final_message_params = {}
                        if matched_person:
                            final_message_key = "face_match:result_named_match_with_id"
                            final_message_params = {"id": matched_person.get("id")}

                        if auto and matched_person:
                            matched_person_id = matched_person.get("id") if isinstance(matched_person, dict) else None
                            matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                            if matched_person_id is not None and matched_person_name:
                                self.assignMatchedFaceToKnownPerson(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    face_id=face_id_int,
                                    person_id=int(matched_person_id),
                                    person_name=str(matched_person_name),
                                )
                                transferred_count += 1
                                final_message_key = "face_match:progress_auto_assigned"
                                final_message_params = {"count": transferred_count}
                                self._setFaceMatchingProgressMessage(
                                    user_key,
                                    final_message_key,
                                    message_params=final_message_params,
                                    transferred_count=transferred_count,
                                )
                                skip_face_ids_set.add(face_id_int)
                                continue

                        return {
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
                            "transferred_count": transferred_count,
                            "auto": auto,
                        }

            final_message_key = "face_match:result_no_match"
            final_message_params = {}
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                running=False,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                transferred_count=transferred_count,
            )

    def list_files(self, *, base_path: str, pattern: str = "*") -> Dict[str, object]:
        if pattern == "__configured_images__":
            files = self.files.listImageFiles(base_path=base_path)
        else:
            files = self.files.list_files(base_path=base_path, pattern=pattern)
        return {"count": len(files), "files": files}

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

    def assignMatchedFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        return self.photos.assignFaceToPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=person_id,
            person_name=person_name,
        )

    def createMatchedFaceAsPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        return self.photos.createPersonFromFace(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_name=person_name,
        )

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

    def getRuntimeConfig(self) -> Dict[str, Any]:
        return self.config.readMergedConfig()

    def saveRuntimeConfig(self, config: Dict[str, Any]) -> bool:
        return self.config.writeConfig(config)
