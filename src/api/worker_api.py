#!/usr/bin/env python3
"""Optional FastAPI router for external AV ImgData workers."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from services.config_service import ConfigService
from services.worker_api_endpoints import handle_worker_api_request
from services.worker_api_service import WorkerApiError, WorkerApiService
from services.worker_provisioning_service import WorkerProvisioningService

router = APIRouter(prefix="/worker-api")
_POST_ACTIONS = {"register", "heartbeat", "claim", "result", "fail"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _package_var() -> Path:
    return Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))


def _config_path() -> Path:
    return _package_var() / "config.json"


def _env_enabled_override() -> Optional[bool]:
    value = os.getenv("AV_IMGDATA_WORKER_API_ENABLED", "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def _worker_api_config() -> Dict[str, Any]:
    try:
        raw = ConfigService(str(_config_path())).readMergedConfig()
    except Exception:
        raw = {}
    config = raw.get("worker_api") if isinstance(raw.get("worker_api"), dict) else {}
    return config if isinstance(config, dict) else {}


def _worker_api_enabled() -> bool:
    override = _env_enabled_override()
    if override is not None:
        return override
    return bool(_worker_api_config().get("ENABLED", False))


def _resolve_package_var_path(value: str) -> Optional[Path]:
    configured = str(value or "").strip()
    if not configured:
        return None
    path = Path(configured)
    return path if path.is_absolute() else _package_var() / path


def _worker_api_state_path() -> Optional[Path]:
    env_path = _resolve_package_var_path(os.getenv("AV_IMGDATA_WORKER_API_STATE_PATH", ""))
    if env_path is not None:
        return env_path
    return _resolve_package_var_path(_worker_api_config().get("STATE_PATH") or "")


def _headers(request: Request) -> Dict[str, str]:
    return {str(key): str(value) for key, value in request.headers.items()}


async def _json_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _disabled_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"status": "error", "code": "worker_api_disabled"})


def _bearer(request: Request) -> str:
    value = str(request.headers.get("authorization") or "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _worker_id(request: Request) -> str:
    return str(request.headers.get("x-worker-id") or "").strip()


def _error_response(exc: WorkerApiError) -> JSONResponse:
    code = exc.code
    status = 401 if code in {"unauthorized", "token_required"} else 403
    if code.endswith("_not_found") or code == "model_file_not_allowed":
        status = 404
    if code.startswith("invalid_") or code.endswith("_required"):
        status = 400
    return JSONResponse(status_code=status, content={"status": "error", "code": code, "message": str(exc)})


@router.get("/status")
async def status() -> JSONResponse:
    if not _worker_api_enabled():
        return _disabled_response()
    service = WorkerApiService(package_var=_package_var(), state_path=_worker_api_state_path())
    return JSONResponse(status_code=200, content={"status": "ok", "service": service.status()})


@router.post("/enroll")
async def enroll(request: Request) -> JSONResponse:
    if not _worker_api_enabled():
        return _disabled_response()
    body = await _json_body(request)
    service = WorkerProvisioningService(package_var=_package_var(), state_path=_worker_api_state_path())
    try:
        payload = service.redeem_enrollment(
            enrollment_code=str(body.get("enrollment_code") or ""),
            worker_id=str(body.get("worker_id") or ""),
        )
        return JSONResponse(status_code=200, content=payload)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.get("/models/{model_pack}/manifest")
async def model_manifest(model_pack: str, request: Request) -> JSONResponse:
    if not _worker_api_enabled():
        return _disabled_response()
    service = WorkerProvisioningService(package_var=_package_var(), state_path=_worker_api_state_path())
    try:
        payload = service.model_manifest(token=_bearer(request), worker_id=_worker_id(request), model_pack=model_pack)
        return JSONResponse(status_code=200, content=payload)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.get("/models/{model_pack}/files/{filename}")
async def model_file(model_pack: str, filename: str, request: Request):
    if not _worker_api_enabled():
        return _disabled_response()
    service = WorkerProvisioningService(package_var=_package_var(), state_path=_worker_api_state_path())
    try:
        path = service.model_file(token=_bearer(request), worker_id=_worker_id(request), model_pack=model_pack, filename=filename)
        return FileResponse(path=str(path), media_type="application/octet-stream", filename=filename)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.post("/{action}")
async def worker_action(action: str, request: Request) -> JSONResponse:
    if action not in _POST_ACTIONS:
        return JSONResponse(status_code=404, content={"status": "error", "code": "unknown_worker_api_route"})
    if not _worker_api_enabled():
        return _disabled_response()
    body = await _json_body(request)
    status_code, payload = handle_worker_api_request(
        action,
        headers=_headers(request),
        body=body,
        package_var=_package_var(),
        state_path=_worker_api_state_path(),
    )
    return JSONResponse(status_code=status_code, content=payload)
