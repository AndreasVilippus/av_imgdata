#!/usr/bin/env python3
"""DSM-authenticated administration endpoints for external worker enrollment."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request

from api.imgdata_api import _prepare_session_request, _read_request_body
from services.worker_api_service import WorkerApiError
from services.worker_provisioning_service import WorkerProvisioningService

router = APIRouter(prefix="/api")


def _package_var() -> Path:
    return Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))


def _state_path() -> Path:
    configured = os.getenv("AV_IMGDATA_WORKER_API_STATE_PATH", "").strip()
    if not configured:
        return _package_var() / "worker-api-state.json"
    path = Path(configured)
    return path if path.is_absolute() else _package_var() / path


def _read_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"enrollments": {}, "workers": {}, "tokens": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        return {"enrollments": {}, "workers": {}, "tokens": {}}
    return state if isinstance(state, dict) else {"enrollments": {}, "workers": {}, "tokens": {}}


def _parse_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _admin_status() -> Dict[str, Any]:
    state = _read_state()
    now = datetime.now(timezone.utc)
    enrollments = []
    for enrollment_id, raw in state.get("enrollments", {}).items():
        entry = raw if isinstance(raw, dict) else {}
        used_at = entry.get("used_at")
        expires_at = entry.get("expires_at")
        if used_at:
            status = "enrolled"
        elif _parse_time(expires_at) <= now:
            status = "expired"
        else:
            status = "waiting"
        enrollments.append({
            "enrollment_id": str(enrollment_id),
            "created_at": entry.get("created_at"),
            "expires_at": expires_at,
            "used_at": used_at,
            "worker_id": entry.get("worker_id"),
            "status": status,
        })
    enrollments.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    workers = []
    for worker_id, raw in state.get("workers", {}).items():
        worker = raw if isinstance(raw, dict) else {}
        workers.append({
            "worker_id": str(worker_id),
            "status": worker.get("status") or "unknown",
            "version": worker.get("version") or "unknown",
            "capabilities": worker.get("capabilities") if isinstance(worker.get("capabilities"), list) else [],
            "registered_at": worker.get("registered_at"),
            "last_seen_at": worker.get("last_seen_at"),
            "metadata": worker.get("metadata") if isinstance(worker.get("metadata"), dict) else {},
        })
    workers.sort(key=lambda item: str(item.get("last_seen_at") or item.get("registered_at") or ""), reverse=True)
    return {"enrollments": enrollments, "workers": workers}


@router.post("/external_worker_enrollment_start")
async def external_worker_enrollment_start(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    body = await _read_request_body(request)
    enrollment_id = str(body.get("enrollment_id") or "").strip()
    try:
        expires_minutes = int(body.get("expires_minutes") or 15)
    except Exception:
        expires_minutes = 15
    try:
        result = WorkerProvisioningService(
            package_var=_package_var(),
            state_path=_state_path(),
        ).create_enrollment(enrollment_id=enrollment_id, expires_minutes=expires_minutes)
    except WorkerApiError as exc:
        return {"success": False, "error": {"code": 400, "message": exc.code}}
    except Exception as exc:
        return {"success": False, "error": {"code": 500, "message": "worker_enrollment_start_failed", "details": str(exc)}}
    return {"success": True, "data": {"enrollment": result, "status": _admin_status()}}


@router.post("/external_worker_enrollment_status")
async def external_worker_enrollment_status(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    return {"success": True, "data": _admin_status()}
