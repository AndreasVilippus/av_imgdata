#!/usr/bin/env python3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from services.status_payload_builder import StatusPayloadBuilder


class RuntimeOperationService:
    def __init__(
        self,
        *,
        timestamp_func: Callable[[], str],
        status_builder: StatusPayloadBuilder,
        stale_stopping_seconds: int = 120,
    ):
        self._timestamp_func = timestamp_func
        self.status_builder = status_builder
        self.stale_stopping_seconds = max(1, int(stale_stopping_seconds or 120))

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def parse_timestamp(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def stamp_progress(
        self,
        current: Dict[str, Any],
        *,
        operation_prefix: str,
        operation_discriminator: Any = "",
    ) -> Dict[str, Any]:
        payload = dict(current) if isinstance(current, dict) else {}
        normalized_prefix = str(operation_prefix or "operation").strip()
        normalized_discriminator = str(operation_discriminator or "").strip()
        if not payload.get("operation_id"):
            suffix = f"-{normalized_discriminator}" if normalized_discriminator else ""
            payload["operation_id"] = f"{normalized_prefix}{suffix}-{uuid4().hex}"
        try:
            current_revision = int(payload.get("revision") or 0)
        except (TypeError, ValueError):
            current_revision = 0
        payload["revision"] = max(0, current_revision) + 1
        timestamp_func = self._timestamp_func
        payload["last_updated_at"] = timestamp_func()
        return payload

    def is_stale_stopping_progress(self, progress: Any) -> bool:
        if not isinstance(progress, dict) or not progress.get("running"):
            return False
        message_key = str(progress.get("message_key") or progress.get("message") or "").strip()
        status = progress.get("status") if isinstance(progress.get("status"), dict) else {}
        phase = str(status.get("phase") or progress.get("phase") or "").strip().lower()
        if message_key not in {"checks:progress_stopping", "face_match:progress_stopping", "cleanup:progress_stopping"} and phase != "stopping":
            return False
        last_updated = self.parse_timestamp(progress.get("last_updated_at"))
        if last_updated is None:
            return False
        age_seconds = (datetime.now(timezone.utc) - last_updated).total_seconds()
        return age_seconds >= self.stale_stopping_seconds

    @staticmethod
    def is_running_progress(progress: Any) -> bool:
        return isinstance(progress, dict) and bool(progress.get("running"))

    def is_blocking_running_progress(self, progress: Any) -> bool:
        return self.is_running_progress(progress) and not self.is_stale_stopping_progress(progress)

    def blocked_by_running_operation_payload(
        self,
        running_progress: Dict[str, Any],
        *,
        requested_operation: str,
    ) -> Dict[str, Any]:
        payload = {
            "running": False,
            "finished": False,
            "blocked": True,
            "blocked_by_running_operation": True,
            "requested_operation": str(requested_operation or "").strip().lower(),
            "running_operation": str((running_progress or {}).get("operation") or "").strip().lower(),
            "running_operation_id": str((running_progress or {}).get("operation_id") or "").strip(),
            "message_key": "status:operation_blocked_by_running_operation",
            "message": "Another operation is already running.",
        }
        if isinstance(running_progress, dict):
            payload["running_progress"] = dict(running_progress)
        payload["status"] = self.status_builder.payload(
            operation=payload["requested_operation"],
            action="",
            mode="none",
            phase="blocked",
            save_only=False,
            progress={},
            counters=[],
        )
        return payload
