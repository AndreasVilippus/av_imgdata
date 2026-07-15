#!/usr/bin/env python3
"""DSM-authenticated administration endpoints for external worker enrollment."""

import asyncio
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Request

from api.imgdata_api import IMGDATA, _prepare_session_request, _read_request_body
from services.external_worker_processor_service import ExternalWorkerProcessorUnavailable
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


@router.post("/external_worker_face_detect")
async def external_worker_face_detect(request: Request):
    """Run one real face-detection job through a registered external worker.

    This DSM-authenticated diagnostic flow uses the same dispatch and result
    normalization service intended for package workflows. The requested source
    must resolve below the authenticated user's Synology Photos shared folder.
    """

    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    if not image_path:
        return {"success": False, "error": {"code": 400, "message": "image_path_required"}}

    try:
        shared_folder = IMGDATA.core.getSharedFolder(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            folder_name="photo",
        )
        if not shared_folder:
            raise ValueError("photos_shared_folder_not_found")
        source = Path(image_path).expanduser().resolve()
        root = Path(shared_folder).expanduser().resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError("source_path_outside_photos_share") from exc
        if not source.is_file():
            raise ValueError("source_image_not_found")

        composition = _composition()
        if not composition.enabled():
            raise ExternalWorkerProcessorUnavailable("worker_api_disabled")
        processor = composition.external_face_processor(nas_root=root)
        operation_id = f"external-worker-face-detect-{uuid4().hex}"

        result = await asyncio.to_thread(
            processor.execute_face_detect,
            image_path=source,
            local_execute=lambda: (_ for _ in ()).throw(
                ExternalWorkerProcessorUnavailable("external_worker_required")
            ),
            policy="external_required",
            operation="cleanup",
            action="external_worker_face_detect",
            mode="scan",
            operation_id=operation_id,
            source_id=str(source),
            entity_type="image",
            entity_id=str(source),
            det_thresh=max(0.0, min(1.0, float(body.get("det_thresh", 0.5)))),
            max_num=max(0, int(body.get("max_num", 0))),
            det_size=body.get("det_size") if isinstance(body.get("det_size"), list) else [640, 640],
        )
    except ExternalWorkerProcessorUnavailable as exc:
        return {"success": False, "error": {"code": 503, "message": str(exc)}}
    except WorkerApiError as exc:
        return {"success": False, "error": {"code": 400, "message": exc.code}}
    except ValueError as exc:
        return {"success": False, "error": {"code": 400, "message": str(exc)}}
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "external_worker_face_detect_failed",
                "details": str(exc),
            },
        }

    faces = result.get("faces") if isinstance(result.get("faces"), list) else []
    return {
        "success": True,
        "data": {
            "schema_version": 1,
            "component": "external_worker",
            "phase": "finished",
            "operation": "cleanup",
            "action": "external_worker_face_detect",
            "mode": "scan",
            "operation_id": operation_id,
            "execution_target": result.get("execution_target"),
            "job_id": result.get("job_id"),
            "image_path": str(source),
            "faces_count": len(faces),
            "faces": faces,
        },
    }
