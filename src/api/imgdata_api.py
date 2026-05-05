#!/usr/bin/env python3
import asyncio
import os
from contextvars import ContextVar
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


def _configured_max_photos_persons() -> int:
    config = IMGDATA.getRuntimeConfig()
    photos = config.get("photos", {}) if isinstance(config.get("photos"), dict) else {}
    return max(1, int(photos["MAX_PHOTOS_PERSONS"]))


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
    return {
        "success": False,
        "error": {"code": exc.status_code, "message": "session_manager_error", "details": exc.detail},
    }


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
    normalized_path = str(image_path or "").strip()
    request_context = _REQUEST_MUTATION_CONTEXT.get({}) or {}

    # Name-conflict processing must be snapshot-based. If the image is
    # refreshed immediately after applying a recommendation, overlapping faces can
    # generate the same conflict combination again and the caller can loop
    # indefinitely. Manual changes and other check types keep the existing
    # refresh behaviour.
    if normalized_type == "name_conflicts":
        return {
            "status": "snapshot_updated",
            "check_type": normalized_type,
            "source_mode": "snapshot",
            "image_path": normalized_path,
            "entries": [],
            "image_entries": [],
            "count": 0,
            "refresh_skipped": True,
            "reason": "name_conflicts_snapshot_mode",
            "resolved_delta": int(resolved_delta or 0),
            "ignored_delta": int(ignored_delta or 0),
            "snapshot_mode": True,
        }, None

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
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    try:
        persons_status = IMGDATA.status_persons(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
        )
        system_status = IMGDATA.status_system(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="status_bootstrap_required")

    return {
        "success": True,
        "data": {
            "persons": persons_status,
            "system": system_status,
        },
    }


@router.post("/exiftool_status")
async def exiftool_status(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": IMGDATA.exiftool_status(),
    }


@router.post("/pip_packages_status")
async def pip_packages_status(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": IMGDATA.pipPackagesStatus(),
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
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    body = await _read_request_body(request)
    action = body.get("action", "")
    auto = bool(body.get("auto"))
    save_only = bool(body.get("save_only"))
    resume_from_progress = bool(body.get("resume_from_progress"))
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
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "unsupported_face_matching_action",
                "details": action,
            },
        }

    try:
        if action in {"search_photo_face_in_file", "search_file_face_in_sources", "mark_missing_photos_faces", "search_missing_faces_insightface"}:
            face_matches = IMGDATA.startFaceMatchingDiscovery(
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
            )
        else:
            loop = asyncio.get_running_loop()
            face_matches = await loop.run_in_executor(
                None,
                lambda: IMGDATA.getFaceMatchFindingEntries(
                    user_key=session_ctx["user_key"],
                    cookies=session_ctx["cookies"],
                    base_url=session_ctx["base_url"],
                    auto=auto,
                ),
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_matching_action_bootstrap_required")

    return {
        "success": True,
        "data": {
            "action": action,
            "auto": auto,
            "save_only": save_only,
            "resume_from_progress": resume_from_progress,
            "face_matches": face_matches
        },
    }


@router.post("/face_matching_findings_status")
async def face_matching_findings_status(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    findings = IMGDATA.getFaceMatchFindings()
    entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
    return {
        "success": True,
        "data": {
            "status": str(findings.get("status") or ""),
            "count": len(entries),
            "transferred_count": int(findings.get("transferred_count") or 0),
            "save_only": bool(findings.get("save_only")),
            "auto": bool(findings.get("auto")),
        },
    }


@router.post("/face_matching_progress")
async def face_matching_progress(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": IMGDATA.getFaceMatchingProgress(session_ctx["user_key"]),
    }


@router.post("/face_matching_stop")
async def face_matching_stop(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": IMGDATA.requestStopFaceMatching(session_ctx["user_key"]),
    }


@router.post("/face_assign_match")
async def face_assign_match(request: Request):
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
        result = IMGDATA.assignMatchedFaceToKnownPerson(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            face_id=face_id,
            person_id=person_id,
            person_name=person_name.strip(),
        )
        findings_update = IMGDATA.removeFaceMatchFindingEntry(
            face_id=face_id,
            increment_transferred_count=True,
        )
        mapping_saved = _save_name_mapping_if_requested(
            save_mapping=save_mapping,
            source_name=source_name,
            target_name=person_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_assign_match_bootstrap_required")
    except Exception as exc:
        return _operation_exception_response(exc, message="face_assign_match_failed")

    return {
        "success": True,
        "data": {
            "face_id": face_id,
            "person_id": person_id,
            "result": result,
            "findings_update": findings_update,
            "mapping_saved": mapping_saved if save_mapping else False,
        },
    }


@router.post("/face_create_match")
async def face_create_match(request: Request):
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
        result = IMGDATA.createMatchedFaceAsPerson(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            face_id=face_id,
            person_name=person_name.strip(),
        )
        findings_update = IMGDATA.removeFaceMatchFindingEntry(
            face_id=face_id,
            increment_transferred_count=True,
        )
        mapping_saved = _save_name_mapping_if_requested(
            save_mapping=save_mapping,
            source_name=source_name,
            target_name=person_name,
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_create_match_bootstrap_required")
    except Exception as exc:
        return _operation_exception_response(exc, message="face_create_match_failed")

    return {
        "success": True,
        "data": {
            "face_id": face_id,
            "person_id": IMGDATA._extractPersonId(result),
            "person_name": person_name.strip(),
            "result": result,
            "findings_update": findings_update,
            "mapping_saved": mapping_saved if save_mapping else False,
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
        transfer_result = IMGDATA.createMetadataFaceAsPhotosPerson(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
            image_path=image_path,
            metadata_face=metadata_face,
            person_name=person_name,
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
            "person_id": transfer_result.get("person_id"),
            "add_result": transfer_result.get("add_result"),
            "create_result": transfer_result.get("create_result"),
            "findings_update": findings_update,
            "progress_update": progress_update,
            "mapping_saved": mapping_saved if save_mapping else False,
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
        result = IMGDATA.startFileAnalysisDiscovery(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="file_analysis_start_bootstrap_required")

    return {
        "success": True,
        "data": _compact_file_analysis_progress(result),
    }


@router.post("/file_analysis_progress")
async def file_analysis_progress(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    return {
        "success": True,
        "data": _compact_file_analysis_progress(IMGDATA.getFileAnalysisProgress()),
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
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: IMGDATA.startChecksReview(
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
            ),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        error_payload = _session_exception_response(exc, bootstrap_message="checks_start_bootstrap_required")
        return JSONResponse(error_payload)
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="checks_start_failed"))

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
        loop = asyncio.get_running_loop()
        resolved = await loop.run_in_executor(
            None,
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

    response_payload = {
        "success": True,
        "data": {
            "entry": resolved.get("entry"),
            "item": resolved.get("item"),
            "auto_applied_count": int(resolved.get("auto_applied_count") or 0),
            "findings_update": None,
        },
    }
    refresh_required = (
        str(entry.get("review_type") or "").strip()
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

    return {
        "success": True,
        "data": IMGDATA.getChecksProgress(session_ctx["user_key"], str(check_type or "dimension_issues")),
    }


@router.post("/checks_findings_status")
async def checks_findings_status(request: Request):
    _session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    check_types = ("dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts")
    statuses = {}
    for check_type in check_types:
        findings = IMGDATA.getChecksFindingEntries(check_type=check_type)
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        statuses[check_type] = {
            "status": str(findings.get("status") or ""),
            "count": len(entries),
            "save_only": bool(findings.get("save_only")),
        }
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

    return {
        "success": True,
        "data": IMGDATA.requestStopChecks(session_ctx["user_key"], str(check_type or "dimension_issues")),
    }


@router.post("/cleanup_start")
async def cleanup_start(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    action = body.get("action", "normalize_names")
    targets = body.get("targets", [])

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: IMGDATA.startCleanupRun(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                action=str(action or "normalize_names"),
                targets=targets if isinstance(targets, list) else [],
            ),
        )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        error_payload = _session_exception_response(exc, bootstrap_message="cleanup_start_bootstrap_required")
        return JSONResponse(error_payload)
    except Exception as exc:
        return JSONResponse(_operation_exception_response(exc, message="cleanup_start_failed"))

    return JSONResponse({"success": True, "data": result})


@router.post("/cleanup_progress")
async def cleanup_progress(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return JSONResponse(error_response)

    body = await _read_request_body(request)
    action = body.get("action", "normalize_names")
    return JSONResponse({
        "success": True,
        "data": IMGDATA.getCleanupProgress(session_ctx["user_key"], str(action or "normalize_names")),
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
            replacement_face_data = None
            if str(result.get("operation") or "").strip().lower() in {"photos_assign", "photos_create"}:
                replacement_face_data = dict(face)
                replacement_face_data["name"] = str(result.get("resolved_name") or new_name)
                target_person = result.get("target_person") if isinstance(result.get("target_person"), dict) else {}
                if target_person.get("id") not in (None, ""):
                    replacement_face_data["person_id"] = target_person.get("id")
            findings_update, refresh_error = _safe_refresh_checks_mutation_state(
                session_ctx,
                check_type="name_conflicts",
                image_path=image_path,
                original_face_data=face,
                replacement_face_data=replacement_face_data,
                resolved_delta=1,
            )
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
            replacement_face_data = None
            if str(face.get("source_format") or "").strip().upper() == "PHOTOS":
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
        shared_folder = IMGDATA.status_system(
            user_key=session_ctx["user_key"],
            cookies=session_ctx["cookies"],
            base_url=session_ctx["base_url"],
        ).get("shared_folder", "")
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
            "checks_ignore_lists": IMGDATA.getChecksIgnoreListsStatus(),
        },
    }


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
