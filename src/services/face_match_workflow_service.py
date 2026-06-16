#!/usr/bin/env python3
import traceback
from contextlib import nullcontext
from copy import deepcopy
from threading import Lock
from threading import Thread
from time import monotonic
from typing import Any, Dict, List, Optional
from uuid import uuid4

from api.session_manager import SessionBootstrapRequired, SessionManagerError


class FaceMatchWorkflowService:
    def __init__(self, backend: Any):
        self.backend = backend
        self._candidate_paths_cache: Dict[str, Dict[str, Any]] = {}
        self._candidate_paths_cache_lock = Lock()

    @staticmethod
    def candidate_paths_cache_key(user_key: str, action: Any) -> str:
        return f"{str(user_key or '').strip()}:{str(action or '').strip().lower()}"

    def invalidate_candidate_paths_cache(self, user_key: str, action: Any) -> None:
        state_key = self.candidate_paths_cache_key(user_key, action)
        with self._candidate_paths_cache_lock:
            self._candidate_paths_cache.pop(state_key, None)

    def get_candidate_paths(
        self,
        *,
        user_key: str,
        action: Any,
        shared_folder: str,
        use_cache: bool = True,
    ) -> List[str]:
        state_key = self.candidate_paths_cache_key(user_key, action)
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
        candidate_paths = self.backend.files.listImageFiles(normalized_shared_folder)
        with self._candidate_paths_cache_lock:
            self._candidate_paths_cache[state_key] = {
                "shared_folder": normalized_shared_folder,
                "paths": list(candidate_paths),
            }
        return candidate_paths

    def request_stop(self, user_key: str) -> Dict[str, Any]:
        self.backend._setFaceMatchingProgressMessage(
            user_key,
            "face_match:progress_stopping",
            stop_requested=True,
        )
        return self.backend.getFaceMatchingProgress(user_key)

    def should_stop(self, user_key: str) -> bool:
        progress = self.backend.getFaceMatchingProgress(user_key)
        return bool(progress.get("stop_requested"))

    def _read_findings(self) -> Dict[str, Any]:
        findings = self.backend.face_match_findings.read()
        return findings if isinstance(findings, dict) else {}

    def _read_findings_status(self) -> Dict[str, Any]:
        findings = self.backend.face_match_findings.read_status()
        return findings if isinstance(findings, dict) else {}

    def _write_findings_payload(self, payload: Dict[str, Any]) -> bool:
        return bool(self.backend.face_match_findings.write(payload))

    def _delete_findings(self) -> bool:
        return bool(self.backend.face_match_findings.delete())

    def get_findings(self) -> Dict[str, Any]:
        return self._read_findings()

    def get_findings_status(self) -> Dict[str, Any]:
        return self._read_findings_status()

    def resume_saved_entries(
        self,
        *,
        action: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        backend = self.backend
        if not save_only or not isinstance(resume_cursor, dict):
            return []
        findings = backend.getFaceMatchFindings()
        if str(findings.get("action") or "").strip().lower() != str(action or "").strip().lower():
            return []
        if not bool(findings.get("save_only")):
            return []
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        normalized_entries: List[Dict[str, Any]] = []
        seen_tokens = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            normalized_entry = backend._normalizeFaceMatchEntry(entry)
            token = backend._faceMatchFindingEntryToken(normalized_entry)
            if token and token in seen_tokens:
                continue
            if token:
                seen_tokens.add(token)
            normalized_entries.append(normalized_entry)
        return normalized_entries

    def append_unique_finding(
        self,
        entries: List[Dict[str, Any]],
        entry: Dict[str, Any],
    ) -> bool:
        backend = self.backend
        normalized_entry = backend._normalizeFaceMatchEntry(entry)
        suppression_checker = getattr(type(backend), "_isFaceMatchFindingSuppressed", None)
        if callable(suppression_checker) and suppression_checker(backend, normalized_entry):
            return False
        token = backend._faceMatchFindingEntryToken(normalized_entry)
        if token and any(backend._faceMatchFindingEntryToken(existing) == token for existing in entries):
            return False
        entries.append(backend._compactFaceMatchFindingEntryForStorage(normalized_entry))
        return True

    def write_persisted_findings_status(
        self,
        *,
        action: str,
        status: str,
        auto: bool,
        save_only: bool,
        transferred_count: int,
    ) -> None:
        backend = self.backend
        if not save_only:
            return
        with backend._checkFindingsLock("face_match"):
            findings = backend.getFaceMatchFindings()
            entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
            backend._writeFaceMatchFindings(
                status=status,
                shared_folder=str(findings.get("shared_folder") or ""),
                action=action,
                auto=auto,
                save_only=True,
                transferred_count=transferred_count,
                entries=[entry for entry in entries if isinstance(entry, dict)],
                job_id=str(findings.get("job_id") or ""),
                started_at=str(findings.get("started_at") or ""),
            )

    def write_findings(
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
        timestamp = self.backend._timestamp_now()
        effective_job_id = str(job_id or timestamp)
        effective_started_at = str(started_at or timestamp)
        self._write_findings_payload(
            {
                "job_id": effective_job_id,
                "started_at": effective_started_at,
                "finished_at": timestamp if finished else "",
                "last_updated_at": timestamp,
                "status": status,
                "shared_folder": shared_folder,
                "action": action,
                "auto": auto,
                "save_only": save_only,
                "transferred_count": transferred_count,
                "count": len(entries),
                "entries": [
                    self.backend._compactFaceMatchFindingEntryForStorage(entry)
                    for entry in entries
                    if isinstance(entry, dict)
                ],
            }
        )

    def should_flush_findings(
        self,
        *,
        entries_count: int,
        last_flush_count: int,
        last_flush_at: float,
    ) -> bool:
        normalized_entry_count = max(0, int(entries_count or 0))
        normalized_last_count = max(0, int(last_flush_count or 0))
        if normalized_entry_count <= normalized_last_count:
            return False
        if normalized_last_count <= 0:
            return True
        entry_delta = normalized_entry_count - normalized_last_count
        if entry_delta >= max(1, int(self.backend.FACE_MATCH_FINDINGS_FLUSH_ENTRY_INTERVAL)):
            return True
        elapsed = monotonic() - max(0.0, float(last_flush_at or 0.0))
        return elapsed >= max(0, int(self.backend.FACE_MATCH_FINDINGS_FLUSH_INTERVAL_SECONDS))

    def persist_findings_entries(
        self,
        *,
        findings: Dict[str, Any],
        entries: List[Dict[str, Any]],
        transferred_count: int,
    ) -> None:
        backend = self.backend
        if not entries:
            self._delete_findings()
            return

        timestamp = backend._timestamp_now()
        self._write_findings_payload(
            {
                "job_id": str(findings.get("job_id") or timestamp),
                "started_at": str(findings.get("started_at") or timestamp),
                "finished_at": str(findings.get("finished_at") or timestamp),
                "last_updated_at": timestamp,
                "status": str(findings.get("status") or "finished"),
                "shared_folder": str(findings.get("shared_folder") or ""),
                "action": str(findings.get("action") or "search_photo_face_in_file"),
                "auto": bool(findings.get("auto")),
                "save_only": bool(findings.get("save_only")),
                "transferred_count": int(transferred_count),
                "count": len(entries),
                "entries": [
                    backend._compactFaceMatchFindingEntryForStorage(entry)
                    for entry in entries
                    if isinstance(entry, dict)
                ],
            },
        )

    def get_finding_entries(
        self,
        *,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
        action: str = "",
        auto: bool = False,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        backend = self.backend
        findings = backend.getFaceMatchFindings()
        stream_compacted = bool(findings.pop("_stream_compacted", False))
        requested_action = str(action or "").strip().lower()
        findings_action = str(findings.get("action") or "").strip().lower()
        if requested_action and findings_action and requested_action != findings_action:
            return {
                "status": str(findings.get("status") or ""),
                "shared_folder": str(findings.get("shared_folder") or ""),
                "action": findings_action,
                "requested_action": requested_action,
                "count": 0,
                "entries": [],
                "transferred_count": 0,
                "save_only": False,
                "auto": bool(auto),
            }
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        suppression_checker = getattr(type(backend), "_isFaceMatchFindingSuppressed", None)
        entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and not (
                callable(suppression_checker)
                and suppression_checker(backend, entry)
            )
        ]
        resolved_entries = entries
        transferred_count = int(findings.get("transferred_count") or 0)
        if stream_compacted and entries and not refresh and not auto:
            backend._persistFaceMatchFindingsEntries(
                findings=findings,
                entries=[entry for entry in entries if isinstance(entry, dict)],
                transferred_count=transferred_count,
            )
        if (refresh or auto) and user_key and isinstance(cookies, dict) and base_url:
            entries_total = len(entries)
            entries_current = 0
            stopped = False
            review_required = False
            if auto:
                backend._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_applying_known_findings",
                    message="Applying known persons from saved findings.",
                    operation_id=f"face-match-findings-{uuid4().hex}",
                    action="load_photo_face_match_findings",
                    source_mode="findings",
                    running=True,
                    finished=False,
                    paused=False,
                    stop_requested=False,
                    entries_current=0,
                    entries_total=entries_total,
                    transferred_count=transferred_count,
                )
            known_persons_cache = backend.photos.sortPersonsForFaceMatch(
                backend.photos.listFotoTeamPersonKnown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    additional=["thumbnail"],
                )
            )
            image_faces_cache: Dict[int, List[Dict[str, Any]]] = {}
            photos_lookup_cache = getattr(backend, "photos_lookup_cache", None)
            next_entries = []
            findings_changed = False
            persisted_entries: Optional[List[Any]] = None
            persisted_transferred_count: Optional[int] = None

            def update_auto_apply_progress() -> None:
                if not auto:
                    return
                backend._setFaceMatchingProgress(
                    user_key,
                    action="load_photo_face_match_findings",
                    source_mode="findings",
                    running=True,
                    finished=False,
                    paused=False,
                    entries_current=entries_current,
                    entries_total=entries_total,
                    transferred_count=transferred_count,
                )

            def persist_checkpoint(remaining_entries: List[Any]) -> None:
                nonlocal persisted_entries, persisted_transferred_count
                persisted_entries = [*next_entries, *remaining_entries]
                persisted_transferred_count = transferred_count
                backend._persistFaceMatchFindingsEntries(
                    findings=findings,
                    entries=persisted_entries,
                    transferred_count=transferred_count,
                )
                update_auto_apply_progress()

            def retain_after_photos_error(entry: Dict[str, Any], exc: SessionManagerError, *, stage: str) -> None:
                if backend._sessionManagerErrorNeedsLogin(exc):
                    raise exc
                backend._debugLog(
                    "face_match_findings_auto_entry_error",
                    action=str(entry.get("action") or findings_action or "search_photo_face_in_file").strip().lower(),
                    stage=stage,
                    image_path=str(entry.get("image_path") or "").strip(),
                    item_id=(entry.get("image") or {}).get("id") if isinstance(entry.get("image"), dict) else None,
                    face_id=(entry.get("face") or {}).get("face_id") if isinstance(entry.get("face"), dict) else None,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    error_detail=exc.detail if isinstance(exc.detail, dict) else {},
                )
                next_entries.append(entry)

            for entry_index, entry in enumerate(entries):
                if auto and backend._shouldStopFaceMatching(user_key):
                    next_entries.extend(entries[entry_index:])
                    stopped = True
                    break
                entries_current = entry_index + 1
                if auto:
                    backend._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_applying_known_findings",
                        message="Applying known persons from saved findings.",
                        action="load_photo_face_match_findings",
                        source_mode="findings",
                        running=True,
                        finished=False,
                        entries_current=entries_current,
                        entries_total=entries_total,
                        transferred_count=transferred_count,
                    )
                if not isinstance(entry, dict):
                    findings_changed = True
                    persist_checkpoint(entries[entry_index + 1:])
                    continue
                original_entry = deepcopy(entry)
                try:
                    entry_exists = backend._storedFaceMatchEntryExists(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        entry=entry,
                        image_faces_cache=image_faces_cache,
                        photos_lookup_cache=photos_lookup_cache,
                    )
                except SessionManagerError as exc:
                    retain_after_photos_error(entry, exc, stage="exists")
                    if auto:
                        next_entries.extend(entries[entry_index + 1:])
                        review_required = True
                        break
                    continue
                if entry != original_entry:
                    findings_changed = True
                if not entry_exists:
                    findings_changed = True
                    persist_checkpoint(entries[entry_index + 1:])
                    continue
                try:
                    resolved_entry = backend._resolveStoredFaceMatchEntry(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        entry=entry,
                        known_persons_cache=known_persons_cache,
                    )
                except SessionManagerError as exc:
                    retain_after_photos_error(entry, exc, stage="resolve")
                    if auto:
                        next_entries.extend(entries[entry_index + 1:])
                        review_required = True
                        break
                    continue
                action = str(resolved_entry.get("action") or "search_photo_face_in_file").strip().lower()
                if action in {"search_file_face_in_sources", "mark_missing_photos_faces"} and not str(resolved_entry.get("source_name") or "").strip():
                    findings_changed = True
                    persist_checkpoint(entries[entry_index + 1:])
                    continue
                if auto and action in {"search_file_face_in_sources", "mark_missing_photos_faces"}:
                    metadata_face = resolved_entry.get("metadata_face")
                    image_path = str(resolved_entry.get("image_path") or "").strip()
                    source_name = str(resolved_entry.get("source_name") or "").strip()
                    if image_path and isinstance(metadata_face, dict) and source_name:
                        if action == "mark_missing_photos_faces":
                            try:
                                result = backend.resolveOrCreatePhotosPersonForMetadataFace(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    image_path=image_path,
                                    metadata_face=metadata_face,
                                    person_name=source_name,
                                    create_missing_person=False,
                                )
                            except SessionManagerError as exc:
                                retain_after_photos_error(entry, exc, stage="apply_metadata")
                                next_entries.extend(entries[entry_index + 1:])
                                review_required = True
                                break
                            if result.get("updated"):
                                transferred_count += 1
                                findings_changed = True
                                persist_checkpoint(entries[entry_index + 1:])
                                continue
                        else:
                            result = backend.replaceMetadataFaceName(
                                image_path=image_path,
                                face_data=metadata_face,
                                new_name=source_name,
                            )
                            if result.get("updated"):
                                transferred_count += 1
                                findings_changed = True
                                persist_checkpoint(entries[entry_index + 1:])
                                continue
                if auto and action != "search_file_face_in_sources":
                    matched_person = resolved_entry.get("matched_person")
                    matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                    face = resolved_entry.get("face")
                    face_id = face.get("face_id") if isinstance(face, dict) else None
                    if matched_person_name and face_id is not None:
                        try:
                            result = backend.resolveOrCreatePhotosPersonForExistingFace(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                image_path=str(resolved_entry.get("image_path") or "").strip(),
                                face_id=int(face_id),
                                person_name=str(matched_person_name),
                                item_id=face.get("item_id") if isinstance(face, dict) and face.get("item_id") is not None else None,
                                create_missing_person=False,
                            )
                        except SessionManagerError as exc:
                            retain_after_photos_error(entry, exc, stage="apply_photos")
                            next_entries.extend(entries[entry_index + 1:])
                            review_required = True
                            break
                        if result.get("updated"):
                            transferred_count += 1
                            findings_changed = True
                            persist_checkpoint(entries[entry_index + 1:])
                            continue
                next_entries.append(resolved_entry)
                if auto:
                    next_entries.extend(entries[entry_index + 1:])
                    review_required = True
                    break
            resolved_entries = next_entries
            if findings_changed and (
                resolved_entries != persisted_entries
                or transferred_count != persisted_transferred_count
            ):
                backend._persistFaceMatchFindingsEntries(
                    findings=findings,
                    entries=resolved_entries,
                    transferred_count=transferred_count,
                )
            if auto:
                if stopped:
                    message_key = "face_match:progress_stopped"
                    message = "Applying known persons stopped."
                elif review_required:
                    message_key = "face_match:progress_review_required"
                    message = "Manual review required for the next saved finding."
                else:
                    message_key = "face_match:progress_known_findings_applied"
                    message = "Known persons from saved findings applied."
                backend._setFaceMatchingProgressMessage(
                    user_key,
                    message_key,
                    message=message,
                    action="load_photo_face_match_findings",
                    source_mode="findings",
                    running=False,
                    finished=True,
                    paused=False,
                    stop_requested=False,
                    entries_current=entries_current,
                    entries_total=entries_total,
                    transferred_count=transferred_count,
                )
        response_entries = [
            backend._compactFaceMatchFindingEntryForResponse(entry)
            for entry in resolved_entries
            if isinstance(entry, dict)
        ]
        return {
            "status": str(findings.get("status") or ""),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "action": findings_action,
            "requested_action": requested_action,
            "count": len(resolved_entries),
            "entries": response_entries,
            "transferred_count": transferred_count,
            "save_only": bool(findings.get("save_only")),
            "auto": bool(auto or findings.get("auto")),
        }

    def get_finding_entries_locked(
        self,
        *,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
        action: str = "",
        auto: bool = False,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        backend = self.backend
        lock = (
            backend._writeOperationLock(
                f"face_match:findings:auto:{str(user_key or '').strip()}",
                phase="face_match_findings_auto_apply",
            )
            if auto and user_key
            else nullcontext()
        )
        with lock:
            with backend._checkFindingsLock("face_match"):
                return self.get_finding_entries(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    action=action,
                    auto=auto,
                    refresh=refresh,
                )


    def remove_metadata_entry(
        self,
        *,
        image_path: str,
        metadata_face: Dict[str, Any],
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        with self.backend._checkFindingsLock("face_match"):
            return self.remove_metadata_entry_unlocked(
                image_path=image_path,
                metadata_face=metadata_face,
                increment_transferred_count=increment_transferred_count,
            )

    def remove_metadata_entry_unlocked(
        self,
        *,
        image_path: str,
        metadata_face: Dict[str, Any],
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        backend = self.backend
        started = monotonic()
        findings = backend.getFaceMatchFindings()
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="read",
            duration_ms=round((monotonic() - started) * 1000, 2),
            mode="metadata",
        )
        filter_started = monotonic()
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        remaining_entries = []
        removed_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_image_path = str(entry.get("image_path") or "").strip()
            entry_metadata_face = entry.get("metadata_face")
            if entry_image_path == str(image_path or "").strip() and isinstance(entry_metadata_face, dict):
                if backend._faceMatchTargetToken(image_path=entry_image_path, face=entry_metadata_face) == backend._faceMatchTargetToken(image_path=image_path, face=metadata_face):
                    removed_count += 1
                    continue
            remaining_entries.append(entry)
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="filter",
            duration_ms=round((monotonic() - filter_started) * 1000, 2),
            mode="metadata",
            entries_count=len(entries),
            remaining_count=len(remaining_entries),
            removed_count=removed_count,
        )

        if removed_count == 0:
            return {
                "removed": False,
                "removed_count": 0,
                "remaining_count": len(entries),
                "deleted": False,
            }

        transferred_count = int(findings.get("transferred_count") or 0)
        if increment_transferred_count:
            transferred_count += removed_count

        if not remaining_entries:
            write_started = monotonic()
            deleted = self._delete_findings()
            backend._debugLog(
                "face_match_findings_remove_phase",
                phase="delete",
                duration_ms=round((monotonic() - write_started) * 1000, 2),
                mode="metadata",
                removed_count=removed_count,
            )
            return {
                "removed": deleted,
                "removed_count": removed_count,
                "remaining_count": 0,
                "deleted": bool(deleted),
                "transferred_count": transferred_count,
            }

        timestamp = backend._timestamp_now()
        updated_payload = {
            "job_id": str(findings.get("job_id") or timestamp),
            "started_at": str(findings.get("started_at") or timestamp),
            "finished_at": str(findings.get("finished_at") or timestamp),
            "last_updated_at": timestamp,
            "status": str(findings.get("status") or "finished"),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "action": str(findings.get("action") or "search_photo_face_in_file"),
            "auto": bool(findings.get("auto")),
            "save_only": bool(findings.get("save_only")),
            "transferred_count": transferred_count,
            "count": len(remaining_entries),
            "entries": [
                backend._compactFaceMatchFindingEntryForStorage(entry)
                for entry in remaining_entries
                if isinstance(entry, dict)
            ],
        }
        write_started = monotonic()
        written = self._write_findings_payload(updated_payload)
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="write",
            duration_ms=round((monotonic() - write_started) * 1000, 2),
            mode="metadata",
            remaining_count=len(remaining_entries),
            removed_count=removed_count,
        )
        return {
            "removed": bool(written),
            "removed_count": removed_count,
            "remaining_count": len(remaining_entries),
            "deleted": False,
            "transferred_count": transferred_count,
        }

    def remove_entry(
        self,
        *,
        face_id: int,
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        with self.backend._checkFindingsLock("face_match"):
            return self.remove_entry_unlocked(
                face_id=face_id,
                increment_transferred_count=increment_transferred_count,
            )

    def remove_entry_unlocked(
        self,
        *,
        face_id: int,
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        backend = self.backend
        started = monotonic()
        findings = backend.getFaceMatchFindings()
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="read",
            duration_ms=round((monotonic() - started) * 1000, 2),
            mode="photos_face",
            face_id=face_id,
        )
        filter_started = monotonic()
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        remaining_entries = []
        removed_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            face = entry.get("face")
            entry_face_id = None
            if isinstance(face, dict):
                try:
                    entry_face_id = int(face.get("face_id"))
                except (TypeError, ValueError):
                    entry_face_id = None
            if entry_face_id == int(face_id):
                removed_count += 1
                continue
            remaining_entries.append(entry)
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="filter",
            duration_ms=round((monotonic() - filter_started) * 1000, 2),
            mode="photos_face",
            face_id=face_id,
            entries_count=len(entries),
            remaining_count=len(remaining_entries),
            removed_count=removed_count,
        )

        if removed_count == 0:
            return {
                "removed": False,
                "removed_count": 0,
                "remaining_count": len(entries),
                "deleted": False,
            }

        transferred_count = int(findings.get("transferred_count") or 0)
        if increment_transferred_count:
            transferred_count += removed_count

        if not remaining_entries:
            write_started = monotonic()
            deleted = self._delete_findings()
            backend._debugLog(
                "face_match_findings_remove_phase",
                phase="delete",
                duration_ms=round((monotonic() - write_started) * 1000, 2),
                mode="photos_face",
                face_id=face_id,
                removed_count=removed_count,
            )
            return {
                "removed": deleted,
                "removed_count": removed_count,
                "remaining_count": 0,
                "deleted": bool(deleted),
                "transferred_count": transferred_count,
            }

        timestamp = backend._timestamp_now()
        updated_payload = {
            "job_id": str(findings.get("job_id") or timestamp),
            "started_at": str(findings.get("started_at") or timestamp),
            "finished_at": str(findings.get("finished_at") or timestamp),
            "last_updated_at": timestamp,
            "status": str(findings.get("status") or "finished"),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "action": str(findings.get("action") or "search_photo_face_in_file"),
            "auto": bool(findings.get("auto")),
            "save_only": bool(findings.get("save_only")),
            "transferred_count": transferred_count,
            "count": len(remaining_entries),
            "entries": [
                backend._compactFaceMatchFindingEntryForStorage(entry)
                for entry in remaining_entries
                if isinstance(entry, dict)
            ],
        }
        write_started = monotonic()
        written = self._write_findings_payload(updated_payload)
        backend._debugLog(
            "face_match_findings_remove_phase",
            phase="write",
            duration_ms=round((monotonic() - write_started) * 1000, 2),
            mode="photos_face",
            face_id=face_id,
            remaining_count=len(remaining_entries),
            removed_count=removed_count,
        )
        return {
            "removed": bool(written),
            "removed_count": removed_count,
            "remaining_count": len(remaining_entries),
            "deleted": False,
            "transferred_count": transferred_count,
        }

    def start_discovery(
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
    ) -> Dict[str, Any]:
        backend = self.backend
        current = backend.getFaceMatchingProgress(user_key)
        if current.get("running"):
            backend._debugLog(
                "face_matching_start_reused_running_progress",
                operation_id=current.get("operation_id"),
                action=current.get("action"),
                active=bool(current.get("active")),
                stale=bool(current.get("stale")),
            )
            return current
        running_operation = backend._runningOperationProgress(user_key, exclude_operation="face_match")
        if running_operation:
            backend._debugLog(
                "face_matching_start_blocked_by_running_operation",
                requested_operation="face_match",
                running_operation=running_operation.get("operation"),
                running_operation_id=running_operation.get("operation_id"),
                running_phase=running_operation.get("phase"),
            )
            return backend._buildStartBlockedByRunningOperationPayload(
                running_operation,
                requested_operation="face_match",
            )

        normalized_action = str(action or "search_photo_face_in_file").strip().lower()
        current_resume_cursor = current.get("resume_cursor") if isinstance(current.get("resume_cursor"), dict) else {}
        current_action = str(current_resume_cursor.get("action") or current.get("action") or "").strip().lower()
        should_continue_current = (
            (resume_from_progress or bool(skip_face_ids) or bool(skip_targets))
            and isinstance(current_resume_cursor, dict)
            and current_action == normalized_action
        )
        resume_cursor = dict(current_resume_cursor) if should_continue_current else {}
        if resume_cursor:
            if not resume_cursor.get("path_index"):
                resume_cursor["path_index"] = int(current.get("images_read") or 0)
            for field in (
                "transferred_count",
                "findings_count",
                "persons_read",
                "images_read",
                "faces_read",
                "target_faces_read",
                "metadata_faces_read",
            ):
                if field not in resume_cursor:
                    resume_cursor[field] = int(current.get(field) or 0)
        cursor_skip_face_ids = resume_cursor.get("skip_face_ids") if isinstance(resume_cursor.get("skip_face_ids"), list) else []
        combined_skip_face_ids = list(skip_face_ids or [])
        combined_skip_targets = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        for face_id in cursor_skip_face_ids:
            try:
                normalized_face_id = int(face_id)
            except Exception:
                continue
            if normalized_face_id not in combined_skip_face_ids:
                combined_skip_face_ids.append(normalized_face_id)
        cursor_skip_targets = resume_cursor.get("skip_targets") if isinstance(resume_cursor.get("skip_targets"), list) else []
        for token in cursor_skip_targets:
            normalized_token = str(token or "").strip()
            if normalized_token and normalized_token not in combined_skip_targets:
                combined_skip_targets.append(normalized_token)
        if resume_cursor:
            auto = bool(resume_cursor.get("auto", auto))
            save_only = bool(resume_cursor.get("save_only", save_only))
            recognize_persons = bool(resume_cursor.get("recognize_persons", recognize_persons))
            normalized_action = str(resume_cursor.get("action") or normalized_action).strip().lower() or normalized_action
        continue_existing_operation = bool(resume_cursor or combined_skip_face_ids or combined_skip_targets)
        resume_path_index = int(resume_cursor.get("path_index") or 0) if resume_cursor else 0
        operation_id = (
            str(current.get("operation_id") or "").strip()
            if continue_existing_operation and str(current.get("operation_id") or "").strip()
            else f"face_match-{uuid4().hex}"
        )
        start_message_key = (
            "face_match:status_preparing_scan"
            if normalized_action in {"search_file_face_in_sources", "mark_missing_photos_faces", "search_missing_faces_insightface"}
            else "face_match:status_starting"
        )
        backend._debugLog(
            "face_matching_start",
            operation_id=operation_id,
            action=normalized_action,
            auto=auto,
            save_only=save_only,
            resume=bool(resume_cursor),
            continue_existing_operation=continue_existing_operation,
            skip_face_ids_count=len(combined_skip_face_ids),
            skip_targets_count=len(combined_skip_targets),
            resume_path_index=resume_path_index,
            recognize_persons=bool(recognize_persons),
        )

        backend._setFaceMatchingProgressMessage(
            user_key,
            start_message_key,
            operation_id=operation_id,
            running=True,
            finished=False,
            paused=False,
            auth_required=False,
            stop_requested=False,
            action=normalized_action,
            result=None,
            error="",
            auto=auto,
            save_only=save_only,
            recognize_persons=bool(recognize_persons),
            persons_read=int(resume_cursor.get("persons_read") or 0) if resume_cursor else 0,
            images_read=int(resume_cursor.get("images_read") or 0) if resume_cursor else resume_path_index,
            faces_read=int(resume_cursor.get("faces_read") or 0) if resume_cursor else 0,
            target_faces_read=int(resume_cursor.get("target_faces_read") or 0) if resume_cursor else 0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=int(resume_cursor.get("metadata_faces_read") or 0) if resume_cursor else 0,
            transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
            findings_count=int(resume_cursor.get("findings_count") or 0) if resume_cursor else 0,
            resume_cursor=backend._buildFaceMatchResumeCursor(
                skip_face_ids=combined_skip_face_ids,
                skip_targets=combined_skip_targets,
                transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
                auto=auto,
                save_only=save_only,
                recognize_persons=bool(recognize_persons),
                action=normalized_action,
                findings_count=int(resume_cursor.get("findings_count") or 0) if resume_cursor else 0,
                path_index=resume_path_index,
                persons_read=int(resume_cursor.get("persons_read") or 0) if resume_cursor else 0,
                images_read=int(resume_cursor.get("images_read") or 0) if resume_cursor else resume_path_index,
                faces_read=int(resume_cursor.get("faces_read") or 0) if resume_cursor else 0,
                target_faces_read=int(resume_cursor.get("target_faces_read") or 0) if resume_cursor else 0,
                metadata_faces_read=int(resume_cursor.get("metadata_faces_read") or 0) if resume_cursor else 0,
            ),
        )
        worker = Thread(
            target=self._run_face_matching,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "action": normalized_action,
                "limit": limit,
                "offset": offset,
                "skip_face_ids": combined_skip_face_ids,
                "skip_targets": combined_skip_targets,
                "auto": auto,
                "save_only": save_only,
                "recognize_persons": bool(recognize_persons),
                "resume_cursor": resume_cursor if resume_cursor else None,
            },
            daemon=True,
        )
        backend.runtime_state.values("face_match_threads")[user_key] = worker
        worker.start()
        return backend.getFaceMatchingProgress(user_key)

    def _run_face_matching(
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
        recognize_persons: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> None:
        backend = self.backend
        started = monotonic()
        backend._debugLog(
            "face_matching_worker_start",
            action=action,
            auto=auto,
            save_only=save_only,
            recognize_persons=bool(recognize_persons),
            limit=limit,
            offset=offset,
            skip_face_ids_count=len(skip_face_ids or []),
            skip_targets_count=len(skip_targets or []),
            resume=bool(resume_cursor),
        )
        try:
            backend.session_manager.keepalive(user_key, base_url=base_url)
            if action == "search_file_face_in_sources":
                result = backend.searchFileFaceInSources(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    skip_targets=skip_targets,
                    auto=auto,
                    save_only=save_only,
                    recognize_persons=recognize_persons,
                    resume_cursor=resume_cursor,
                )
            elif action == "mark_missing_photos_faces":
                result = backend.searchMissingPhotosFaces(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    skip_targets=skip_targets,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            elif action == "search_missing_faces_insightface":
                result = backend.searchMissingPhotosFacesWithInsightFace(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    skip_targets=skip_targets,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            else:
                result = backend.searchPhotoFaceInFile(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    limit=limit,
                    offset=offset,
                    skip_face_ids=skip_face_ids,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            progress_updates: Dict[str, Any] = {
                "result": result,
                "running": False,
                "finished": True,
                "stop_requested": False,
                "action": action,
                "auto": auto,
                "save_only": save_only,
            }
            if isinstance(result, dict):
                for field in ("findings_count", "transferred_count"):
                    if field in result:
                        progress_updates[field] = result.get(field)
            backend._setFaceMatchingProgress(user_key, **progress_updates)
            backend._debugLog(
                "face_matching_worker_finished",
                action=action,
                auto=auto,
                save_only=save_only,
                duration_ms=round((monotonic() - started) * 1000, 2),
                findings_count=progress_updates.get("findings_count"),
                transferred_count=progress_updates.get("transferred_count"),
            )
        except (SessionBootstrapRequired, SessionManagerError) as exc:
            current_progress = backend.getFaceMatchingProgress(user_key)
            backend._writePersistedFaceMatchFindingsStatus(
                action=action,
                status="failed",
                auto=auto,
                save_only=save_only,
                transferred_count=int(current_progress.get("transferred_count") or 0),
            )
            backend._setFaceMatchingSessionExceptionProgress(
                user_key,
                exc,
                action=action,
                auto=auto,
                save_only=save_only,
                resume_cursor=resume_cursor,
                skip_face_ids=skip_face_ids,
                skip_targets=skip_targets,
            )
            backend._debugLog(
                "face_matching_worker_session_exception",
                action=action,
                duration_ms=round((monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
                error=str(exc),
            )
        except Exception as exc:
            current_progress = backend.getFaceMatchingProgress(user_key)
            backend._writePersistedFaceMatchFindingsStatus(
                action=action,
                status="failed",
                auto=auto,
                save_only=save_only,
                transferred_count=int(current_progress.get("transferred_count") or 0),
            )
            error_message = backend._formatExceptionForProgress(exc)
            error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
            backend._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_failed",
                message="Face matching failed.",
                running=False,
                finished=True,
                paused=False,
                auth_required=False,
                error=error_message,
                error_traceback=error_traceback,
                action=action,
                auto=auto,
                save_only=save_only,
            )
            backend._debugLog(
                "face_matching_worker_exception",
                action=action,
                duration_ms=round((monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
                error=error_message,
                traceback=error_traceback,
            )
        finally:
            backend.runtime_state.values("face_match_threads").pop(user_key, None)
