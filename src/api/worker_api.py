#!/usr/bin/env python3
"""Optional FastAPI router for external AV ImgData workers."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from services.worker_api_composition_service import (
    WorkerApiCompositionService,
    worker_error_http_status,
)
from services.worker_api_endpoints import handle_worker_api_request
from services.worker_runtime_service import WorkerApiError


router = APIRouter(prefix="/worker-api")
_POST_ACTIONS = {"register", "heartbeat", "claim", "result", "fail"}


def _package_var() -> Path:
    return Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")).resolve()


@lru_cache(maxsize=4)
def _composition_for(package_var: str) -> WorkerApiCompositionService:
    return WorkerApiCompositionService(package_var=Path(package_var))


def _composition() -> WorkerApiCompositionService:
    return _composition_for(str(_package_var()))


async def _json_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _headers(request: Request) -> Dict[str, str]:
    return {str(key): str(value) for key, value in request.headers.items()}


def _disabled_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"status": "error", "code": "worker_api_disabled"})


def _bearer(request: Request) -> str:
    value = str(request.headers.get("authorization") or "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _worker_id(request: Request, body: Dict[str, Any] | None = None) -> str:
    header = str(request.headers.get("x-worker-id") or "").strip()
    if header:
        return header
    return str((body or {}).get("worker_id") or "").strip()


def _error_response(exc: WorkerApiError) -> JSONResponse:
    return JSONResponse(
        status_code=worker_error_http_status(exc.code),
        content={"status": "error", "code": exc.code, "message": str(exc)},
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
    status_code, payload = handle_worker_api_request(
        action,
        headers=_headers(request),
        body=body,
        service=composition.worker_api,
    )
    return JSONResponse(status_code=status_code, content=payload)
