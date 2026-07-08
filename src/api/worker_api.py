#!/usr/bin/env python3
"""Optional FastAPI router for external AV ImgData workers."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.config_service import ConfigService
from services.worker_api_endpoints import handle_worker_api_request
from services.worker_api_service import WorkerApiService

router = APIRouter(prefix="/worker-api")

_POST_ACTIONS = {"register", "heartbeat", "claim", "result", "fail"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _package_var() -> Path:
    return Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))


def _env_enabled_override() -> Optional[bool]:
    value = os.getenv("AV_IMGDATA_WORKER_API_ENABLED", "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def _worker_api_config() -> Dict[str, Any]:
    try:
        raw = ConfigService().readConfig()
    except Exception:
        raw = {}
    config = raw.get("worker_api") if isinstance(raw.get("worker_api"), dict) else {}
    return config if isinstance(config, dict) else {}


def _worker_api_enabled() -> bool:
    override = _env_enabled_override()
    if override is not None:
        return override
    config = _worker_api_config()
    return bool(config.get("ENABLED", False))


def _worker_api_state_path() -> Optional[Path]:
    configured = str(_worker_api_config().get("STATE_PATH") or "").strip()
    if not configured:
        return None
    path = Path(configured)
    if path.is_absolute():
        return path
    return _package_var() / path


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


@router.get("/status")
async def status() -> JSONResponse:
    if not _worker_api_enabled():
        return _disabled_response()
    service = WorkerApiService(package_var=_package_var(), state_path=_worker_api_state_path())
    return JSONResponse(status_code=200, content={"status": "ok", "service": service.status()})


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
