#!/usr/bin/env python3
"""DSM-authenticated administration endpoints for external worker enrollment."""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request

from api.imgdata_api import _prepare_session_request, _read_request_body
from services.worker_api_composition_service import WorkerApiCompositionService
from services.worker_runtime_service import WorkerApiError


router = APIRouter(prefix="/api")


def _package_var() -> Path:
    return Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")).resolve()


def _composition(package_var: Optional[Path] = None) -> WorkerApiCompositionService:
    return WorkerApiCompositionService(package_var=package_var or _package_var())


def _services(package_var: Optional[Path] = None):
    composition = _composition(package_var)
    return composition.worker_api, composition.provisioning


def _admin_status():
    return _composition().worker_api.admin_status()


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
        composition = _composition()
        result = composition.provisioning.create_enrollment(
            enrollment_id=enrollment_id,
            expires_minutes=expires_minutes,
        )
        status = composition.worker_api.admin_status()
    except WorkerApiError as exc:
        return {"success": False, "error": {"code": 400, "message": exc.code}}
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "worker_enrollment_start_failed",
                "details": str(exc),
            },
        }
    return {"success": True, "data": {"enrollment": result, "status": status}}


@router.post("/external_worker_enrollment_status")
async def external_worker_enrollment_status(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    try:
        status = _admin_status()
    except WorkerApiError as exc:
        return {"success": False, "error": {"code": 500, "message": exc.code}}
    return {"success": True, "data": status}


@router.post("/external_worker_delete")
async def external_worker_delete(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    body = await _read_request_body(request)
    worker_id = str(body.get("worker_id") or "").strip()
    try:
        composition = _composition()
        deleted = composition.worker_api.delete_worker(worker_id=worker_id)
        status = composition.worker_api.admin_status()
    except WorkerApiError as exc:
        status_code = 404 if exc.code == "worker_not_found" else 400
        return {"success": False, "error": {"code": status_code, "message": exc.code}}
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "worker_delete_failed",
                "details": str(exc),
            },
        }
    return {"success": True, "data": {"deleted": deleted, "status": status}}
