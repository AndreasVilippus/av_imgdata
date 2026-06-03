#!/usr/bin/env python3
from datetime import datetime, timezone
from threading import Lock, Thread
from time import monotonic
from typing import Any, Dict, List, Optional, Type
from uuid import uuid4

from api.session_manager import SessionBootstrapRequired, SessionManagerError
from handler.file_handler import SidecarLookupCache
from models.metadata_face import MetadataFace
from services.bbox_normalizer import to_display_face


class ChecksWorkflowService:
    def __init__(self, backend: Any, operation_error_type: Type[Exception]):
        self.backend = backend
        self._operation_error_type = operation_error_type
        self._candidate_paths_cache: Dict[str, Dict[str, Any]] = {}
        self._candidate_paths_cache_lock = Lock()

    def invalidate_candidate_paths_cache(self, user_key: str, check_type: Any) -> None:
        state_key = self.backend._checksStateKey(user_key, check_type)
        with self._candidate_paths_cache_lock:
            for key in list(self._candidate_paths_cache.keys()):
                if str(key).startswith(f"{state_key}:"):
                    self._candidate_paths_cache.pop(key, None)
            self._candidate_paths_cache.pop(state_key, None)

    def get_candidate_paths(
        self,
        *,
        user_key: str,
        check_type: Any,
        shared_folder: str,
        changed_since_days: int = 0,
        use_cache: bool = True,
    ) -> List[str]:
        backend = self.backend
        normalized_days = max(0, int(changed_since_days or 0))
        state_key = f"{backend._checksStateKey(user_key, check_type)}:days-{normalized_days}"
        normalized_shared_folder = str(shared_folder or "").strip()
        if not normalized_shared_folder:
            return []

        if use_cache:
            with self._candidate_paths_cache_lock:
                cached = self._candidate_paths_cache.get(state_key)
                if (
                    isinstance(cached, dict)
                    and str(cached.get("shared_folder") or "") == normalized_shared_folder
                    and isinstance(cached.get("paths"), list)
                ):
                    return list(cached.get("paths") or [])

        candidate_paths = backend.files.listImageFiles(normalized_shared_folder)
        if normalized_days > 0:
            cutoff_mtime_ns = int((datetime.now(timezone.utc).timestamp() - (normalized_days * 86400)) * 1_000_000_000)
            lookup_cache = SidecarLookupCache()
            changed_paths: List[str] = []
            for image_path in candidate_paths:
                normalized_path = str(image_path or "").strip()
                if not normalized_path:
                    continue
                if backend._fileChangedSince(normalized_path, cutoff_mtime_ns):
                    changed_paths.append(normalized_path)
                    continue
                sidecar_path = backend.files.findXmpForImage(normalized_path, lookup_cache=lookup_cache)
                if sidecar_path and backend._fileChangedSince(sidecar_path, cutoff_mtime_ns):
                    changed_paths.append(normalized_path)
            candidate_paths = changed_paths
        with self._candidate_paths_cache_lock:
            self._candidate_paths_cache[state_key] = {
                "shared_folder": normalized_shared_folder,
                "changed_since_days": normalized_days,
                "paths": list(candidate_paths),
            }
        return candidate_paths

    @staticmethod
    def build_resume_cursor(
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
        normalized_days = max(0, int(changed_since_days or 0))
        return {
            "path_index": max(0, int(path_index)),
            "pending_entries": list(pending_entries or []),
            "source_mode": str(source_mode or "scan"),
            "check_type": str(check_type or "dimension_issues"),
            "save_only": bool(save_only),
            "findings_count": max(0, int(findings_count)),
            "resolved_count": max(0, int(resolved_count)),
            "ignored_count": max(0, int(ignored_count)),
            "metrics_trusted": bool(metrics_trusted),
            "changed_since_days": normalized_days,
        }

    def build_scan_payload(
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
        normalized_days = max(0, int(changed_since_days or 0))
        return {
            "running": running,
            "finished": finished,
            "stop_requested": stop_requested,
            "source_mode": "scan",
            "check_type": check_type,
            "save_only": save_only,
            "changed_since_days": normalized_days,
            "files_scanned": files_scanned,
            "total_files": total_files,
            "findings_count": findings_count,
            "resolved_count": max(0, int(resolved_count)),
            "ignored_count": max(0, int(ignored_count)),
            "current_path": current_path,
            "result": result,
            "resume_cursor": self.build_resume_cursor(
                path_index=path_index,
                pending_entries=pending_entries,
                source_mode="scan",
                check_type=check_type,
                save_only=save_only,
                findings_count=findings_count,
                resolved_count=resolved_count,
                ignored_count=ignored_count,
                changed_since_days=normalized_days,
            ),
            "message_key": message_key,
            "message": message,
            "message_params": message_params or {},
        }

    @staticmethod
    def count_open_scan_findings(
        current_entry: Optional[Dict[str, Any]] = None,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        count = 0
        if isinstance(current_entry, dict) and current_entry:
            count += 1
        for entry in pending_entries or []:
            if isinstance(entry, dict) and entry:
                count += 1
        return count

    @staticmethod
    def mark_entries_manual_review_required(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        marked_entries: List[Dict[str, Any]] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            marked_entry = dict(entry)
            marked_entry["_manual_review_required"] = True
            marked_entries.append(marked_entry)
        return marked_entries

    @staticmethod
    def current_result_entry(progress: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        result = progress.get("result") if isinstance(progress, dict) and isinstance(progress.get("result"), dict) else {}
        entry = result.get("entry") if isinstance(result.get("entry"), dict) else None
        return entry if isinstance(entry, dict) and entry else None

    def trusted_resume_cursor(
        self,
        current_progress: Optional[Dict[str, Any]],
        *,
        check_type: str,
        save_only: bool,
        advance_current_result: bool = False,
    ) -> Dict[str, Any]:
        progress = current_progress if isinstance(current_progress, dict) else {}
        resume_cursor = progress.get("resume_cursor") if isinstance(progress.get("resume_cursor"), dict) else {}
        resolved_count = int(progress.get("resolved_count") or 0)
        ignored_count = int(progress.get("ignored_count") or 0)
        if (
            advance_current_result
            and str(check_type or "").strip().lower() == "name_conflicts"
            and self.current_result_entry(progress) is not None
        ):
            ignored_count += 1
        return self.build_resume_cursor(
            path_index=int(resume_cursor.get("path_index") or 0),
            pending_entries=resume_cursor.get("pending_entries") if isinstance(resume_cursor.get("pending_entries"), list) else [],
            source_mode=str(resume_cursor.get("source_mode") or "scan"),
            check_type=str(resume_cursor.get("check_type") or check_type or "dimension_issues"),
            save_only=bool(resume_cursor.get("save_only", save_only)),
            findings_count=int(progress.get("findings_count") or 0),
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            metrics_trusted=True,
        )

    def write_findings(
        self,
        *,
        check_type: str,
        status: str,
        shared_folder: str,
        source_mode: str,
        save_only: bool,
        entries: List[Dict[str, Any]],
    ) -> bool:
        backend = self.backend
        payload = {
            "status": status,
            "shared_folder": shared_folder,
            "source_mode": source_mode,
            "check_type": check_type,
            "save_only": save_only,
            "count": len(entries),
            "paths": sorted({
                str(entry.get("image_path") or "").strip()
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("image_path") or "").strip()
            }),
            "entries": entries,
            "finished_at": backend._timestamp_now(),
        }
        return backend.file_analysis.writeCheckFindings(check_type, payload)

    def resume_saved_entries(
        self,
        *,
        check_type: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not save_only or not isinstance(resume_cursor, dict):
            return []
        findings = self.backend.file_analysis.readCheckFindings(check_type)
        if str(findings.get("check_type") or check_type).strip().lower() != str(check_type or "").strip().lower():
            return []
        if not bool(findings.get("save_only")):
            return []
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        return self.append_unique_findings([], entries)

    def append_unique_findings(
        self,
        existing_entries: List[Dict[str, Any]],
        new_entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        seen_tokens = {
            token
            for token in (self.backend._checksEntryToken(entry) for entry in existing_entries)
            if token
        }
        for entry in new_entries:
            if not isinstance(entry, dict):
                continue
            token = self.backend._checksEntryToken(entry)
            if token and token in seen_tokens:
                continue
            if token:
                seen_tokens.add(token)
            existing_entries.append(entry)
        return existing_entries

    def write_persisted_findings_status(self, *, check_type: str, status: str, save_only: bool) -> None:
        if not save_only:
            return
        backend = self.backend
        with backend._checkFindingsLock(check_type):
            findings = backend.file_analysis.readCheckFindings(check_type)
            entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
            self.write_findings(
                check_type=check_type,
                status=status,
                shared_folder=str(findings.get("shared_folder") or ""),
                source_mode="scan",
                save_only=True,
                entries=[entry for entry in entries if isinstance(entry, dict)],
            )

    def get_finding_entries(self, *, check_type: str) -> Dict[str, Any]:
        findings = self.backend.file_analysis.readCheckFindings(check_type)
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        return {
            "status": str(findings.get("status") or ""),
            "check_type": str(findings.get("check_type") or check_type),
            "source_mode": str(findings.get("source_mode") or "findings"),
            "save_only": bool(findings.get("save_only")),
            "count": len(entries),
            "entries": entries,
        }

    def refresh_finding_entries(
        self,
        *,
        check_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        backend = self.backend
        normalized_type = backend._normalizeChecksType(check_type)
        with backend._checkFindingsLock(normalized_type):
            return self._refresh_finding_entries_unlocked(
                check_type=normalized_type,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )

    def _refresh_finding_entries_unlocked(
        self,
        *,
        check_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        backend = self.backend
        normalized_type = backend._normalizeChecksType(check_type)
        findings = backend.file_analysis.readCheckFindings(normalized_type)
        if not isinstance(findings, dict) or not isinstance(findings.get("entries"), list):
            return self.get_finding_entries(check_type=normalized_type)

        shared_folder = str(findings.get("shared_folder") or "")
        status = str(findings.get("status") or "finished")
        source_mode = str(findings.get("source_mode") or "findings")
        save_only = bool(findings.get("save_only"))
        stored_entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        candidate_paths: List[str] = []
        seen_paths = set()
        for entry in stored_entries:
            if not isinstance(entry, dict):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            if not image_path or image_path in seen_paths:
                continue
            seen_paths.add(image_path)
            candidate_paths.append(image_path)

        refreshed_entries: List[Dict[str, Any]] = []
        for image_path in candidate_paths:
            refreshed_entries.extend(
                backend._buildCheckEntriesForType(
                    image_path=image_path,
                    review_type=normalized_type,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
            )

        self.write_findings(
            check_type=normalized_type,
            status=status,
            shared_folder=shared_folder,
            source_mode=source_mode,
            save_only=save_only,
            entries=refreshed_entries,
        )
        return self.get_finding_entries(check_type=normalized_type)

    def refresh_finding_entries_for_image(
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
        backend = self.backend
        normalized_type = backend._normalizeChecksType(check_type)
        with backend._checkFindingsLock(normalized_type):
            return self._refresh_finding_entries_for_image_unlocked(
                check_type=normalized_type,
                image_path=image_path,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                original_face_data=original_face_data,
                replacement_face_data=replacement_face_data,
            )

    def _refresh_finding_entries_for_image_unlocked(
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
        backend = self.backend
        normalized_type = backend._normalizeChecksType(check_type)
        normalized_path = str(image_path or "").strip()
        if not normalized_path:
            return self.get_finding_entries(check_type=normalized_type)

        findings = backend.file_analysis.readCheckFindings(normalized_type)
        existing_entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        if not existing_entries:
            return self.get_finding_entries(check_type=normalized_type)

        photo_faces = backend._loadPhotoFacesForImageWithOverride(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=normalized_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )
        rebuilt_entries = backend._buildCheckEntriesForType(
            image_path=normalized_path,
            review_type=normalized_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            photo_faces=photo_faces,
        )

        updated_entries: List[Dict[str, Any]] = []
        replaced = False
        for entry in existing_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("image_path") or "").strip() == normalized_path:
                if not replaced:
                    updated_entries.extend(rebuilt_entries)
                    replaced = True
                continue
            updated_entries.append(entry)

        if not replaced:
            return self.get_finding_entries(check_type=normalized_type)

        self.write_findings(
            check_type=normalized_type,
            status=str(findings.get("status") or "finished"),
            shared_folder=str(findings.get("shared_folder") or ""),
            source_mode=str(findings.get("source_mode") or "findings"),
            save_only=bool(findings.get("save_only")),
            entries=updated_entries,
        )
        return self.get_finding_entries(check_type=normalized_type)

    def refresh_scan_progress_for_image(
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
        backend = self.backend
        normalized_type = backend._normalizeChecksType(check_type)
        normalized_path = str(image_path or "").strip()
        if not normalized_path:
            return backend.getChecksProgress(user_key, normalized_type)

        current = backend.getChecksProgress(user_key, normalized_type)
        if not isinstance(current, dict) or str(current.get("source_mode") or "").strip().lower() != "scan":
            return current

        resume_cursor = current.get("resume_cursor") if isinstance(current.get("resume_cursor"), dict) else {}
        pending_entries = resume_cursor.get("pending_entries") if isinstance(resume_cursor.get("pending_entries"), list) else []
        current_result = current.get("result") if isinstance(current.get("result"), dict) else {}
        current_entry = current_result.get("entry") if isinstance(current_result.get("entry"), dict) else {}

        photo_faces = backend._loadPhotoFacesForImageWithOverride(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=normalized_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )
        rebuilt_entries = backend._buildCheckEntriesForType(
            image_path=normalized_path,
            review_type=normalized_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            photo_faces=photo_faces,
        )
        processed_tokens: List[str] = []
        if isinstance(current_entry, dict) and str(current_entry.get("image_path") or "").strip() == normalized_path:
            current_entry_token = backend._checksEntryToken(current_entry)
            if current_entry_token:
                processed_tokens.append(current_entry_token)
        replacement_entries = backend._markChecksEntriesManualReviewRequired(
            backend._excludeChecksEntriesByTokens(rebuilt_entries, processed_tokens)
        )

        remaining_pending_entries: List[Dict[str, Any]] = []
        for entry in pending_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("image_path") or "").strip() == normalized_path:
                continue
            remaining_pending_entries.append(entry)
        remaining_pending_entries = replacement_entries + remaining_pending_entries

        findings_count = int(current.get("findings_count") or 0)
        resolved_count = int(current.get("resolved_count") or 0)
        ignored_count = int(current.get("ignored_count") or 0)
        resolved_count += max(0, int(resolved_delta or 0))
        ignored_count += max(0, int(ignored_delta or 0))

        updated_resume_cursor = backend._buildChecksResumeCursor(
            path_index=int(resume_cursor.get("path_index") or 0),
            pending_entries=remaining_pending_entries,
            source_mode=str(resume_cursor.get("source_mode") or "scan"),
            check_type=str(resume_cursor.get("check_type") or normalized_type),
            save_only=bool(resume_cursor.get("save_only", current.get("save_only"))),
            findings_count=findings_count,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
        )

        updated_progress = dict(current)
        updated_progress.update({
            "check_type": normalized_type,
            "findings_count": findings_count,
            "resolved_count": resolved_count,
            "ignored_count": ignored_count,
            "result": None,
            "resume_cursor": updated_resume_cursor,
        })
        backend._setChecksProgress(user_key, **updated_progress)
        return backend.getChecksProgress(user_key, normalized_type)

    def get_suggested_name_conflict_rename(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        backend = self.backend
        if not isinstance(item, dict) or str(item.get("review_type") or "").strip().lower() != "name_conflicts":
            return None

        left_state = str(item.get("left_state") or "").strip().lower()
        right_state = str(item.get("right_state") or "").strip().lower()
        left_face = item.get("left_face_target") if isinstance(item.get("left_face_target"), dict) else item.get("left_face")
        right_face = item.get("right_face_target") if isinstance(item.get("right_face_target"), dict) else item.get("right_face")
        left_name = str(item.get("left_name") or "").strip()
        right_name = str(item.get("right_name") or "").strip()

        if right_state == "suggested" and isinstance(left_face, dict) and right_name:
            return {
                "face": left_face,
                "new_name": right_name,
                "source_name": str(left_face.get("name") or "").strip(),
            }
        if left_state == "suggested" and isinstance(right_face, dict) and left_name:
            return {
                "face": right_face,
                "new_name": left_name,
                "source_name": str(right_face.get("name") or "").strip(),
            }
        return None

    def get_suggested_duplicate_face_deletion(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        backend = self.backend
        if not isinstance(item, dict) or str(item.get("review_type") or "").strip().lower() != "duplicate_faces":
            return None

        left_state = str(item.get("left_state") or "").strip().lower()
        right_state = str(item.get("right_state") or "").strip().lower()
        left_face = item.get("left_face_target") if isinstance(item.get("left_face_target"), dict) else item.get("left_face")
        right_face = item.get("right_face_target") if isinstance(item.get("right_face_target"), dict) else item.get("right_face")

        if left_state == "suggested" and right_state != "suggested" and isinstance(right_face, dict):
            return {
                "face": right_face,
                "kept_side": "left",
                "removed_side": "right",
            }
        if right_state == "suggested" and left_state != "suggested" and isinstance(left_face, dict):
            return {
                "face": left_face,
                "kept_side": "right",
                "removed_side": "left",
            }
        return None

    @staticmethod
    def stored_checks_face_from_entry(face: Any) -> Dict[str, Any]:
        if isinstance(face, MetadataFace):
            face = face.to_dict()
        if not isinstance(face, dict):
            return {}
        return dict(face)

    def build_stored_checks_review_item_from_entry(self, entry: Any) -> Optional[Dict[str, Any]]:
        backend = self.backend
        if not isinstance(entry, dict):
            return None
        review_type = str(entry.get("review_type") or "").strip().lower()
        image_path = str(entry.get("image_path") or "").strip()
        if not review_type or not image_path:
            return None

        if review_type in {"name_conflicts", "duplicate_faces", "position_deviations"}:
            left_face = backend._storedChecksFaceFromEntry(
                entry.get("left_face_target")
                or entry.get("left_face_signature")
                or entry.get("left_face")
            )
            right_face = backend._storedChecksFaceFromEntry(
                entry.get("right_face_target")
                or entry.get("right_face_signature")
                or entry.get("right_face")
            )
            if not left_face or not right_face:
                return None

            left_name = str(entry.get("left_name") or left_face.get("name") or entry.get("face_name") or "").strip()
            right_name = str(entry.get("right_name") or right_face.get("name") or entry.get("face_name") or "").strip()

            item = dict(entry)
            item.update({
                "review_type": review_type,
                "image_path": image_path,
                "left_name": left_name,
                "right_name": right_name,
                "left_format": str(left_face.get("source_format") or entry.get("left_format") or "").strip(),
                "right_format": str(right_face.get("source_format") or entry.get("right_format") or "").strip(),
                "left_source": str(left_face.get("source") or entry.get("left_source") or "").strip(),
                "right_source": str(right_face.get("source") or entry.get("right_source") or "").strip(),
                "left_face": to_display_face(left_face),
                "right_face": to_display_face(right_face),
                "left_face_target": left_face,
                "right_face_target": right_face,
                "left_face_signature": left_face,
                "right_face_signature": right_face,
                "left_state": str(entry.get("left_state") or "alert").strip() or "alert",
                "right_state": str(entry.get("right_state") or "alert").strip() or "alert",
                "left_alert_faces": list(entry.get("left_alert_faces") or []),
                "left_reference_faces": list(entry.get("left_reference_faces") or []),
                "right_alert_faces": list(entry.get("right_alert_faces") or []),
                "right_reference_faces": list(entry.get("right_reference_faces") or []),
                "from_stored_finding": True,
            })
            return item

        if review_type == "dimension_issues":
            item = dict(entry)
            item.setdefault("review_type", review_type)
            item.setdefault("image_path", image_path)
            item["from_stored_finding"] = True
            return item

        return None

    def resolve_checks_review_entry(self, *, entry: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        backend = self.backend
        resolved = backend._resolveChecksReviewEntryCore(entry=entry, **kwargs)
        if not isinstance(resolved, dict):
            return resolved

        if (
            resolved.get("entry") is None
            and resolved.get("item") is None
            and int(resolved.get("auto_applied_count") or 0) == 0
            and not resolved.get("stop_requested")
        ):
            stored_item = backend._buildStoredChecksReviewItemFromEntry(entry)
            if stored_item is not None:
                next_resolved = dict(resolved)
                next_resolved["entry"] = entry
                next_resolved["item"] = stored_item
                next_resolved["stale"] = False
                next_resolved["from_stored_finding"] = True
                return next_resolved

        return resolved

    def resolve_checks_review_entry_core(
        self,
        *,
        entry: Dict[str, Any],
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        include_item: bool = True,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        max_auto_apply_actions: Optional[int] = None,
    ) -> Dict[str, Any]:
        backend = self.backend
        normalized_entry = dict(entry or {})
        auto_applied_count = 0
        seen_entry_tokens = set()
        try:
            auto_apply_limit = int(max_auto_apply_actions) if max_auto_apply_actions is not None else backend.CHECKS_AUTO_APPLY_MAX_ACTIONS_PER_CALL
        except (TypeError, ValueError):
            auto_apply_limit = backend.CHECKS_AUTO_APPLY_MAX_ACTIONS_PER_CALL
        auto_apply_limit = max(1, auto_apply_limit)

        def auto_apply_limit_reached() -> bool:
            return auto_apply_limit > 0 and auto_applied_count >= auto_apply_limit

        def stop_requested() -> bool:
            review_type = str(normalized_entry.get("review_type") or "").strip().lower()
            return backend._shouldStopChecks(str(user_key or ""), review_type)

        def stopped_result() -> Dict[str, Any]:
            return {
                "entry": None,
                "item": None,
                "auto_applied_count": auto_applied_count,
                "processed_entry_tokens": list(seen_entry_tokens),
                "stop_requested": True,
                "finished": True,
            }

        while True:
            if stop_requested():
                return stopped_result()
            if not include_item and not auto_apply_suggested_names and not auto_apply_suggested_duplicates:
                return {
                    "entry": normalized_entry,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "finished": True,
                }
            item = backend.getChecksReviewItem(
                entry=normalized_entry,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if not item:
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "processed_entry_tokens": list(seen_entry_tokens),
                    "finished": True,
                }

            action = (
                backend._getSuggestedNameConflictRename(item)
                if auto_apply_suggested_names
                else None
            )
            delete_action = (
                backend._getSuggestedDuplicateFaceDeletion(item)
                if auto_apply_suggested_duplicates
                else None
            )
            if not action:
                if not delete_action:
                    return {
                        "entry": normalized_entry,
                        "item": item,
                        "auto_applied_count": auto_applied_count,
                        "processed_entry_tokens": list(seen_entry_tokens),
                        "finished": True,
                    }
            if delete_action:
                current_entry_token = backend._checksEntryToken(normalized_entry)
                if current_entry_token:
                    seen_entry_tokens.add(current_entry_token)
                result = backend.deleteMetadataFace(
                    image_path=str(item.get("image_path") or ""),
                    face_data=delete_action["face"],
                )
                if not result.get("deleted"):
                    return {
                        "entry": normalized_entry,
                        "item": item,
                        "auto_applied_count": auto_applied_count,
                        "auto_apply_warning": str(result.get("warning") or ""),
                        "finished": True,
                    }
                auto_applied_count += 1
                if auto_apply_limit_reached():
                    return {
                        "entry": None,
                        "item": None,
                        "auto_applied_count": auto_applied_count,
                        "processed_entry_tokens": list(seen_entry_tokens),
                        "auto_apply_limit_reached": True,
                        "finished": True,
                    }
                if stop_requested():
                    return stopped_result()
                if (
                    backend._isChecksFacePairType(item.get("review_type"))
                    and str(item.get("review_type") or "").strip().lower() != "name_conflicts"
                ):
                    return {
                        "entry": None,
                        "item": None,
                        "auto_applied_count": auto_applied_count,
                        "processed_entry_tokens": list(seen_entry_tokens),
                    }
                next_entry = next(
                    (
                        candidate
                        for candidate in backend._buildCheckEntriesForType(
                            image_path=str(item.get("image_path") or ""),
                            review_type=str(item.get("review_type") or ""),
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            shared_folder=shared_folder,
                        )
                        if backend._checksEntryToken(candidate) not in seen_entry_tokens
                    ),
                    None,
                )
                if not next_entry:
                    return {
                        "entry": None,
                        "item": None,
                        "auto_applied_count": auto_applied_count,
                        "processed_entry_tokens": list(seen_entry_tokens),
                    }
                normalized_entry = next_entry
                continue
            if not action:
                return {
                    "entry": normalized_entry,
                    "item": item,
                    "auto_applied_count": auto_applied_count,
                }

            result = backend.replaceChecksFaceName(
                user_key=str(user_key or ""),
                cookies=dict(cookies or {}),
                base_url=base_url,
                image_path=str(item.get("image_path") or ""),
                face_data=action["face"],
                new_name=str(action["new_name"] or ""),
            )
            current_entry_token = backend._checksEntryToken(normalized_entry)
            if current_entry_token:
                seen_entry_tokens.add(current_entry_token)
            if not result.get("updated"):
                return {
                    "entry": normalized_entry,
                    "item": item,
                    "auto_applied_count": auto_applied_count,
                    "auto_apply_warning": str(result.get("warning") or ""),
                    "finished": True,
                }

            auto_applied_count += 1
            if auto_apply_limit_reached():
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "processed_entry_tokens": list(seen_entry_tokens),
                    "auto_apply_limit_reached": True,
                }
            if stop_requested():
                return stopped_result()
            if str(item.get("review_type") or "").strip().lower() == "name_conflicts":
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "processed_entry_tokens": list(seen_entry_tokens),
                    "finished": True,
                }
            if (
                backend._isChecksFacePairType(item.get("review_type"))
                and str(item.get("review_type") or "").strip().lower() != "name_conflicts"
            ):
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "processed_entry_tokens": list(seen_entry_tokens),
                }
            next_entry = next(
                (
                    candidate
                    for candidate in backend._buildCheckEntriesForType(
                        image_path=str(item.get("image_path") or ""),
                        review_type=str(item.get("review_type") or ""),
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                    )
                    if backend._checksEntryToken(candidate) not in seen_entry_tokens
                ),
                None,
            )
            if not next_entry:
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                    "processed_entry_tokens": list(seen_entry_tokens),
                }
            normalized_entry = next_entry

    def exclude_checks_entries_by_tokens(
        self,
        entries: List[Dict[str, Any]],
        excluded_tokens: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        backend = self.backend
        normalized_tokens = {
            str(token or "").strip()
            for token in (excluded_tokens or [])
            if str(token or "").strip()
        }
        filtered_entries: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_token = backend._checksEntryToken(entry)
            if entry_token and entry_token in normalized_tokens:
                continue
            filtered_entries.append(entry)
        return filtered_entries

    def rebuild_checks_entries_for_image_after_mutation(
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
        backend = self.backend
        rebuilt_entries = backend._buildCheckEntriesForType(
            image_path=image_path,
            review_type=review_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
        )
        return backend._excludeChecksEntriesByTokens(rebuilt_entries, excluded_tokens)

    def search_next_item(
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
        backend = self.backend
        last_keepalive_at = monotonic()
        shared_folder = backend.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        if not shared_folder:
            return backend._buildChecksScanPayload(
                check_type=check_type,
                save_only=save_only,
                files_scanned=0,
                total_files=0,
                findings_count=0,
                path_index=0,
                pending_entries=[],
                message_key="checks:progress_shared_folder_missing",
                message="Shared folder could not be resolved.",
                changed_since_days=changed_since_days,
            )

        if isinstance(resume_cursor, dict):
            changed_since_days = max(0, int(resume_cursor.get("changed_since_days", changed_since_days) or 0))
        path_index = int(resume_cursor.get("path_index") or 0) if isinstance(resume_cursor, dict) else 0
        pending_entries = resume_cursor.get("pending_entries") if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("pending_entries"), list) else []
        metrics_trusted = bool(resume_cursor.get("metrics_trusted")) if isinstance(resume_cursor, dict) else False
        findings_count = int(resume_cursor.get("findings_count") or 0) if metrics_trusted and isinstance(resume_cursor, dict) else 0
        resolved_count = int(resume_cursor.get("resolved_count") or 0) if metrics_trusted and isinstance(resume_cursor, dict) else 0
        ignored_count = int(resume_cursor.get("ignored_count") or 0) if metrics_trusted and isinstance(resume_cursor, dict) else 0
        if not save_only and not metrics_trusted:
            findings_count = backend._countOpenChecksScanFindings(None, pending_entries)
        saved_entries = self.resume_saved_entries(
            check_type=check_type,
            save_only=save_only,
            resume_cursor=resume_cursor,
        )
        if save_only:
            findings_count = len(saved_entries)
        checks_findings_debouncer = backend._newChecksFindingsDebouncer()
        scan_context = backend._newChecksScanContext()

        def flush_saved_checks_findings(*, force: bool = False, status: str = "running", reason: str = "") -> bool:
            if not save_only:
                return False
            if not saved_entries and not force:
                return False

            if not checks_findings_debouncer.should_flush(force=force, entry_count=len(saved_entries)):
                return False

            self.write_findings(
                check_type=check_type,
                status=status,
                shared_folder=shared_folder,
                source_mode="scan",
                save_only=True,
                entries=saved_entries,
            )
            checks_findings_debouncer.mark_flushed(len(saved_entries))
            progress_key = backend._checksStateKey(user_key, check_type)
            backend._updateChecksProgressHeartbeat(flush=True)
            with backend.runtime_state.lock("checks_progress"):
                progress = backend.runtime_state.memory("checks_progress").get(progress_key)
                if not isinstance(progress, dict):
                    progress = backend.runtime_state.read_persisted("checks_progress", progress_key)
                if not isinstance(progress, dict):
                    progress = {}
                progress = dict(progress)
                progress["check_type"] = check_type
                progress["source_mode"] = "scan"
                progress["save_only"] = True
                progress["changed_since_days"] = max(0, int(changed_since_days or 0))
                progress["running"] = status not in {"finished", "stopped", "failed"}
                progress["finished"] = status in {"finished", "stopped", "failed"}
                progress["last_progress_at"] = backend._utcNowIso()
                progress["heartbeat_at"] = progress["last_progress_at"]
                progress["last_flush_at"] = progress["last_progress_at"]
                progress["last_flush_count"] = len(saved_entries)
                progress["findings_count"] = len(saved_entries)
                progress["message_params"] = {
                    **(progress.get("message_params") if isinstance(progress.get("message_params"), dict) else {}),
                    "count": len(saved_entries),
                    "findings": len(saved_entries),
                }
                progress["last_flush_reason"] = str(reason or "save_only_findings_flush")
                backend.runtime_state.memory("checks_progress")[progress_key] = progress
                backend.runtime_state.persist("checks_progress", progress_key, dict(progress))
            return True

        candidate_paths = backend._getChecksCandidatePaths(
            user_key=user_key,
            check_type=check_type,
            shared_folder=shared_folder,
            changed_since_days=changed_since_days,
            use_cache=True,
        )
        total_files = len(candidate_paths)
        backend._setChecksProgressMessage(
            user_key,
            check_type,
            "checks:progress_scanning",
            message_params={"current": max(0, path_index), "total": total_files, "findings": findings_count},
            running=True,
            finished=False,
            stop_requested=False,
            source_mode="scan",
            save_only=save_only,
            changed_since_days=changed_since_days,
            files_scanned=max(0, path_index),
            total_files=total_files,
            findings_count=findings_count,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            current_path="",
            resume_cursor=backend._buildChecksResumeCursor(
                path_index=path_index,
                pending_entries=pending_entries,
                source_mode="scan",
                check_type=check_type,
                save_only=save_only,
                findings_count=findings_count,
                resolved_count=resolved_count,
                ignored_count=ignored_count,
                changed_since_days=changed_since_days,
            ),
        )

        if pending_entries and not save_only:
            entry = pending_entries[0]
            remaining_entries = pending_entries[1:]
            manual_review_required = bool(entry.get("_manual_review_required")) if isinstance(entry, dict) else False
            resolved = backend._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=auto_apply_suggested_names and not manual_review_required,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates and not manual_review_required,
                include_item=auto_apply_suggested_names or auto_apply_suggested_duplicates,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if resolved.get("stop_requested"):
                flush_saved_checks_findings(force=True, status="stopped", reason="stop_requested")
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=min(path_index, total_files),
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count + int(resolved.get("auto_applied_count") or 0),
                    ignored_count=ignored_count,
                    path_index=path_index,
                    pending_entries=[entry] + remaining_entries if entry else remaining_entries,
                    current_path=str((entry or {}).get("image_path") or ""),
                    message_key="checks:progress_stopped",
                    message="Checks scan stopped.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )
            entry = resolved.get("entry")
            item = resolved.get("item")
            auto_applied_count = int(resolved.get("auto_applied_count") or 0)
            processed_entry_tokens = [
                str(token or "").strip()
                for token in resolved.get("processed_entry_tokens") or []
                if str(token or "").strip()
            ]
            if auto_applied_count:
                if check_type == "name_conflicts":
                    resolved_count += auto_applied_count
                target_entry = entry or pending_entries[0]
                target_image_path = str(target_entry.get("image_path") or "").strip()
                if check_type == "name_conflicts":
                    rebuilt_same_image_entries = backend._excludeChecksEntriesByTokens(
                        [
                            candidate
                            for candidate in remaining_entries
                            if str(candidate.get("image_path") or "").strip() == target_image_path
                        ],
                        processed_entry_tokens,
                    )
                else:
                    rebuilt_same_image_entries = backend._rebuildChecksEntriesForImageAfterMutation(
                        image_path=target_image_path,
                        review_type=str(target_entry.get("review_type") or check_type),
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                        excluded_tokens=processed_entry_tokens,
                    )
                other_remaining_entries = [
                    candidate
                    for candidate in remaining_entries
                    if str(candidate.get("image_path") or "").strip()
                    != target_image_path
                ]
                refreshed_pending_entries = rebuilt_same_image_entries + other_remaining_entries
                findings_count = backend._countOpenChecksScanFindings(
                    refreshed_pending_entries[0] if refreshed_pending_entries else None,
                    refreshed_pending_entries[1:] if refreshed_pending_entries else [],
                )
                if refreshed_pending_entries:
                    entry = refreshed_pending_entries[0]
                    remaining_entries = refreshed_pending_entries[1:]
                    if check_type == "name_conflicts":
                        item = None
                    else:
                        item = backend.getChecksReviewItem(
                            entry=entry,
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            shared_folder=shared_folder,
                        )
                else:
                    entry = None
                    item = None
                    remaining_entries = []
            if resolved.get("auto_apply_warning"):
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=min(path_index, total_files),
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    path_index=path_index,
                    pending_entries=remaining_entries,
                    current_path=str((entry or {}).get("image_path") or ""),
                    result={"entry": entry, "item": item} if entry and item else None,
                    message_key=str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                    message="Suggested name could not be applied automatically.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )
            if not entry:
                findings_count = backend._countOpenChecksScanFindings(None, remaining_entries)
                pending_entries = remaining_entries
            else:
                findings_count = backend._countOpenChecksScanFindings(entry, remaining_entries)
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=min(path_index, total_files),
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    path_index=path_index,
                    pending_entries=remaining_entries,
                    current_path=str(entry.get("image_path") or ""),
                    result={
                        "entry": entry,
                        "item": item,
                    },
                    message_key="checks:progress_result_found",
                    message="Check finding found.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )

        for index in range(max(0, path_index), total_files):
            last_keepalive_at = backend._refreshSessionIfNeeded(
                user_key=user_key,
                base_url=base_url,
                last_keepalive_at=last_keepalive_at,
            )
            if backend._shouldStopChecks(user_key, check_type):
                flush_saved_checks_findings(force=True, status="stopped", reason="stop_requested")
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=index,
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    path_index=index,
                    pending_entries=[],
                    message_key="checks:progress_stopped",
                    message="Checks scan stopped.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )
            image_path = candidate_paths[index]
            scanned_count = index + 1
            backend._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_scanning",
                message_params={"current": scanned_count, "total": total_files, "findings": findings_count},
                running=True,
                finished=False,
                stop_requested=False,
                source_mode="scan",
                save_only=save_only,
                changed_since_days=changed_since_days,
                files_scanned=scanned_count,
                total_files=total_files,
                findings_count=findings_count,
                resolved_count=resolved_count,
                ignored_count=ignored_count,
                current_path=image_path,
                resume_cursor=backend._buildChecksResumeCursor(
                    path_index=index,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    changed_since_days=changed_since_days,
                ),
            )
            if backend._shouldSkipRawFaceCheckWithoutSidecar(image_path, check_type, scan_context):
                continue

            jpeg_context_override = None
            if backend._shouldProbeJpegFaceCheckWithoutSidecar(image_path, check_type, scan_context):
                jpeg_context_override = backend.files.readJpegContext(image_path)
                if not jpeg_context_override.get("xmp_content"):
                    continue

            analysis = backend.files.analyzeMetadata(
                backend._readImageMetadata(
                    image_path,
                    scan_context=scan_context,
                    jpeg_context_override=jpeg_context_override,
                )
            )
            entries = backend._buildCheckEntriesForType(
                image_path=image_path,
                review_type=check_type,
                analysis=analysis,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if not entries:
                continue

            findings_count = backend._countOpenChecksScanFindings(entries[0], entries[1:])
            if save_only:
                entry = entries[0]
                resolved = backend._resolveChecksReviewEntry(
                    entry=entry,
                    auto_apply_suggested_names=auto_apply_suggested_names,
                    auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
                if resolved.get("stop_requested"):
                    flush_saved_checks_findings(force=True, status="stopped", reason="stop_requested")
                    return backend._buildChecksScanPayload(
                        check_type=check_type,
                        save_only=save_only,
                        files_scanned=scanned_count,
                        total_files=total_files,
                        findings_count=findings_count,
                        resolved_count=resolved_count + int(resolved.get("auto_applied_count") or 0),
                        ignored_count=ignored_count,
                        path_index=index + 1,
                        pending_entries=entries,
                        current_path=image_path,
                        message_key="checks:progress_stopped",
                        message="Checks scan stopped.",
                        message_params={"count": findings_count},
                        changed_since_days=changed_since_days,
                    )
                auto_applied_count = int(resolved.get("auto_applied_count") or 0)
                processed_entry_tokens = [
                    str(token or "").strip()
                    for token in resolved.get("processed_entry_tokens") or []
                    if str(token or "").strip()
                ]
                if auto_applied_count:
                    if check_type == "name_conflicts":
                        resolved_count += auto_applied_count
                if resolved.get("auto_apply_warning"):
                    self.append_unique_findings(saved_entries, entries)
                    findings_count = len(saved_entries)
                    flush_saved_checks_findings(force=True, reason="auto_apply_warning")
                    backend._setChecksProgressMessage(
                        user_key,
                        check_type,
                        str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                        message="Suggested solution could not be applied automatically. The finding was saved for later review.",
                        message_params={"count": findings_count},
                        running=True,
                        finished=False,
                        source_mode="scan",
                        save_only=True,
                        changed_since_days=changed_since_days,
                        files_scanned=scanned_count,
                        total_files=total_files,
                        findings_count=findings_count,
                        resolved_count=resolved_count,
                        ignored_count=ignored_count,
                        current_path=image_path,
                        result=None,
                        resume_cursor=backend._buildChecksResumeCursor(
                            path_index=index + 1,
                            pending_entries=[],
                            source_mode="scan",
                            check_type=check_type,
                            save_only=True,
                            findings_count=findings_count,
                            resolved_count=resolved_count,
                            ignored_count=ignored_count,
                            changed_since_days=changed_since_days,
                        ),
                    )
                    continue

                refreshed_entries = entries
                if auto_applied_count:
                    if check_type == "name_conflicts":
                        refreshed_entries = backend._excludeChecksEntriesByTokens(entries[1:], processed_entry_tokens)
                    else:
                        refreshed_entries = backend._buildCheckEntriesForType(
                            image_path=image_path,
                            review_type=check_type,
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            shared_folder=shared_folder,
                        )

                if refreshed_entries:
                    self.append_unique_findings(saved_entries, refreshed_entries)
                    findings_count = len(saved_entries)
                    flush_saved_checks_findings(reason="save_only_result")
                else:
                    findings_count = len(saved_entries)
                backend._setChecksProgressMessage(
                    user_key,
                    check_type,
                    "checks:progress_scanning",
                    message_params={"current": scanned_count, "total": total_files, "findings": findings_count},
                    running=True,
                    finished=False,
                    source_mode="scan",
                    save_only=True,
                    changed_since_days=changed_since_days,
                    files_scanned=scanned_count,
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    current_path=image_path,
                    resume_cursor=backend._buildChecksResumeCursor(
                        path_index=index + 1,
                        pending_entries=[],
                        source_mode="scan",
                        check_type=check_type,
                        save_only=True,
                        findings_count=findings_count,
                        resolved_count=resolved_count,
                        ignored_count=ignored_count,
                        changed_since_days=changed_since_days,
                    ),
                )
                continue

            entry = entries[0]
            item = None
            remaining_entries = entries[1:]
            resolved = backend._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                include_item=save_only or auto_apply_suggested_names or auto_apply_suggested_duplicates,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if resolved.get("stop_requested"):
                flush_saved_checks_findings(force=True, status="stopped", reason="stop_requested")
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=False,
                    files_scanned=scanned_count,
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count + int(resolved.get("auto_applied_count") or 0),
                    ignored_count=ignored_count,
                    path_index=index + 1,
                    pending_entries=[entry] + remaining_entries if entry else remaining_entries,
                    current_path=image_path,
                    message_key="checks:progress_stopped",
                    message="Checks scan stopped.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )
            entry = resolved.get("entry")
            item = resolved.get("item")
            auto_applied_count = int(resolved.get("auto_applied_count") or 0)
            processed_entry_tokens = [
                str(token or "").strip()
                for token in resolved.get("processed_entry_tokens") or []
                if str(token or "").strip()
            ]
            if auto_applied_count:
                if check_type == "name_conflicts":
                    resolved_count += auto_applied_count
                if check_type == "name_conflicts":
                    refreshed_entries = backend._excludeChecksEntriesByTokens(remaining_entries, processed_entry_tokens)
                else:
                    refreshed_entries = backend._rebuildChecksEntriesForImageAfterMutation(
                        image_path=image_path,
                        review_type=check_type,
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                        excluded_tokens=processed_entry_tokens,
                    )
                findings_count = backend._countOpenChecksScanFindings(
                    refreshed_entries[0] if refreshed_entries else None,
                    refreshed_entries[1:] if refreshed_entries else [],
                )
                if not refreshed_entries:
                    continue
                entry = refreshed_entries[0]
                remaining_entries = refreshed_entries[1:]
                if check_type == "name_conflicts":
                    item = None
                else:
                    item = backend.getChecksReviewItem(
                        entry=entry,
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                    )
            if resolved.get("auto_apply_warning"):
                return backend._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=False,
                    files_scanned=scanned_count,
                    total_files=total_files,
                    findings_count=findings_count,
                    resolved_count=resolved_count,
                    ignored_count=ignored_count,
                    path_index=index + 1,
                    pending_entries=remaining_entries,
                    current_path=image_path,
                    result={"entry": entry, "item": item} if entry and item else None,
                    message_key=str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                    message="Suggested name could not be applied automatically.",
                    message_params={"count": findings_count},
                    changed_since_days=changed_since_days,
                )
            if not entry:
                findings_count = 0
                continue
            findings_count = backend._countOpenChecksScanFindings(entry, remaining_entries)
            return backend._buildChecksScanPayload(
                check_type=check_type,
                save_only=False,
                files_scanned=scanned_count,
                total_files=total_files,
                findings_count=findings_count,
                resolved_count=resolved_count,
                ignored_count=ignored_count,
                path_index=index + 1,
                pending_entries=remaining_entries,
                current_path=image_path,
                result={
                    "entry": entry,
                    "item": item,
                },
                message_key="checks:progress_result_found",
                message="Check finding found.",
                message_params={"count": findings_count},
                changed_since_days=changed_since_days,
            )

        if save_only:
            flush_saved_checks_findings(force=True, status="finished", reason="final")
            return backend._buildChecksScanPayload(
                check_type=check_type,
                save_only=True,
                files_scanned=total_files,
                total_files=total_files,
                findings_count=len(saved_entries),
                resolved_count=resolved_count,
                ignored_count=ignored_count,
                path_index=total_files,
                pending_entries=[],
                message_key="checks:progress_findings_saved" if saved_entries else "checks:progress_findings_empty",
                message="Checks findings saved." if saved_entries else "No checks findings were saved.",
                message_params={"count": len(saved_entries)},
                changed_since_days=changed_since_days,
            )

        return backend._buildChecksScanPayload(
            check_type=check_type,
            save_only=False,
            files_scanned=total_files,
            total_files=total_files,
            findings_count=findings_count,
            resolved_count=resolved_count,
            ignored_count=ignored_count,
            path_index=total_files,
            pending_entries=[],
            message_key="checks:progress_finished_no_match",
            message="No further checks findings found.",
            message_params={"count": findings_count},
            changed_since_days=changed_since_days,
        )

    def start_review(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        source_mode: str,
        check_type: str,
        save_only: bool = False,
        resume_from_progress: bool = False,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        advance_current_result: bool = False,
        changed_since_days: int = 0,
    ) -> Dict[str, Any]:
        backend = self.backend
        backend._clearChecksStopRequest(user_key=user_key, check_type=check_type)
        backend._setActiveChecksContext(user_key=user_key, check_type=check_type, save_only=save_only)
        source_mode_normalized = str(source_mode or "findings").strip().lower()
        if source_mode_normalized not in {"findings", "scan"}:
            source_mode_normalized = "findings"

        check_type_normalized = str(check_type or "dimension_issues").strip().lower()
        supported_types = {"dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts"}
        if check_type_normalized not in supported_types:
            check_type_normalized = "dimension_issues"

        if source_mode_normalized == "scan":
            return self.start_scan(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                check_type=check_type_normalized,
                save_only=save_only,
                resume_from_progress=resume_from_progress,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                advance_current_result=advance_current_result,
                changed_since_days=changed_since_days,
            )

        findings_payload = self.get_finding_entries(check_type=check_type_normalized)
        stored_entries = findings_payload.get("entries") if isinstance(findings_payload.get("entries"), list) else []
        entries = [entry for entry in stored_entries if isinstance(entry, dict)]
        return {
            "check_type": check_type_normalized,
            "source_mode": source_mode_normalized,
            "save_only": bool(findings_payload.get("save_only")),
            "count": len(entries),
            "entries": entries,
        }

    def start_scan(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool = False,
        resume_from_progress: bool = False,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        advance_current_result: bool = False,
        changed_since_days: int = 0,
    ) -> Dict[str, Any]:
        backend = self.backend
        check_type = backend._normalizeChecksType(check_type)
        with backend._checks_start_lock:
            current = backend.getChecksProgress(user_key, check_type)
            state_key = backend._checksStateKey(user_key, check_type)
            current_source_mode = str(current.get("source_mode") or "").strip().lower() if isinstance(current, dict) else ""
            if current.get("running") and current_source_mode == "scan":
                return backend._buildChecksStartBlockedPayload(current, requested_check_type=check_type)

            running_progress = backend._runningChecksScanProgress(user_key, exclude_check_type=check_type)
            if running_progress:
                return backend._buildChecksStartBlockedPayload(running_progress, requested_check_type=check_type)

            running_operation = backend._runningOperationProgress(user_key, exclude_operation="checks")
            if running_operation:
                return backend._buildStartBlockedByRunningOperationPayload(
                    running_operation,
                    requested_operation="checks",
                )

            resume_cursor = current.get("resume_cursor") if resume_from_progress and isinstance(current.get("resume_cursor"), dict) else {}
            if resume_cursor:
                resume_cursor = self.trusted_resume_cursor(
                    current,
                    check_type=check_type,
                    save_only=save_only,
                    advance_current_result=advance_current_result,
                )
                save_only = bool(resume_cursor.get("save_only", save_only))
                changed_since_days = max(0, int(resume_cursor.get("changed_since_days", changed_since_days) or 0))
                check_type = str(resume_cursor.get("check_type") or check_type or "dimension_issues").strip().lower()
                state_key = backend._checksStateKey(user_key, check_type)
            else:
                self.invalidate_candidate_paths_cache(user_key, check_type)
            operation_id = (
                str(current.get("operation_id") or "").strip()
                if resume_cursor and str(current.get("operation_id") or "").strip()
                else f"checks-{check_type}-{uuid4().hex}"
            )

            backend._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:status_preparing_scan",
                operation_id=operation_id,
                running=True,
                finished=False,
                stop_requested=False,
                source_mode="scan",
                save_only=save_only,
                changed_since_days=changed_since_days,
                files_scanned=0,
                total_files=0,
                findings_count=int(resume_cursor.get("findings_count") or 0) if resume_cursor else 0,
                resolved_count=int(resume_cursor.get("resolved_count") or 0) if resume_cursor else 0,
                ignored_count=int(resume_cursor.get("ignored_count") or 0) if resume_cursor else 0,
                current_path="",
                result=None,
                resume_cursor=resume_cursor or self.build_resume_cursor(
                    path_index=0,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=0,
                    resolved_count=0,
                    ignored_count=0,
                    changed_since_days=changed_since_days,
                ),
            )
            worker = Thread(
                target=self._run_scan,
                kwargs={
                    "user_key": user_key,
                    "cookies": dict(cookies),
                    "base_url": base_url,
                    "check_type": check_type,
                    "save_only": save_only,
                    "changed_since_days": changed_since_days,
                    "auto_apply_suggested_names": auto_apply_suggested_names,
                    "auto_apply_suggested_duplicates": auto_apply_suggested_duplicates,
                    "resume_cursor": resume_cursor if resume_cursor else None,
                },
                daemon=True,
            )
            backend.runtime_state.values("checks_threads")[state_key] = worker
            worker.start()
        return backend.getChecksProgress(user_key, check_type)

    def _run_scan(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]] = None,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        changed_since_days: int = 0,
    ) -> None:
        backend = self.backend
        try:
            result = self.search_next_item(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                check_type=check_type,
                save_only=save_only,
                changed_since_days=changed_since_days,
                resume_cursor=resume_cursor,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
            )
            backend._setChecksProgress(user_key, **result)
        except (SessionBootstrapRequired, SessionManagerError) as exc:
            self.write_persisted_findings_status(check_type=check_type, status="failed", save_only=save_only)
            current_progress = backend.getChecksProgress(user_key, check_type)
            current_resume_cursor = current_progress.get("resume_cursor") if isinstance(current_progress.get("resume_cursor"), dict) else {}
            detail = exc.detail if isinstance(exc, SessionManagerError) and isinstance(exc.detail, dict) else {}
            backend._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_failed",
                message=str(exc),
                running=False,
                finished=False,
                stop_requested=False,
                error=str(exc),
                error_details=detail,
                save_only=save_only,
                source_mode="scan",
                changed_since_days=changed_since_days,
                files_scanned=int(current_progress.get("files_scanned") or 0),
                total_files=int(current_progress.get("total_files") or 0),
                findings_count=int(current_progress.get("findings_count") or 0),
                resolved_count=int(current_progress.get("resolved_count") or 0),
                ignored_count=int(current_progress.get("ignored_count") or 0),
                current_path=str(current_progress.get("current_path") or ""),
                resume_cursor=current_resume_cursor or resume_cursor or self.build_resume_cursor(
                    path_index=0,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=0,
                    resolved_count=0,
                    ignored_count=0,
                    changed_since_days=changed_since_days,
                ),
            )
        except self._operation_error_type as exc:
            details = exc.details if isinstance(exc.details, dict) else {}
            if str(details.get("code") or "") != "checks_stop_requested":
                raise
            current_progress = backend.getChecksProgress(user_key, check_type)
            current_resume_cursor = current_progress.get("resume_cursor") if isinstance(current_progress.get("resume_cursor"), dict) else {}
            backend._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_stopped",
                message="Checks scan stopped.",
                running=False,
                finished=True,
                stop_requested=True,
                save_only=save_only,
                source_mode="scan",
                changed_since_days=changed_since_days,
                files_scanned=int(current_progress.get("files_scanned") or 0),
                total_files=int(current_progress.get("total_files") or 0),
                findings_count=int(current_progress.get("findings_count") or 0),
                resolved_count=int(current_progress.get("resolved_count") or 0),
                ignored_count=int(current_progress.get("ignored_count") or 0),
                current_path=str(current_progress.get("current_path") or ""),
                resume_cursor=current_resume_cursor or resume_cursor or self.build_resume_cursor(
                    path_index=0,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=0,
                    resolved_count=0,
                    ignored_count=0,
                    changed_since_days=changed_since_days,
                ),
            )
        except Exception as exc:
            self.write_persisted_findings_status(check_type=check_type, status="failed", save_only=save_only)
            backend._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_failed",
                message="Checks scan failed.",
                running=False,
                finished=True,
                stop_requested=False,
                error=str(exc),
                save_only=save_only,
                source_mode="scan",
                changed_since_days=changed_since_days,
            )
        finally:
            backend.runtime_state.values("checks_threads").pop(backend._checksStateKey(user_key, check_type), None)
