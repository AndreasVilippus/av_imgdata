#!/usr/bin/env python3
import asyncio
import hashlib
import json
import logging
import os
import time
import traceback
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlsplit
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from api.session_manager import SessionBootstrapRequired, SessionManager, SessionManagerError
from imgdata import ImgDataOperationError, ImgDataService

router = APIRouter(prefix="/api")

DSM_INTERNAL_BASE_URL = os.getenv("DSM_INTERNAL_BASE_URL", "https://127.0.0.1:5001")
DSM_INTERNAL_VERIFY_SSL = os.getenv("DSM_INTERNAL_VERIFY_SSL", "false").lower() in ("1", "true", "yes")
SESSION_MANAGER = SessionManager(verify_ssl=DSM_INTERNAL_VERIFY_SSL, timeout=20)
IMGDATA = ImgDataService(SESSION_MANAGER)

_REQUEST_MUTATION_CONTEXT: ContextVar[Dict[str, Any]] = ContextVar("request_mutation_context", default={})
_DEBUG_LOGGER = logging.getLogger("av_imgdata.backend_debug")
_DEBUG_LOGGER.setLevel(logging.INFO)
_DEBUG_LOGGER.propagate = False
_DEBUG_LOGGER_SIGNATURE: Optional[Tuple[str, int, int]] = None


def _configured_max_photos_persons() -> int:
    config = IMGDATA.getRuntimeConfig()
    photos = config.get("photos", {}) if isinstance(config.get("photos"), dict) else {}
    return max(1, int(photos["MAX_PHOTOS_PERSONS"]))


def _backend_debug_config() -> Dict[str, Any]:
    try:
        config = IMGDATA.getRuntimeConfig()
    except Exception:
        return {}
    debug = config.get("debug") if isinstance(config.get("debug"), dict) else {}
    return debug if isinstance(debug, dict) else {}


def is_backend_debug_enabled() -> bool:
    override = os.getenv("AV_IMGDATA_BACKEND_DEBUG", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return bool(_backend_debug_config().get("BACKEND_DEBUG_ENABLED", False))


def backend_debug_log_path() -> str:
    debug = _backend_debug_config()
    configured = str(debug.get("BACKEND_DEBUG_LOG_PATH") or "").strip()
    if configured:
        return configured
    var_dir = os.getenv("SYNOPKG_PKGVAR")
    if var_dir:
        return str(Path(var_dir) / "backend-debug.log")
    return str(Path(IMGDATA.config._config_path).parent / "backend-debug.log")


def _backend_debug_logger() -> Optional[logging.Logger]:
    global _DEBUG_LOGGER_SIGNATURE
    debug = _backend_debug_config()
    path = backend_debug_log_path()
    max_bytes = max(65536, min(10485760, int(debug.get("BACKEND_DEBUG_LOG_MAX_BYTES") or 1048576)))
    backups = max(1, min(10, int(debug.get("BACKEND_DEBUG_LOG_BACKUPS") or 3)))
    signature = (path, max_bytes, backups)
    if _DEBUG_LOGGER_SIGNATURE == signature and _DEBUG_LOGGER.handlers:
        return _DEBUG_LOGGER

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    except Exception:
        return None

    handler.setFormatter(logging.Formatter("%(message)s"))
    for old_handler in list(_DEBUG_LOGGER.handlers):
        _DEBUG_LOGGER.removeHandler(old_handler)
        try:
            old_handler.close()
        except Exception:
            pass
    _DEBUG_LOGGER.addHandler(handler)
    _DEBUG_LOGGER_SIGNATURE = signature
    return _DEBUG_LOGGER


def _safe_debug_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _safe_debug_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_debug_value(item) for item in value[:100]]
    return str(value)


def _debug_user_key(user_key: str) -> str:
    if not user_key:
        return ""
    return hashlib.sha256(user_key.encode("utf-8", errors="ignore")).hexdigest()[:12]


async def _run_backend_call(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


def backend_debug_log(event: str, **fields: Any) -> None:
    if not is_backend_debug_enabled():
        return
    logger = _backend_debug_logger()
    if logger is None:
        return
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": str(event),
    }
    payload.update({key: _safe_debug_value(value) for key, value in fields.items()})
    try:
        logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception:
        pass


IMGDATA.setDebugLogger(backend_debug_log)


def _progress_debug_summary(progress: Dict[str, Any]) -> Dict[str, Any]:
    status = progress.get("status") if isinstance(progress.get("status"), dict) else {}
    return {
        "operation_id": progress.get("operation_id"),
        "revision": progress.get("revision"),
        "action": progress.get("action"),
        "running": bool(progress.get("running")),
        "active": bool(progress.get("active")),
        "stale": bool(progress.get("stale")),
        "stop_requested": bool(progress.get("stop_requested")),
        "resume_available": bool(progress.get("resume_available")),
        "findings_count": int(progress.get("findings_count") or 0),
        "transferred_count": int(progress.get("transferred_count") or 0),
        "status_phase": status.get("phase"),
        "status_operation": status.get("operation"),
    }


@router.get("/ping")
async def ping():
    return {
        "success": True,
        "data": {
            "output": "pong"
        }
    }


def _merge_cookie_sources(request_cookies: Dict[str, str], body_cookies: Dict[str, str]) -> Dict[str, str]:
    merged = dict(request_cookies)
    for key, value in body_cookies.items():
        if isinstance(value, str) and value:
            merged[key] = value
    return merged


def _dsm_base_url_from_request(request: Request) -> str:
    for candidate in (request.headers.get("origin"), request.headers.get("referer")):
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if not parsed.scheme or not parsed.netloc:
            continue
        if parsed.port == 9771:
            continue
        return f"{parsed.scheme}://{parsed.netloc}"
    return DSM_INTERNAL_BASE_URL


async def _prepare_session_request(
    request: Request,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    try:
        body = await request.json()
    except Exception:
        body = {}

    body_cookies = body.get("cookies") if isinstance(body.get("cookies"), dict) else {}
    cookies = _merge_cookie_sources(dict(request.cookies), body_cookies)
    if not cookies:
        return None, {"success": False, "error": {"code": 401, "message": "missing session cookie"}}
    if "id" not in cookies and "_SSID" not in cookies:
        return None, {"success": False, "error": {"code": 401, "message": "No DSM session cookie found"}}

    dsm_base_url = _dsm_base_url_from_request(request)
    user_key = SESSION_MANAGER.user_key_from_cookies(cookies)
    if not user_key:
        return None, {"success": False, "error": {"code": 401, "message": "No session key (id/_SSID) for user separation"}}

    body_kk_message = body.get("kk_message")
    body_syno_token = body.get("synoToken") or body.get("syno_token")
    body_account = body.get("account")
    header_syno_token = request.headers.get("x-syno-token")

    IMGDATA.update_session_context(
        user_key=user_key,
        base_url=dsm_base_url,
        kk_message=body_kk_message,
        synotoken=body_syno_token or header_syno_token,
        account=body_account,
        cookies=cookies,
    )

    return {
        "user_key": user_key,
        "cookies": cookies,
        "base_url": dsm_base_url,
    }, None


async def _read_request_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        _REQUEST_MUTATION_CONTEXT.set({})
        return {}
    if not isinstance(body, dict):
        _REQUEST_MUTATION_CONTEXT.set({})
        return {}

    normalized_check_type = str(
        body.get("check_type")
        or body.get("review_type")
        or body.get("finding_type")
        or body.get("type")
        or ""
    ).strip().lower()
    _REQUEST_MUTATION_CONTEXT.set(
        {
            "auto": bool(body.get("auto")),
            "check_type": normalized_check_type,
            "image_path": str(body.get("image_path") or "").strip(),
        }
    )
    return body


def _session_exception_response(
    exc: Union[SessionBootstrapRequired, SessionManagerError],
    *,
    bootstrap_message: str,
) -> Dict[str, Any]:
    if isinstance(exc, SessionBootstrapRequired):
        return {
            "success": False,
            "error": {
                "code": 401,
                "message": bootstrap_message,
                "details": str(exc),
            },
        }
    message = "session_manager_error" if exc.status_code == 401 else "synology_api_error"
    return {
        "success": False,
        "error": {"code": exc.status_code, "message": message, "details": exc.detail},
    }


def _session_exception_debug_detail(exc: Union[SessionBootstrapRequired, SessionManagerError]) -> Dict[str, Any]:
    if not isinstance(exc, SessionManagerError) or not isinstance(exc.detail, dict):
        return {}
    return exc.detail


def _exception_details(exc: Exception) -> Any:
    if isinstance(exc, ImgDataOperationError):
        return exc.details
    return str(exc)


def _operation_exception_response(exc: Exception, *, message: str, code: int = 500) -> Dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": _exception_details(exc),
        },
    }


def _compact_checks_findings_update(findings_update: Any, *, image_path: str = "") -> Any:
    if not isinstance(findings_update, dict):
        return findings_update

    entries = findings_update.get("entries") if isinstance(findings_update.get("entries"), list) else []
    normalized_path = str(image_path or "").strip()
    compact = {
        "status": str(findings_update.get("status") or ""),
        "check_type": str(findings_update.get("check_type") or ""),
        "source_mode": str(findings_update.get("source_mode") or "findings"),
        "save_only": bool(findings_update.get("save_only")),
        "count": int(findings_update.get("count") if findings_update.get("count") is not None else len(entries)),
    }
    if normalized_path:
        compact["image_path"] = normalized_path
        compact["image_entries"] = [
            entry for entry in entries
            if isinstance(entry, dict) and str(entry.get("image_path") or "").strip() == normalized_path
        ]
    return compact



def _enrich_checks_progress_counters(progress: Any) -> Any:
    if not isinstance(progress, dict):
        return progress
    normalized_type = str(progress.get("check_type") or "").strip().lower()
    source_mode = str(progress.get("source_mode") or "").strip().lower()
    save_only = bool(progress.get("save_only"))
    if source_mode != "scan" or not save_only or not normalized_type:
        return progress
    if progress.get("findings_count") is not None:
        return progress

    statuses = None
    try:
        status_reader = getattr(IMGDATA, "getChecksFindingsStatus", None)
        if callable(status_reader):
            statuses = status_reader()
    except Exception:
        statuses = None

    if isinstance(statuses, dict) and isinstance(statuses.get("statuses"), dict):
        statuses = statuses.get("statuses")
    current = statuses.get(normalized_type) if isinstance(statuses, dict) else None
    if isinstance(current, dict):
        try:
            progress = dict(progress)
            progress["findings_count"] = max(0, int(current.get("count") or 0))
        except Exception:
            pass
    return progress

def _compact_file_analysis_progress(progress: Any) -> Any:
    if not isinstance(progress, dict):
        return progress

    unused_ui_fields = {
        "configured_extensions",
        "directories_read",
        "extensions",
        "job_id",
        "last_updated_at",
    }
    return {
        key: value
        for key, value in progress.items()
        if key not in unused_ui_fields
    }


def _save_name_mapping_if_requested(*, save_mapping: bool, source_name: Any, target_name: Any) -> bool:
    normalized_source = str(source_name or "").strip()
    normalized_target = str(target_name or "").strip()
    if not save_mapping or not normalized_source or not normalized_target:
        return False
    return IMGDATA.saveNameMapping(
        source_name=normalized_source,
        target_name=normalized_target,
    )


def _is_browser_image_compatible_path(path: str) -> bool:
    extension = Path(path).suffix.lower().lstrip(".")
    return extension in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "avif"}


def _image_preview_unavailable_response() -> Response:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" viewBox="0 0 640 420">'
        '<rect width="640" height="420" fill="#f3f4f6"/>'
        '<rect x="160" y="110" width="320" height="200" rx="8" fill="#ffffff" stroke="#cbd5e1"/>'
        '<path d="M230 250l55-68 45 52 34-40 46 56z" fill="#cbd5e1"/>'
        '<circle cx="398" cy="166" r="22" fill="#cbd5e1"/>'
        '<text x="320" y="348" text-anchor="middle" font-family="Arial, sans-serif" '
        'font-size="24" fill="#475569">Preview unavailable</text>'
        "</svg>"
    )
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _refresh_checks_mutation_state(
    session_ctx: Dict[str, Any],
    *,
    check_type: str,
    image_path: str,
    original_face_data: Optional[Dict[str, Any]] = None,
    replacement_face_data: Optional[Dict[str, Any]] = None,
    resolved_delta: int = 0,
    ignored_delta: int = 0,
) -> Optional[Dict[str, Any]]:
    normalized_type = str(check_type or "").strip().lower()
    normalized_path = str(image_path or "").strip()
    if not normalized_type or not normalized_path:
        return None

    findings_update = IMGDATA.refreshChecksFindingEntriesForImage(
        check_type=normalized_type,
        image_path=normalized_path,
        user_key=session_ctx["user_key"],
        cookies=session_ctx["cookies"],
        base_url=session_ctx["base_url"],
        original_face_data=original_face_data,
        replacement_face_data=replacement_face_data,
    )
    IMGDATA.refreshChecksScanProgressForImage(
        user_key=session_ctx["user_key"],
        check_type=normalized_type,
        image_path=normalized_path,
        cookies=session_ctx["cookies"],
        base_url=session_ctx["base_url"],
        original_face_data=original_face_data,
        replacement_face_data=replacement_face_data,
        resolved_delta=resolved_delta,
        ignored_delta=ignored_delta,
    )
    return findings_update



def _snapshot_name_conflicts_mutation_state(
    session_ctx: Dict[str, Any],
    *,
    check_type: str,
    image_path: str,
    original_face_data: Optional[Dict[str, Any]] = None,
    replacement_face_data: Optional[Dict[str, Any]] = None,
    resolved_delta: int = 0,
    ignored_delta: int = 0,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Update name-conflict findings from the existing snapshot without re-reading the image."""
    normalized_type = str(check_type or "").strip().lower()
    normalized_path = str(image_path or "").strip()
    if normalized_type != "name_conflicts" or not normalized_path:
        return None, None

    with IMGDATA.file_analysis.lockCheckFindings(normalized_type):
        return _snapshot_name_conflicts_mutation_state_locked(
            session_ctx,
            check_type=normalized_type,
            image_path=normalized_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
            resolved_delta=resolved_delta,
            ignored_delta=ignored_delta,
        )


def _snapshot_name_conflicts_mutation_state_locked(
    session_ctx: Dict[str, Any],
    *,
    check_type: str,
    image_path: str,
    original_face_data: Optional[Dict[str, Any]] = None,
    replacement_face_data: Optional[Dict[str, Any]] = None,
    resolved_delta: int = 0,
    ignored_delta: int = 0,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    normalized_type = str(check_type or "").strip().lower()
    normalized_path = str(image_path or "").strip()
    try:
        findings = IMGDATA.file_analysis.readCheckFindings(normalized_type)
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []

        original = original_face_data if isinstance(original_face_data, dict) else {}
        replacement = replacement_face_data if isinstance(replacement_face_data, dict) else {}
        def collect_face_names(source: Any) -> set:
            names = set()
            if not isinstance(source, dict):
                return names
            for key in ("name", "face_name", "person_name", "source_name", "target_name", "old_name", "new_name"):
                value = str(source.get(key) or "").strip()
                if value:
                    names.add(value)
            for key in (
                "left_face_signature",
                "right_face_signature",
                "face_signature",
                "signature",
                "left_face",
                "right_face",
                "metadata_face",
                "photos_face",
                "original_face_data",
                "replacement_face_data",
            ):
                names.update(collect_face_names(source.get(key)))
            return names

        candidate_names = collect_face_names(original)
        candidate_names.update(collect_face_names(replacement))
        candidate_signatures = {
            str(original.get("left_face_signature") or "").strip(),
            str(original.get("right_face_signature") or "").strip(),
            str(original.get("face_signature") or "").strip(),
            str(original.get("signature") or "").strip(),
            str(replacement.get("left_face_signature") or "").strip(),
            str(replacement.get("right_face_signature") or "").strip(),
            str(replacement.get("face_signature") or "").strip(),
            str(replacement.get("signature") or "").strip(),
        }
        candidate_signatures = {value for value in candidate_signatures if value}

        def matches_mutated_snapshot_entry(entry: Any) -> bool:
            if not isinstance(entry, dict):
                return False
            if str(entry.get("image_path") or "").strip() != normalized_path:
                return False
            if candidate_signatures:
                entry_signatures = {
                    str(entry.get("left_face_signature") or "").strip(),
                    str(entry.get("right_face_signature") or "").strip(),
                    str(entry.get("face_signature") or "").strip(),
                    str(entry.get("signature") or "").strip(),
                }
                if any(value and value in candidate_signatures for value in entry_signatures):
                    return True
            if candidate_names:
                entry_names = collect_face_names(entry)
                if any(value and value in candidate_names for value in entry_names):
                    return True
            # If the request does not carry a stable token, remove all snapshot
            # findings for the changed image. This preserves the no-re-read
            # invariant and prevents same-image combination loops.
            return not candidate_signatures and not candidate_names

        remaining_entries = [entry for entry in entries if not matches_mutated_snapshot_entry(entry)]
        removed_count = max(0, len(entries) - len(remaining_entries))

        updated_payload = dict(findings) if isinstance(findings, dict) else {}
        updated_payload["check_type"] = normalized_type
        updated_payload["source_mode"] = str(updated_payload.get("source_mode") or "findings")
        updated_payload["save_only"] = bool(updated_payload.get("save_only", False))
        updated_payload["entries"] = remaining_entries
        updated_payload["count"] = len(remaining_entries)
        if resolved_delta:
            updated_payload["resolved_count"] = max(0, int(updated_payload.get("resolved_count") or 0) + int(resolved_delta))
        if ignored_delta:
            updated_payload["ignored_count"] = max(0, int(updated_payload.get("ignored_count") or 0) + int(ignored_delta))
        IMGDATA.file_analysis.writeCheckFindings(normalized_type, updated_payload)

        progress = IMGDATA.getChecksProgress(session_ctx["user_key"], normalized_type)
        if isinstance(progress, dict):
            progress = dict(progress)
            progress["findings_count"] = len(remaining_entries)
            progress["last_updated_at"] = IMGDATA._utcNowIso()
            progress["resolved_count"] = max(0, int(progress.get("resolved_count") or 0) + int(resolved_delta or 0))
            progress["ignored_count"] = max(0, int(progress.get("ignored_count") or 0) + int(ignored_delta or 0))
            resume_cursor = progress.get("resume_cursor")
            if isinstance(resume_cursor, dict):
                resume_cursor = dict(resume_cursor)
                resume_cursor["findings_count"] = len(remaining_entries)
                resume_cursor["resolved_count"] = progress["resolved_count"]
                resume_cursor["ignored_count"] = progress["ignored_count"]
                pending_entries = resume_cursor.get("pending_entries")
                if isinstance(pending_entries, list):
                    resume_cursor["pending_entries"] = [
                        entry for entry in pending_entries
                        if not matches_mutated_snapshot_entry(entry)
                    ]
                else:
                    resume_cursor["pending_entries"] = []
                progress["resume_cursor"] = resume_cursor
            state_key = IMGDATA._checksStateKey(session_ctx["user_key"], normalized_type)
            IMGDATA.runtime_state.write("checks_progress", state_key, progress)

        compact = _compact_checks_findings_update(updated_payload, image_path=normalized_path)
        if isinstance(compact, dict):
            compact["removed_count"] = removed_count
            compact["snapshot_update"] = True
        return compact, None
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return None, _session_exception_response(exc, bootstrap_message="checks_mutation_snapshot_bootstrap_required")["error"]
    except Exception as exc:
        return None, _operation_exception_response(exc, message="checks_mutation_snapshot_failed")["error"]


def _safe_refresh_checks_mutation_state(
    session_ctx: Dict[str, Any],
    *,
    check_type: str,
    image_path: str,
    original_face_data: Optional[Dict[str, Any]] = None,
    replacement_face_data: Optional[Dict[str, Any]] = None,
    resolved_delta: int = 0,
    ignored_delta: int = 0,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    normalized_type = str(check_type or "").strip().lower()

    # Name-conflict mutations must not re-read the changed image.
    # They update the persisted snapshot/finding list only, so same-image
    # combinations cannot re-enter the active review flow.
    if normalized_type == "name_conflicts":
        return _snapshot_name_conflicts_mutation_state(
            session_ctx,
            check_type=check_type,
            image_path=image_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
            resolved_delta=resolved_delta,
            ignored_delta=ignored_delta,
        )

    try:
        refresh_kwargs = {
            "check_type": check_type,
            "image_path": image_path,
        }
        if original_face_data is not None:
            refresh_kwargs["original_face_data"] = original_face_data
        if replacement_face_data is not None:
            refresh_kwargs["replacement_face_data"] = replacement_face_data
        if resolved_delta:
            refresh_kwargs["resolved_delta"] = resolved_delta
        if ignored_delta:
            refresh_kwargs["ignored_delta"] = ignored_delta
        findings_update = _refresh_checks_mutation_state(session_ctx, **refresh_kwargs)
        return findings_update, None
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return None, _session_exception_response(exc, bootstrap_message="checks_mutation_refresh_bootstrap_required")["error"]
    except Exception as exc:
        return None, _operation_exception_response(exc, message="checks_mutation_refresh_failed")["error"]


@router.post("/status")
async def status(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        persons_started = time.monotonic()
        persons_status = await _run_backend_call(
            lambda: IMGDATA.status_persons(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                background=True,
            )
        )
        backend_debug_log(
            "status_phase",
            phase="persons",
            duration_ms=round((time.monotonic() - persons_started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            known=int(persons_status.get("known") or 0) if isinstance(persons_status, dict) else None,
            total=int(persons_status.get("total") or 0) if isinstance(persons_status, dict) else None,
        )
        system_started = time.monotonic()
        system_status = await _run_backend_call(
            lambda: IMGDATA.status_system(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                background=True,
            )
        )
        backend_debug_log(
            "status_phase",
            phase="system",
            duration_ms=round((time.monotonic() - system_started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        backend_debug_log(
            "status_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return _session_exception_response(exc, bootstrap_message="status_bootstrap_required")

    backend_debug_log(
        "status_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
    )
    return {
        "success": True,
        "data": {
            "persons": persons_status,
            "system": system_status,
        },
    }


@router.post("/exiftool_status")
async def exiftool_status(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    data = await _run_backend_call(lambda: IMGDATA.exiftool_status(background=True))
    return {
        "success": True,
        "data": data,
    }


@router.post("/insightface_status")
async def insightface_status(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": await _run_backend_call(lambda: IMGDATA.insightFaceStatus()),
    }


@router.post("/image_backend_status")
async def image_backend_status(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": await _run_backend_call(lambda: IMGDATA.imageBackendStatus()),
    }


@router.post("/insightface_model_delete")
async def insightface_model_delete(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    try:
        result = IMGDATA.deleteInsightFaceModel(model_name=str(body.get("model_name") or ""))
    except ValueError as exc:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": str(exc),
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "insightface_model_delete_failed",
                "details": str(exc),
            },
        }

    return {
        "success": True,
        "data": result,
    }


@router.post("/exiftool_extensions")
async def exiftool_extensions(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    data = IMGDATA.exiftool_extensions()
    if not data.get("success"):
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": data.get("error") or "exiftool_extensions_unavailable",
            },
        }

    return {
        "success": True,
        "data": data,
    }


@router.post("/exiftool_install")
async def exiftool_install(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        result = IMGDATA.install_exiftool()
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "exiftool_install_failed",
                "details": str(exc),
            },
        }

    return {
        "success": bool(result.get("success")),
        "data": result if result.get("success") else {},
        "error": None if result.get("success") else {
            "code": 500,
            "message": result.get("message") or "exiftool_install_failed",
        },
    }


@router.post("/exiftool_remove")
async def exiftool_remove(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        result = IMGDATA.remove_exiftool()
    except Exception as exc:
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "exiftool_remove_failed",
                "details": str(exc),
            },
        }

    return {
        "success": bool(result.get("success")),
        "data": result if result.get("success") else {},
        "error": None if result.get("success") else {
            "code": 500,
            "message": result.get("message") or "exiftool_remove_failed",
        },
    }


@router.post("/face_matching_action")
async def face_matching_action(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    action = body.get("action", "")
    auto = bool(body.get("auto"))
    save_only = bool(body.get("save_only"))
    recognize_persons = bool(body.get("recognize_persons"))
    skip_unknown_persons = bool(body.get("skip_unknown_persons"))
    resume_from_progress = bool(body.get("resume_from_progress"))
    refresh = bool(body.get("refresh"))
    default_limit = _configured_max_photos_persons()
    limit = body.get("limit", default_limit)
    offset = body.get("offset", 0)
    skip_face_ids = body.get("skip_face_ids") if isinstance(body.get("skip_face_ids"), list) else []
    skip_targets = body.get("skip_targets") if isinstance(body.get("skip_targets"), list) else []
    try:
        limit = int(limit)
    except Exception:
        limit = default_limit
    try:
        offset = int(offset)
    except Exception:
        offset = 0
    normalized_skip_face_ids = []
    normalized_skip_targets = []
    for face_id in skip_face_ids:
        try:
            normalized_skip_face_ids.append(int(face_id))
        except Exception:
            continue
    for target in skip_targets:
        normalized = str(target or "").strip()
        if normalized:
            normalized_skip_targets.append(normalized)

    if action not in {"search_photo_face_in_file", "search_file_face_in_sources", "mark_missing_photos_faces", "search_missing_faces_insightface", "load_photo_face_match_findings"}:
        backend_debug_log(
            "face_matching_action_rejected",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            action=action,
        )
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "unsupported_face_matching_action",
                "details": action,
            },
        }

    try:
        backend_debug_log(
            "face_matching_action_start",
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            action=action,
            auto=auto,
            save_only=save_only,
            recognize_persons=recognize_persons,
            skip_unknown_persons=skip_unknown_persons,
            resume_from_progress=resume_from_progress,
            refresh=refresh,
            limit=limit,
            offset=offset,
            skip_face_ids_count=len(normalized_skip_face_ids),
            skip_targets_count=len(normalized_skip_targets),
            findings_action=str(body.get("findings_action") or body.get("source_action") or "").strip(),
        )
        if action in {"search_photo_face_in_file", "search_file_face_in_sources", "mark_missing_photos_faces", "search_missing_faces_insightface"}:
            face_matches = await _run_backend_call(
                lambda: IMGDATA.startFaceMatchingDiscovery(
                    user_key=session_ctx["user_key"],
                    cookies=session_ctx["cookies"],
                    base_url=session_ctx["base_url"],
                    action=action,
                    limit=limit,
                    offset=offset,
                    skip_face_ids=normalized_skip_face_ids,
                    skip_targets=normalized_skip_targets,
                    auto=auto,
                    save_only=save_only,
                    resume_from_progress=resume_from_progress,
                    recognize_persons=recognize_persons,
                    skip_unknown_persons=skip_unknown_persons,
                )
            )
        else:
            face_matches = await _run_backend_call(
                lambda: IMGDATA.getFaceMatchFindingEntriesLocked(
                    user_key=session_ctx["user_key"],
                    cookies=session_ctx["cookies"],
                    base_url=session_ctx["base_url"],
                    action=str(body.get("findings_action") or body.get("source_action") or "").strip(),
                    auto=auto,
                    refresh=refresh,
                ),
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        backend_debug_log(
            "face_matching_action_session_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            action=action,
            error_type=type(exc).__name__,
            error=str(exc),
            error_detail=_session_exception_debug_detail(exc),
        )
        return _session_exception_response(exc, bootstrap_message="face_matching_action_bootstrap_required")
    except Exception as exc:
        backend_debug_log(
            "face_matching_action_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            action=action,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _operation_exception_response(exc, message="face_matching_action_failed")

    result_summary = _progress_debug_summary(face_matches) if isinstance(face_matches, dict) else {}
    if isinstance(face_matches, dict) and "entries" in face_matches:
        entries = face_matches.get("entries") if isinstance(face_matches.get("entries"), list) else []
        result_summary = {
            "status": face_matches.get("status"),
            "action": face_matches.get("action"),
            "count": len(entries),
            "transferred_count": int(face_matches.get("transferred_count") or 0),
            "save_only": bool(face_matches.get("save_only")),
            "auto": bool(face_matches.get("auto")),
        }
    backend_debug_log(
        "face_matching_action_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        action=action,
        result=result_summary,
    )
    return {
        "success": True,
        "data": {
            "action": action,
            "auto": auto,
            "save_only": save_only,
            "resume_from_progress": resume_from_progress,
            "refresh": refresh,
            "face_matches": face_matches
        },
    }


@router.post("/face_matching_findings_status")
async def face_matching_findings_status(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    requested_action = str(body.get("action") or body.get("source_action") or "").strip().lower()
    findings = await _run_backend_call(lambda: IMGDATA.getFaceMatchFindingsStatus())
    findings_action = str(findings.get("action") or "").strip().lower()
    if requested_action and findings_action and requested_action != findings_action:
        count = 0
    else:
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        try:
            count = max(0, int(findings.get("count") if "count" in findings else len(entries)))
        except (TypeError, ValueError):
            count = len(entries)
    backend_debug_log(
        "face_matching_findings_status",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        requested_action=requested_action,
        findings_action=findings_action,
        status=str(findings.get("status") or ""),
        count=count,
        transferred_count=int(findings.get("transferred_count") or 0),
    )
    return {
        "success": True,
        "data": {
            "status": str(findings.get("status") or ""),
            "action": findings_action,
            "requested_action": requested_action,
            "count": count,
            "transferred_count": int(findings.get("transferred_count") or 0),
            "save_only": bool(findings.get("save_only")) if count else False,
            "auto": bool(findings.get("auto")) if count else False,
        },
    }


@router.post("/face_matching_progress")
async def face_matching_progress(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        progress = await _run_backend_call(
            lambda: IMGDATA.getFaceMatchingProgress(session_ctx["user_key"], compact_for_response=True)
        )
    except Exception as exc:
        backend_debug_log(
            "face_matching_progress_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise
    backend_debug_log(
        "face_matching_progress",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        progress=_progress_debug_summary(progress),
    )
    return {
        "success": True,
        "data": progress,
    }


@router.post("/face_matching_stop")
async def face_matching_stop(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    progress = IMGDATA.requestStopFaceMatching(session_ctx["user_key"])
    backend_debug_log(
        "face_matching_stop",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        progress=_progress_debug_summary(progress),
    )
    return {
        "success": True,
        "data": progress,
    }


@router.post("/face_assign_match")
async def face_assign_match(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    face_id = body.get("face_id")
    person_id = body.get("person_id")
    person_name = body.get("person_name")
    save_mapping = bool(body.get("save_mapping"))
    source_name = body.get("source_name")
    try:
        face_id = int(face_id)
        person_id = int(person_id)
    except Exception:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_or_person_id",
            },
        }
    if not isinstance(person_name, str) or not person_name.strip():
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_person_name",
            },
        }

    try:
        data = IMGDATA.applyPhotoFaceMatchAssignment(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            face_id=face_id,
            person_id=person_id,
            person_name=person_name.strip(),
            save_mapping=save_mapping,
            source_name=source_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        backend_debug_log(
            "face_assign_match_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            face_id=face_id,
            person_id=person_id,
            error_type=type(exc).__name__,
            error=str(exc),
            error_detail=_session_exception_debug_detail(exc),
        )
        return _session_exception_response(exc, bootstrap_message="face_assign_match_bootstrap_required")
    except Exception as exc:
        backend_debug_log(
            "face_assign_match_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            face_id=face_id,
            person_id=person_id,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _operation_exception_response(exc, message="face_assign_match_failed")

    backend_debug_log(
        "face_assign_match_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        face_id=face_id,
        person_id=person_id,
        findings_count=int((data.get("findings_update") or {}).get("count") or 0) if isinstance(data.get("findings_update"), dict) else None,
        transferred_count=int((data.get("findings_update") or {}).get("transferred_count") or 0) if isinstance(data.get("findings_update"), dict) else None,
        mapping_saved=bool(data.get("mapping_saved")),
    )
    return {
        "success": True,
        "data": data,
    }


@router.post("/face_create_match")
async def face_create_match(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    face_id = body.get("face_id")
    person_name = body.get("person_name")
    save_mapping = bool(body.get("save_mapping"))
    source_name = body.get("source_name")
    try:
        face_id = int(face_id)
    except Exception:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_id",
            },
        }
    if not isinstance(person_name, str) or not person_name.strip():
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_person_name",
            },
        }

    try:
        data = IMGDATA.applyPhotoFaceMatchPersonCreation(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            face_id=face_id,
            person_name=person_name.strip(),
            save_mapping=save_mapping,
            source_name=source_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        backend_debug_log(
            "face_create_match_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            face_id=face_id,
            error_type=type(exc).__name__,
            error=str(exc),
            error_detail=_session_exception_debug_detail(exc),
        )
        return _session_exception_response(exc, bootstrap_message="face_create_match_bootstrap_required")
    except Exception as exc:
        backend_debug_log(
            "face_create_match_exception",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            user_key_hash=_debug_user_key(session_ctx["user_key"]),
            face_id=face_id,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _operation_exception_response(exc, message="face_create_match_failed")

    backend_debug_log(
        "face_create_match_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        face_id=face_id,
        person_id=data.get("person_id"),
        findings_count=int((data.get("findings_update") or {}).get("count") or 0) if isinstance(data.get("findings_update"), dict) else None,
        transferred_count=int((data.get("findings_update") or {}).get("transferred_count") or 0) if isinstance(data.get("findings_update"), dict) else None,
        mapping_saved=bool(data.get("mapping_saved")),
    )
    return {
        "success": True,
        "data": data,
    }


@router.post("/face_skip_match")
async def face_skip_match(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    face_id = body.get("face_id")
    image_path = str(body.get("image_path") or "").strip()
    metadata_face = body.get("metadata_face")

    parsed_face_id = None
    if face_id not in (None, ""):
        try:
            parsed_face_id = int(face_id)
        except Exception:
            return {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "invalid_face_skip_match_request",
                },
            }

    if parsed_face_id is None and (not image_path or not isinstance(metadata_face, dict)):
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_skip_match_request",
            },
        }

    try:
        if parsed_face_id is not None:
            findings_update = IMGDATA.removeFaceMatchFindingEntry(
                face_id=parsed_face_id,
                increment_transferred_count=False,
            )
        else:
            findings_update = IMGDATA.removeFaceMatchFindingMetadataEntry(
                image_path=image_path,
                metadata_face=metadata_face,
                increment_transferred_count=False,
            )
    except Exception as exc:
        return _operation_exception_response(exc, message="face_skip_match_failed")

    return {
        "success": True,
        "data": {
            "face_id": parsed_face_id,
            "image_path": image_path,
            "findings_update": findings_update,
        },
    }


@router.post("/face_apply_metadata_match")
async def face_apply_metadata_match(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    metadata_face = body.get("metadata_face")
    person_name = str(body.get("person_name") or "").strip()
    if not image_path or not isinstance(metadata_face, dict) or not person_name:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_apply_metadata_match_request",
            },
        }

    try:
        result = IMGDATA.replaceMetadataFaceName(
            image_path=image_path,
            face_data=metadata_face,
            new_name=person_name,
        )
        findings_update = (
            IMGDATA.removeFaceMatchFindingMetadataEntry(
                image_path=image_path,
                metadata_face=metadata_face,
                increment_transferred_count=True,
            )
            if result.get("updated")
            else None
        )
    except Exception as exc:
        return _operation_exception_response(exc, message="face_apply_metadata_match_failed")

    return {
        "success": True,
        "data": {
            "image_path": image_path,
            "person_name": person_name,
            "result": result,
            "findings_update": findings_update,
        },
    }


@router.post("/face_assign_metadata_match")
async def face_assign_metadata_match(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    metadata_face = body.get("metadata_face")
    person_id = body.get("person_id")
    person_name = str(body.get("person_name") or "").strip()
    save_mapping = bool(body.get("save_mapping"))
    update_metadata_name = bool(body.get("update_metadata_name"))
    source_name = body.get("source_name")
    if not image_path or not isinstance(metadata_face, dict) or not person_name:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_assign_metadata_match_request",
            },
        }
    try:
        person_id = int(person_id)
    except Exception:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_person_id",
            },
        }

    try:
        transfer_result = IMGDATA.assignMetadataFaceToKnownPhotosPerson(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            image_path=image_path,
            metadata_face=metadata_face,
            person_id=person_id,
            person_name=person_name,
        )
        metadata_update = (
            IMGDATA.replaceMetadataFaceName(
                image_path=image_path,
                face_data=metadata_face,
                new_name=person_name,
            )
            if update_metadata_name and transfer_result.get("face_id") is not None
            else None
        )
        findings_update = IMGDATA.removeFaceMatchFindingMetadataEntry(
            image_path=image_path,
            metadata_face=metadata_face,
            increment_transferred_count=True,
        )
        progress_update = IMGDATA.recordFaceMatchTransferProgress(
            session_ctx["user_key"],
            skip_targets=[
                IMGDATA._faceMatchTargetToken(
                    image_path=image_path,
                    face=metadata_face,
                ),
            ],
        )
        mapping_saved = _save_name_mapping_if_requested(
            save_mapping=save_mapping,
            source_name=source_name,
            target_name=person_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_assign_metadata_match_bootstrap_required")
    except Exception as exc:
        return _operation_exception_response(exc, message="face_assign_metadata_match_failed")

    return {
        "success": True,
        "data": {
            "image_path": image_path,
            "person_id": person_id,
            "person_name": person_name,
            "face_id": int(transfer_result["face_id"]),
            "add_result": transfer_result.get("add_result"),
            "assign_result": transfer_result.get("assign_result"),
            "metadata_update": metadata_update,
            "findings_update": findings_update,
            "progress_update": progress_update,
            "mapping_saved": mapping_saved if save_mapping else False,
        },
    }


@router.post("/face_create_metadata_match")
async def face_create_metadata_match(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    metadata_face = body.get("metadata_face")
    person_name = str(body.get("person_name") or "").strip()
    save_mapping = bool(body.get("save_mapping"))
    update_metadata_name = bool(body.get("update_metadata_name"))
    source_name = body.get("source_name")
    if not image_path or not isinstance(metadata_face, dict) or not person_name:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_create_metadata_match_request",
            },
        }

    try:
        transfer_result = IMGDATA.resolveOrCreatePhotosPersonForMetadataFace(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            image_path=image_path,
            metadata_face=metadata_face,
            person_name=person_name,
            create_missing_person=True,
        )
        metadata_update = (
            IMGDATA.replaceMetadataFaceName(
                image_path=image_path,
                face_data=metadata_face,
                new_name=person_name,
            )
            if update_metadata_name and transfer_result.get("face_id") is not None
            else None
        )
        findings_update = IMGDATA.removeFaceMatchFindingMetadataEntry(
            image_path=image_path,
            metadata_face=metadata_face,
            increment_transferred_count=True,
        )
        progress_update = IMGDATA.recordFaceMatchTransferProgress(
            session_ctx["user_key"],
            skip_targets=[
                IMGDATA._faceMatchTargetToken(
                    image_path=image_path,
                    face=metadata_face,
                ),
            ],
        )
        mapping_saved = _save_name_mapping_if_requested(
            save_mapping=save_mapping,
            source_name=source_name,
            target_name=person_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_create_metadata_match_bootstrap_required")
    except Exception as exc:
        return _operation_exception_response(exc, message="face_create_metadata_match_failed")

    return {
        "success": True,
        "data": {
            "image_path": image_path,
            "person_name": person_name,
            "face_id": int(transfer_result["face_id"]),
            "person_id": (transfer_result.get("target_person") or {}).get("id") if isinstance(transfer_result, dict) else None,
            "add_result": transfer_result.get("add_result"),
            "create_result": transfer_result.get("create_result"),
            "transfer_result": transfer_result,
            "metadata_update": metadata_update,
            "findings_update": findings_update,
            "progress_update": progress_update,
            "mapping_saved": mapping_saved if save_mapping else False,
        },
    }


@router.post("/face_delete_metadata_match")
async def face_delete_metadata_match(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    metadata_face = body.get("metadata_face")
    if not image_path or not isinstance(metadata_face, dict):
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_face_delete_metadata_match_request",
            },
        }

    try:
        result = IMGDATA.deleteMetadataFace(image_path=image_path, face_data=metadata_face)
        findings_update = (
            IMGDATA.removeFaceMatchFindingMetadataEntry(
                image_path=image_path,
                metadata_face=metadata_face,
                increment_transferred_count=False,
            )
            if result.get("deleted")
            else None
        )
    except Exception as exc:
        return _operation_exception_response(exc, message="face_delete_metadata_match_failed")

    return {
        "success": True,
        "data": {
            "image_path": image_path,
            "result": result,
            "findings_update": findings_update,
        },
    }


@router.post("/face_person_suggest")
async def face_person_suggest(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    name_prefix = body.get("name_prefix")
    limit = body.get("limit", 10)
    if not isinstance(name_prefix, str) or not name_prefix.strip():
        return {
            "success": True,
            "data": {
                "list": [],
            },
        }
    try:
        limit = int(limit)
    except Exception:
        limit = 10

    try:
        result = IMGDATA.suggestPersonsByName(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            name_prefix=name_prefix.strip(),
            limit=limit,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_person_suggest_bootstrap_required")

    return {
        "success": True,
        "data": {
            "list": result,
        },
    }


@router.post("/file_analysis_start")
async def file_analysis_start(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        result = await _run_backend_call(
            lambda: IMGDATA.startFileAnalysisDiscovery(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
            )
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="file_analysis_start_bootstrap_required")

    return {
        "success": True,
        "data": _compact_file_analysis_progress(result),
    }


@router.post("/file_analysis_progress")
async def file_analysis_progress(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    progress = await _run_backend_call(lambda: IMGDATA.getFileAnalysisProgress())
    data = _compact_file_analysis_progress(progress)
    status = progress.get("status") if isinstance(progress, dict) and isinstance(progress.get("status"), dict) else {}
    backend_debug_log(
        "file_analysis_progress_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        running=bool(progress.get("running")) if isinstance(progress, dict) else None,
        active=bool(progress.get("active")) if isinstance(progress, dict) else None,
        phase=status.get("phase"),
        files_analyzed=int(progress.get("files_analyzed") or 0) if isinstance(progress, dict) else None,
        files_matched_total=int(progress.get("files_matched_total") or 0) if isinstance(progress, dict) else None,
    )
    return {
        "success": True,
        "data": data,
    }


@router.post("/file_analysis_stop")
async def file_analysis_stop(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": IMGDATA.requestStopFileAnalysis(),
    }


def _attach_checks_status_for_response(payload, *, check_type: str = "", source_mode: str = ""):
    return IMGDATA.attachChecksStatusForResponse(
        payload,
        check_type=check_type,
        source_mode=source_mode,
    )


@router.post("/checks_start")
async def checks_start(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    source_mode = body.get("source_mode", "findings")
    check_type = body.get("check_type", "dimension_issues")
    save_only = bool(body.get("save_only"))
    resume_from_progress = bool(body.get("resume_from_progress"))
    auto_apply_suggested_names = bool(body.get("auto_apply_suggested_names"))
    auto_apply_suggested_duplicates = bool(body.get("auto_apply_suggested_duplicates"))
    advance_current_result = bool(body.get("advance_current_result"))
    try:
        changed_since_days = max(0, int(body.get("changed_since_days") or 0)) if str(source_mode or "").strip().lower() == "scan" else 0
    except (TypeError, ValueError):
        changed_since_days = 0

    try:
        result = await _run_backend_call(
            lambda: IMGDATA.checks_workflow.start_review(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                source_mode=source_mode,
                check_type=check_type,
                save_only=save_only,
                resume_from_progress=resume_from_progress,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                advance_current_result=advance_current_result,
                changed_since_days=changed_since_days,
            ),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        error_payload = _session_exception_response(exc, bootstrap_message="checks_start_bootstrap_required")
        return JSONResponse(error_payload)
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_start_failed"))

    result = _attach_checks_status_for_response(
        result if isinstance(result, dict) else {},
        check_type=str(check_type or "dimension_issues"),
        source_mode=str(source_mode or ""),
    )
    response_payload = {
        "success": True,
        "data": result,
    }
    return JSONResponse(response_payload)


@router.post("/checks_item")
async def checks_item(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    entry = body.get("entry")
    auto_apply_suggested_names = bool(body.get("auto_apply_suggested_names"))
    auto_apply_suggested_duplicates = bool(body.get("auto_apply_suggested_duplicates"))
    if not isinstance(entry, dict):
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_check_entry",
            },
        }

    try:
        resolved = await _run_backend_call(
            lambda: IMGDATA._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                max_auto_apply_actions=1,
            ),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        error_payload = _session_exception_response(exc, bootstrap_message="checks_item_bootstrap_required")
        return JSONResponse(error_payload)
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_item_failed"))

    resolved = resolved if isinstance(resolved, dict) else {}
    review_type = str(entry.get("review_type") or "").strip().lower()
    data_payload = {
        "entry": resolved.get("entry"),
        "item": resolved.get("item"),
        "auto_applied_count": int(resolved.get("auto_applied_count") or 0),
        "findings_update": None,
        "check_type": review_type,
        "source_mode": "findings",
        "running": False,
        "finished": False,
        "save_only": False,
        "resolved_count": int(resolved.get("auto_applied_count") or 0),
        "skipped_count": int(resolved.get("skipped_count") or 0),
        "ignored_count": int(resolved.get("ignored_count") or 0),
    }
    data_payload = _attach_checks_status_for_response(
        data_payload,
        check_type=review_type,
        source_mode="findings",
    )
    response_payload = {
        "success": True,
        "data": data_payload,
    }
    if resolved.get("stop_requested") or IMGDATA._shouldStopChecks(
        session_ctx["user_key"],
        str(entry.get("review_type") or ""),
    ):
        response_payload["data"]["stop_requested"] = True
        return JSONResponse(response_payload)

    refresh_required = (
        review_type
        and review_type != "name_conflicts"
        and (
            int(resolved.get("auto_applied_count") or 0) > 0
            or resolved.get("item") is None
        )
    )
    if refresh_required:
        image_path = str(entry.get("image_path") or "")
        findings_update = IMGDATA.refreshChecksFindingEntriesForImage(
            check_type=str(entry.get("review_type") or ""),
            image_path=image_path,
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
        )
        response_payload["data"]["findings_update"] = _compact_checks_findings_update(
            findings_update,
            image_path=image_path,
        )
    return JSONResponse(response_payload)


@router.post("/checks_progress")
async def checks_progress(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    body = await _read_request_body(request)
    check_type = body.get("check_type", "dimension_issues")
    progress = await _run_backend_call(
        lambda: IMGDATA.getChecksProgress(session_ctx["user_key"], str(check_type or "dimension_issues"))
    )

    return {
        "success": True,
        "data": _enrich_checks_progress_counters(progress),
    }


@router.post("/checks_findings_status")
async def checks_findings_status(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    result = await _run_backend_call(lambda: IMGDATA.getChecksFindingsStatus())
    statuses = result.get("statuses") if isinstance(result, dict) and isinstance(result.get("statuses"), dict) else {}
    return {
        "success": True,
        "data": {
            "statuses": statuses,
        },
    }


@router.post("/checks_stop")
async def checks_stop(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response
    body = await _read_request_body(request)
    check_type = body.get("check_type", "dimension_issues")

    result = await _run_backend_call(
        lambda: IMGDATA.requestStopChecks(session_ctx["user_key"], str(check_type or "dimension_issues"))
    )
    result = _attach_checks_status_for_response(
        result if isinstance(result, dict) else {},
        check_type=str(check_type or "dimension_issues"),
        source_mode=str((result or {}).get("source_mode") or "scan") if isinstance(result, dict) else "scan",
    )
    return {
        "success": True,
        "data": result,
    }


@router.post("/cleanup_start")
async def cleanup_start(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    action = body.get("action", "normalize_names")
    targets = body.get("targets", [])
    options = body.get("options", {})

    try:
        result = await _run_backend_call(
            lambda: IMGDATA.startCleanupRun(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                action=str(action or "normalize_names"),
                targets=targets if isinstance(targets, list) else [],
                options=options if isinstance(options, dict) else {},
            ),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        error_payload = _session_exception_response(exc, bootstrap_message="cleanup_start_bootstrap_required")
        return JSONResponse(error_payload)
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="cleanup_start_failed"))

    return JSONResponse({"success": True, "data": result})


@router.post("/cleanup_face_frames_findings")
async def cleanup_face_frames_findings(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    return JSONResponse({
        "success": True,
        "data": IMGDATA.face_frame_standardization.findings(
            user_key=session_ctx["user_key"],
            operation_mode=str(body.get("operation_mode") or ""),
        ),
    })


@router.post("/cleanup_face_frames_select")
async def cleanup_face_frames_select(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    item_id = str(body.get("item_id") or "").strip()
    if not item_id:
        return JSONResponse({"success": False, "error": {"code": 400, "message": "missing_item_id"}})
    try:
        result = IMGDATA.face_frame_standardization.update_selection(
            item_id=item_id,
            selected=bool(body.get("selected")),
            user_key=session_ctx["user_key"],
            operation_mode=str(body.get("operation_mode") or "findings"),
        )
        IMGDATA.face_frame_standardization.sync_review_progress(
            user_key=session_ctx["user_key"],
            operation_mode=str(body.get("operation_mode") or "findings"),
        )
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="cleanup_face_frames_select_failed"))
    return JSONResponse({"success": True, "data": result})


@router.post("/cleanup_face_frames_apply")
async def cleanup_face_frames_apply(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    selected_item_ids = body.get("selected_item_ids")
    try:
        result = await _run_backend_call(
            lambda: IMGDATA.face_frame_standardization.apply_selected(
                selected_item_ids=selected_item_ids if isinstance(selected_item_ids, list) else None,
                user_key=session_ctx["user_key"],
                operation_mode=str(body.get("operation_mode") or "findings"),
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
            )
        )
        await _run_backend_call(
            lambda: IMGDATA.face_frame_standardization.sync_review_progress(
                user_key=session_ctx["user_key"],
                operation_mode=str(body.get("operation_mode") or "findings"),
            )
        )
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="cleanup_face_frames_apply_failed"))
    return JSONResponse({"success": True, "data": result})


@router.post("/recognition_findings")
async def recognition_findings(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    action = str(body.get("action") or "").strip()
    return JSONResponse({"success": True, "data": IMGDATA.face_recognition.findings(
        action,
        user_key=session_ctx["user_key"],
        operation_mode=str(body.get("operation_mode") or ""),
    )})


@router.post("/recognition_review")
async def recognition_review(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    action = str(body.get("action") or "").strip()
    item_id = str(body.get("item_id") or "").strip()
    decision = str(body.get("decision") or "").strip()
    if not item_id or not decision:
        return JSONResponse({"success": False, "error": {"code": 400, "message": "invalid_recognition_review_request"}})
    operation_mode = str(body.get("operation_mode") or "findings")
    result = await _run_backend_call(lambda: IMGDATA.face_recognition.update_review(
        action=action,
        item_id=item_id,
        decision=decision,
        user_key=session_ctx["user_key"],
        operation_mode=operation_mode,
    ))
    await _run_backend_call(lambda: IMGDATA.face_recognition.sync_review_progress(
        user_key=session_ctx["user_key"],
        action=action,
        operation_mode=operation_mode,
    ))
    return JSONResponse({"success": True, "data": result})


@router.post("/recognition_suggestions_apply")
async def recognition_suggestions_apply(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)
    body = await _read_request_body(request)
    selected_ids = body.get("selected_suggestion_ids")
    action = str(body.get("action") or "recognition_analyze_unknown_faces")
    try:
        result = await _run_backend_call(lambda: IMGDATA.face_recognition.apply_suggestions(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            selected_ids=selected_ids if isinstance(selected_ids, list) else None,
            operation_mode=str(body.get("operation_mode") or "findings"),
            action=action,
        ))
        await _run_backend_call(lambda: IMGDATA.face_recognition.sync_review_progress(
            user_key=session_ctx["user_key"],
            action=action,
            operation_mode=str(body.get("operation_mode") or "findings"),
        ))
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="recognition_suggestions_apply_failed"))
    return JSONResponse({"success": True, "data": result})


@router.post("/cleanup_progress")
async def cleanup_progress(request: Request):
    started = time.monotonic()
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    action = body.get("action", "normalize_names")
    progress = IMGDATA.getCleanupProgress(session_ctx["user_key"], str(action or "normalize_names"))
    backend_debug_log(
        "cleanup_progress_end",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
        user_key_hash=_debug_user_key(session_ctx["user_key"]),
        progress=_progress_debug_summary(progress) if isinstance(progress, dict) else {},
        persons_scanned=int(progress.get("persons_scanned") or 0) if isinstance(progress, dict) else None,
        persons_total=int(progress.get("persons_total") or 0) if isinstance(progress, dict) else None,
        images_scanned=int(progress.get("images_scanned") or 0) if isinstance(progress, dict) else None,
        images_total=int(progress.get("images_total") or 0) if isinstance(progress, dict) else None,
        profiles_built=int(progress.get("profiles_built") or 0) if isinstance(progress, dict) else None,
    )
    return JSONResponse({
        "success": True,
        "data": progress,
    })


@router.post("/cleanup_stop")
async def cleanup_stop(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    action = body.get("action", "normalize_names")
    return JSONResponse({
        "success": True,
        "data": IMGDATA.requestStopCleanup(session_ctx["user_key"], str(action or "normalize_names")),
    })


@router.post("/checks_delete_metadata_face")
async def checks_delete_metadata_face(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    face = body.get("face")
    if not image_path or not isinstance(face, dict):
        return JSONResponse({
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_delete_face_request",
            },
        })

    try:
        result = IMGDATA.deleteMetadataFace(
            image_path=image_path,
            face_data=face,
        )
        findings_update = None
        review_type = str(body.get("review_type") or "").strip().lower()
        refresh_error = None
        if result.get("deleted") and review_type:
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type=review_type,
                image_path=image_path,
            )
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_delete_metadata_face_failed"))

    return JSONResponse({
        "success": True,
        "data": {
            **result,
            "findings_update": findings_update,
            "refresh_error": refresh_error,
        },
    })


@router.post("/checks_replace_metadata_face_name")
async def checks_replace_metadata_face_name(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    face = body.get("face")
    new_name = str(body.get("new_name") or "").strip()
    review_type = str(body.get("review_type") or "").strip().lower() or "name_conflicts"
    save_mapping = bool(body.get("save_mapping"))
    source_name = str(body.get("source_name") or "").strip()
    create_missing_person = bool(body.get("create_missing_person"))
    if not image_path or not isinstance(face, dict) or not new_name:
        return JSONResponse({
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_replace_face_request",
            },
        })

    try:
        result = IMGDATA.replaceChecksFaceName(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            image_path=image_path,
            face_data=face,
            new_name=new_name,
            create_missing_person=create_missing_person,
        )
        findings_update = None
        if result.get("updated") and save_mapping and source_name:
            mapping_saved = _save_name_mapping_if_requested(
                save_mapping=True,
                source_name=source_name,
                target_name=new_name,
            )
        else:
            mapping_saved = False
        refresh_error = None
        if result.get("updated"):
            replacement_face_data = dict(face)
            replacement_face_data["name"] = str(result.get("resolved_name") or new_name)
            if str(result.get("operation") or "").strip().lower() in {"photos_assign", "photos_create"}:
                target_person = result.get("target_person") if isinstance(result.get("target_person"), dict) else {}
                if target_person.get("id") not in (None, ""):
                    replacement_face_data["person_id"] = target_person.get("id")
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type=review_type,
                image_path=image_path,
                original_face_data=face,
                replacement_face_data=replacement_face_data,
                resolved_delta=1,
            )
        elif str(result.get("warning") or "").strip() == "checks:warning_face_replace_not_found":
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type=review_type,
                image_path=image_path,
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return JSONResponse(_session_exception_response(exc, bootstrap_message="checks_replace_metadata_face_name_bootstrap_required"))
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_replace_metadata_face_name_failed"))

    return JSONResponse({
        "success": True,
        "data": {
            **result,
            "mapping_saved": mapping_saved if save_mapping else False,
            "findings_update": findings_update,
            "refresh_error": refresh_error,
        },
    })


@router.post("/checks_replace_metadata_face_position")
async def checks_replace_metadata_face_position(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    face = body.get("face")
    source_face = body.get("source_face")
    review_type = str(body.get("review_type") or "").strip().lower()
    if not image_path or not isinstance(face, dict) or not isinstance(source_face, dict):
        return JSONResponse({
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_replace_face_position_request",
            },
        })

    try:
        result = IMGDATA.replaceMetadataFacePosition(
            image_path=image_path,
            face_data=face,
            source_face_data=source_face,
        )
        findings_update = None
        refresh_error = None
        if result.get("updated") and review_type:
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type=review_type,
                image_path=image_path,
            )
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_replace_metadata_face_position_failed"))

    return JSONResponse({
        "success": True,
        "data": {
            **result,
            "findings_update": findings_update,
            "refresh_error": refresh_error,
        },
    })


@router.post("/checks_assign_face_person")
async def checks_assign_face_person(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    image_path = str(body.get("image_path") or "").strip()
    face = body.get("face")
    review_type = str(body.get("review_type") or "").strip().lower()
    person_name = str(body.get("person_name") or "").strip()
    person_id = body.get("person_id")
    if not image_path or not isinstance(face, dict) or not person_name:
        return JSONResponse({
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_assign_face_person_request",
            },
        })
    try:
        person_id = int(person_id)
    except Exception:
        return JSONResponse({
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_person_id",
            },
        })

    try:
        result = IMGDATA.assignChecksFaceToKnownPerson(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            image_path=image_path,
            face_data=face,
            person_id=person_id,
            person_name=person_name,
        )
        findings_update = None
        refresh_error = None
        if result.get("updated") and review_type:
            replacement_face_data = dict(face)
            replacement_face_data["name"] = person_name
            replacement_face_data["person_id"] = person_id
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type=review_type,
                image_path=image_path,
                original_face_data=face,
                replacement_face_data=replacement_face_data,
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="checks_assign_face_person_bootstrap_required")
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_assign_face_person_failed"))

    return JSONResponse({
        "success": True,
        "data": {
            **result,
            "findings_update": findings_update,
            "refresh_error": refresh_error,
        },
    })

@router.get("/file_image")
async def file_image(request: Request, path: str = ""):
    if not path:
        return {"success": False, "error": {"code": 400, "message": "missing_path"}}

    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        shared_folder = (await _run_backend_call(
            lambda: IMGDATA.status_system(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
            )
        )).get("shared_folder", "")
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="file_image_bootstrap_required")

    if not shared_folder:
        return {"success": False, "error": {"code": 404, "message": "shared_folder_not_found"}}

    requested = os.path.abspath(path)
    shared_root = os.path.abspath(shared_folder)
    if not requested.startswith(shared_root + os.sep) and requested != shared_root:
        return {"success": False, "error": {"code": 403, "message": "path_outside_shared_folder"}}
    if not os.path.isfile(requested):
        return {"success": False, "error": {"code": 404, "message": "file_not_found"}}

    preview = IMGDATA.files.extractEmbeddedJpegPreview(requested)
    if preview:
        return Response(
            content=preview,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    decoder = getattr(IMGDATA, "image_decoder", None)
    if decoder is not None:
        decoded = await _run_backend_call(lambda: decoder.decode_to_jpeg(requested))
        if getattr(decoded, "success", False) and getattr(decoded, "image_bytes", b""):
            return Response(
                content=decoded.image_bytes,
                media_type="image/jpeg",
                headers={"Cache-Control": "private, max-age=3600"},
            )
        error = str(getattr(decoded, "error", "") or "")
        if error and error not in {"image_decoder_extension_not_enabled", "image_decoder_disabled"}:
            backend_debug_log(
                "file_image_decoder_failed",
                path=requested,
                source=str(getattr(decoded, "source", "") or "image_decoder"),
                error=error,
            )

    if not _is_browser_image_compatible_path(requested):
        return _image_preview_unavailable_response()

    return FileResponse(requested)


@router.post("/config_get")
async def config_get(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    config = IMGDATA.getRuntimeConfig()
    return {
        "success": True,
        "data": {
            "config": config,
            "config_path": str(IMGDATA.config._config_path),
            "backend_debug_log_path": backend_debug_log_path(),
            "checks_ignore_lists": IMGDATA.getChecksIgnoreListsStatus(),
        },
    }


@router.post("/database_name_mappings")
async def database_name_mappings(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    search = str(body.get("search") or "").strip()
    try:
        page = max(1, int(body.get("page") or 1))
        page_size = max(1, min(100, int(body.get("page_size") or 25)))
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": {"code": 400, "message": "invalid_database_list_pagination"},
        }
    try:
        result = await _run_backend_call(
            lambda: IMGDATA.listNameMappingsPage(search=search, page=page, page_size=page_size)
        )
    except Exception as exc:
        return _operation_exception_response(exc, message="database_name_mappings_load_failed")
    return {"success": True, "data": {"list": "name_mappings", **result}}


@router.post("/database_name_mapping_delete")
async def database_name_mapping_delete(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    try:
        mapping_id = int(body.get("id"))
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": {"code": 400, "message": "invalid_name_mapping_id"},
        }
    if mapping_id < 1:
        return {
            "success": False,
            "error": {"code": 400, "message": "invalid_name_mapping_id"},
        }
    try:
        deleted = await _run_backend_call(lambda: IMGDATA.deleteNameMapping(mapping_id))
    except Exception as exc:
        return _operation_exception_response(exc, message="database_name_mapping_delete_failed")
    if not deleted:
        return {
            "success": False,
            "error": {"code": 404, "message": "name_mapping_not_found"},
        }
    return {"success": True, "data": {"id": mapping_id, "deleted": True}}


@router.post("/database_name_mappings_clear")
async def database_name_mappings_clear(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        deleted = await _run_backend_call(lambda: IMGDATA.clearNameMappings())
    except Exception as exc:
        return _operation_exception_response(exc, message="database_name_mappings_clear_failed")
    return {"success": True, "data": {"list": "name_mappings", "cleared": True, "deleted": int(deleted or 0)}}


@router.post("/database_name_mapping_save")
async def database_name_mapping_save(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    source_name = str(body.get("source_name") or "").strip()
    target_name = str(body.get("target_name") or "").strip()
    if not source_name or not target_name:
        return {
            "success": False,
            "error": {"code": 400, "message": "missing_name_mapping_values"},
        }
    try:
        mapping_id = int(body.get("id") or 0)
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": {"code": 400, "message": "invalid_name_mapping_id"},
        }
    try:
        if mapping_id > 0:
            saved = await _run_backend_call(
                lambda: IMGDATA.updateNameMappingTarget(mapping_id, target_name)
            )
        else:
            saved = await _run_backend_call(
                lambda: IMGDATA.saveNameMapping(source_name=source_name, target_name=target_name)
            )
    except Exception as exc:
        return _operation_exception_response(exc, message="database_name_mapping_save_failed")
    if not saved:
        return {
            "success": False,
            "error": {"code": 500, "message": "database_name_mapping_save_failed"},
        }
    return {
        "success": True,
        "data": {"id": mapping_id or None, "source_name": source_name, "target_name": target_name, "saved": True},
    }


@router.post("/database_checks_ignore_lists")
async def database_checks_ignore_lists(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        statuses = await _run_backend_call(lambda: IMGDATA.getChecksIgnoreListsStatus())
    except Exception as exc:
        return _operation_exception_response(exc, message="database_checks_ignore_lists_load_failed")
    return {"success": True, "data": {"checks_ignore_lists": statuses}}


@router.post("/config_save")
async def config_save(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    config = body.get("config")
    if not isinstance(config, dict):
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_config_payload",
            },
        }

    if not IMGDATA.saveRuntimeConfig(config):
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "config_write_failed",
            },
        }

    return {
        "success": True,
        "data": {
            "config": IMGDATA.getRuntimeConfig(),
            "config_path": str(IMGDATA.config._config_path),
            "backend_debug_log_path": backend_debug_log_path(),
            "checks_ignore_lists": IMGDATA.getChecksIgnoreListsStatus(),
            "saved": True,
        },
    }


@router.post("/checks_ignore_entry")
async def checks_ignore_entry(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    entry = body.get("entry") if isinstance(body.get("entry"), dict) else {}
    image_path = str(entry.get("image_path") or body.get("image_path") or "").strip()
    check_type = str(entry.get("review_type") or body.get("check_type") or "").strip().lower()
    if not image_path or not check_type:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_ignore_payload",
            },
        }

    ignore_result = IMGDATA.ignoreChecksEntry(entry=entry)
    if not ignore_result.get("ignored"):
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": str(ignore_result.get("reason") or "checks_ignore_failed"),
            },
        }

    findings_update, refresh_error = _safe_refresh_checks_mutation_state(
        session_ctx,
        check_type=check_type,
        image_path=image_path,
        ignored_delta=1,
    )

    return {
        "success": True,
        "data": {
            "ignored": True,
            "token": ignore_result.get("token"),
            "findings_update": findings_update,
            "refresh_error": refresh_error,
            "config": IMGDATA.getRuntimeConfig(),
            "config_path": str(IMGDATA.config._config_path),
            "checks_ignore_lists": IMGDATA.getChecksIgnoreListsStatus(),
        },
    }


@router.post("/checks_ignore_list_clear")
async def checks_ignore_list_clear(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    review_type = str(body.get("review_type") or body.get("check_type") or "").strip().lower()
    if review_type not in {"duplicate_faces", "position_deviations", "name_conflicts"}:
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "invalid_checks_ignore_list_type",
            },
        }

    if not IMGDATA.clearChecksIgnoreList(review_type):
        return {
            "success": False,
            "error": {
                "code": 500,
                "message": "checks_ignore_list_clear_failed",
            },
        }

    return {
        "success": True,
        "data": {
            "cleared": True,
            "review_type": review_type,
            "checks_ignore_lists": IMGDATA.getChecksIgnoreListsStatus(),
        },
    }
