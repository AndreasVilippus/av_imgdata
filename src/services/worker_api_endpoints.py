#!/usr/bin/env python3
"""Small framework-neutral endpoint adapter for the DSM worker API."""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.worker_api_composition_service import worker_error_http_status
from services.worker_api_service import WorkerApiService
from services.worker_runtime_service import WorkerApiError


def _bearer_token(headers: Optional[Dict[str, str]], body: Optional[Dict[str, Any]]) -> str:
    body = body if isinstance(body, dict) else {}
    headers = headers if isinstance(headers, dict) else {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            text = str(value or "").strip()
            if text.lower().startswith("bearer "):
                return text[7:].strip()
    return str(body.get("token") or "")


def _worker_id(headers: Optional[Dict[str, str]], body: Optional[Dict[str, Any]]) -> str:
    body = body if isinstance(body, dict) else {}
    headers = headers if isinstance(headers, dict) else {}
    for key, value in headers.items():
        if key.lower() == "x-worker-id":
            header = str(value or "").strip()
            if header:
                return header
    return str(body.get("worker_id") or "").strip()


def handle_worker_api_request(
    action: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    package_var: Optional[Path] = None,
    state_path: Optional[Path] = None,
    service: Optional[WorkerApiService] = None,
) -> Tuple[int, Dict[str, Any]]:
    body = body if isinstance(body, dict) else {}
    runtime = service or WorkerApiService(package_var=package_var, state_path=state_path)
    token = _bearer_token(headers, body)
    worker_id = _worker_id(headers, body)
    try:
        if action == "register":
            payload = runtime.register_worker(
                token=token,
                worker_id=worker_id,
                version=str(body.get("version") or "unknown"),
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
                metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            )
        elif action == "heartbeat":
            payload = runtime.heartbeat(
                token=token,
                worker_id=worker_id,
                status=str(body.get("status") or "ready"),
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
                metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            )
        elif action == "claim":
            payload = runtime.claim_job(
                token=token,
                worker_id=worker_id,
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
            )
        elif action == "result":
            payload = runtime.record_result(
                token=token,
                worker_id=worker_id,
                job_id=str(body.get("job_id") or ""),
                result=body.get("result") if isinstance(body.get("result"), dict) else {},
            )
        elif action == "fail":
            payload = runtime.record_failure(
                token=token,
                worker_id=worker_id,
                job_id=str(body.get("job_id") or ""),
                error=body.get("error") if isinstance(body.get("error"), dict) else {},
            )
        else:
            return worker_error_http_status("unknown_worker_api_action"), {
                "status": "error",
                "code": "unknown_worker_api_action",
            }
        return 200, payload
    except WorkerApiError as exc:
        return worker_error_http_status(exc.code), {
            "status": "error",
            "code": exc.code,
            "message": str(exc),
        }
