#!/usr/bin/env python3
"""Optional FastAPI router for external AV ImgData workers."""

import sys
import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from services.worker_api_composition_service import (
    WorkerApiCompositionService,
    worker_error_http_status,
)
from services.worker_api_endpoints import handle_worker_api_request
from services.worker_runtime_service import WorkerApiError, WorkerRuntimePathService


router = APIRouter(prefix="/worker-api")
_POST_ACTIONS = {"register", "heartbeat", "claim", "result", "fail"}


@lru_cache(maxsize=4)
def _composition_for(package_var: str) -> WorkerApiCompositionService:
    return WorkerApiCompositionService(package_var=Path(package_var))


def _composition() -> WorkerApiCompositionService:
    return _composition_for(str(WorkerRuntimePathService.resolve_package_var()))


async def _json_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        _backend_debug_log(
            "worker_api_json_body_invalid",
            method=str(getattr(request, "method", "")),
            path=str(getattr(getattr(request, "url", None), "path", "")),
            content_type=str(request.headers.get("content-type") or ""),
            content_length=str(request.headers.get("content-length") or ""),
            worker_id=str(request.headers.get("x-worker-id") or ""),
            error_type=type(exc).__name__,
        )
        return {}
    return body if isinstance(body, dict) else {}


def _headers(request: Request) -> Dict[str, str]:
    return {str(key): str(value) for key, value in request.headers.items()}


def _disabled_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"status": "error", "code": "worker_api_disabled"})


def _bearer(request: Request) -> str:
    value = str(request.headers.get("authorization") or "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _worker_id(request: Request, body: Optional[Dict[str, Any]] = None) -> str:
    header = str(request.headers.get("x-worker-id") or "").strip()
    if header:
        return header
    return str((body or {}).get("worker_id") or "").strip()


def _error_response(exc: WorkerApiError) -> JSONResponse:
    return JSONResponse(
        status_code=worker_error_http_status(exc.code),
        content={"status": "error", "code": exc.code, "message": str(exc)},
    )


async def _run_worker_api_call(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


def _backend_debug_log(event: str, **fields: Any) -> None:
    module = sys.modules.get("api.imgdata_api")
    logger = getattr(module, "backend_debug_log", None) if module is not None else None
    if not callable(logger):
        return
    try:
        logger(event, **fields)
    except Exception:
        pass


def _log_worker_api_response(action: str, status_code: int, payload: Dict[str, Any], body: Dict[str, Any], request: Request) -> None:
    if status_code < 400:
        return
    _backend_debug_log(
        "worker_api_action_failed",
        action=action,
        status_code=status_code,
        response_status=payload.get("status"),
        response_code=payload.get("code"),
        response_message=payload.get("message"),
        worker_id=_worker_id(request, body),
        job_id=str(body.get("job_id") or ""),
    )


@router.get("/status")
async def status() -> JSONResponse:
    composition = _composition()
    if not composition.enabled():
        return _disabled_response()
    return JSONResponse(status_code=200, content={"status": "ok", "service": composition.worker_api.status()})


@router.post("/enroll")
async def enroll(request: Request) -> JSONResponse:
    composition = _composition()
    if not composition.enabled():
        return _disabled_response()
    body = await _json_body(request)
    try:
        payload = composition.provisioning.redeem_enrollment(
            enrollment_code=str(body.get("enrollment_code") or ""),
            worker_id=_worker_id(request, body),
        )
        return JSONResponse(status_code=200, content=payload)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.get("/models/{model_pack}/manifest")
async def model_manifest(model_pack: str, request: Request) -> JSONResponse:
    composition = _composition()
    if not composition.enabled():
        return _disabled_response()
    try:
        payload = composition.provisioning.model_manifest(
            token=_bearer(request),
            worker_id=_worker_id(request),
            model_pack=model_pack,
        )
        return JSONResponse(status_code=200, content=payload)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.get("/models/{model_pack}/files/{filename}")
async def model_file(model_pack: str, filename: str, request: Request):
    composition = _composition()
    if not composition.enabled():
        return _disabled_response()
    try:
        path = composition.provisioning.model_file(
            token=_bearer(request),
            worker_id=_worker_id(request),
            model_pack=model_pack,
            filename=filename,
        )
        return FileResponse(path=str(path), media_type="application/octet-stream", filename=filename)
    except WorkerApiError as exc:
        return _error_response(exc)


@router.post("/{action}")
async def worker_action(action: str, request: Request) -> JSONResponse:
    if action not in _POST_ACTIONS:
        return JSONResponse(status_code=404, content={"status": "error", "code": "unknown_worker_api_route"})
    composition = _composition()
    if not composition.enabled():
        return _disabled_response()
    body = await _json_body(request)
    status_code, payload = await _run_worker_api_call(
        lambda: handle_worker_api_request(
            action,
            headers=_headers(request),
            body=body,
            service=composition.worker_api,
        )
    )
    _log_worker_api_response(action, status_code, payload, body, request)
    return JSONResponse(status_code=status_code, content=payload)
