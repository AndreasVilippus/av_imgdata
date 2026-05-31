#!/usr/bin/env python3
from threading import Thread
from typing import Any, Dict, Optional, Type
from uuid import uuid4

from api.session_manager import SessionBootstrapRequired, SessionManagerError


class ChecksWorkflowService:
    def __init__(self, backend: Any, operation_error_type: Type[Exception]):
        self.backend = backend
        self._operation_error_type = operation_error_type

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

        findings_payload = backend.getChecksFindingEntries(check_type=check_type_normalized)
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
                resume_cursor = backend._trustedChecksResumeCursor(
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
                backend._invalidateChecksCandidatePathsCache(user_key, check_type)
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
                resume_cursor=resume_cursor or backend._buildChecksResumeCursor(
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
            result = backend.searchNextChecksItem(
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
            backend._writePersistedChecksFindingsStatus(check_type=check_type, status="failed", save_only=save_only)
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
                resume_cursor=current_resume_cursor or resume_cursor or backend._buildChecksResumeCursor(
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
                resume_cursor=current_resume_cursor or resume_cursor or backend._buildChecksResumeCursor(
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
            backend._writePersistedChecksFindingsStatus(check_type=check_type, status="failed", save_only=save_only)
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
