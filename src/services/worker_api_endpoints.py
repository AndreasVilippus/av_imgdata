#!/usr/bin/env python3
"""Small framework-neutral endpoint adapter for the DSM worker API.

Synology/DSM routing can call ``handle_worker_api_request`` with the route name,
HTTP headers and JSON body. The adapter deliberately contains no web-framework
imports so it can be used from CGI, an existing DSM handler, or future tests.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.worker_api_service import WorkerApiError, WorkerApiService


def _bearer_token(headers: Optional[Dict[str, str]], body: Optional[Dict[str, Any]]) -> str:
    body = body if isinstance(body, dict) else {}
    headers = headers if isinstance(headers, dict) else {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            text = str(value or "").strip()
            if text.lower().startswith("bearer "):
                return text[7:].strip()
    return str(body.get("token") or "")


def handle_worker_api_request(
    action: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    package_var: Optional[Path] = None,
    state_path: Optional[Path] = None,
) -> Tuple[int, Dict[str, Any]]:
    body = body if isinstance(body, dict) else {}
    service = WorkerApiService(package_var=package_var, state_path=state_path)
    token = _bearer_token(headers, body)
    try:
        if action == "register":
            payload = service.register_worker(
                token=token,
                worker_id=str(body.get("worker_id") or ""),
                version=str(body.get("version") or "unknown"),
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
                metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            )
        elif action == "heartbeat":
            payload = service.heartbeat(
                token=token,
                worker_id=str(body.get("worker_id") or ""),
                status=str(body.get("status") or "ready"),
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
                metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            )
        elif action == "claim":
            payload = service.claim_job(
                token=token,
                worker_id=str(body.get("worker_id") or ""),
                capabilities=body.get("capabilities") if isinstance(body.get("capabilities"), list) else None,
            )
        elif action == "result":
            payload = service.record_result(
                token=token,
                worker_id=str(body.get("worker_id") or ""),
                job_id=str(body.get("job_id") or ""),
                result=body.get("result") if isinstance(body.get("result"), dict) else {},
            )
        elif action == "fail":
            payload = service.record_failure(
                token=token,
                worker_id=str(body.get("worker_id") or ""),
                job_id=str(body.get("job_id") or ""),
                error=body.get("error") if isinstance(body.get("error"), dict) else {},
            )
        else:
            return 404, {"status": "error", "code": "unknown_worker_api_action"}
        return 200, payload
    except WorkerApiError as exc:
        status = 401 if exc.code == "unauthorized" else 400
        return status, {"status": "error", "code": exc.code, "message": str(exc)}
