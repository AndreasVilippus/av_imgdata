#!/usr/bin/env python3
import asyncio
import os
import shutil
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlsplit
from fastapi import APIRouter, Request
from api.session_manager import SessionBootstrapRequired, SessionManager, SessionManagerError
from imgdata import ImgDataService

router = APIRouter(prefix="/api")

DSM_INTERNAL_BASE_URL = os.getenv("DSM_INTERNAL_BASE_URL", "https://127.0.0.1:5001")
DSM_INTERNAL_VERIFY_SSL = os.getenv("DSM_INTERNAL_VERIFY_SSL", "false").lower() in ("1", "true", "yes")
SESSION_MANAGER = SessionManager(verify_ssl=DSM_INTERNAL_VERIFY_SSL, timeout=20)
IMGDATA = ImgDataService(SESSION_MANAGER)


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
        return {}
    return body if isinstance(body, dict) else {}


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
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="status_bootstrap_required")

    return {
        "success": True,
        "data": {
            "persons": persons_status
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
    limit = body.get("limit", 100)
    offset = body.get("offset", 0)
    skip_face_ids = body.get("skip_face_ids") if isinstance(body.get("skip_face_ids"), list) else []
    try:
        limit = int(limit)
    except Exception:
        limit = 100
    try:
        offset = int(offset)
    except Exception:
        offset = 0
    normalized_skip_face_ids = []
    for face_id in skip_face_ids:
        try:
            normalized_skip_face_ids.append(int(face_id))
        except Exception:
            continue

    if action != "search_photo_face_in_file":
        return {
            "success": False,
            "error": {
                "code": 400,
                "message": "unsupported_face_matching_action",
                "details": action,
            },
        }

    try:
        loop = asyncio.get_running_loop()
        face_matches = await loop.run_in_executor(
            None,
            lambda: IMGDATA.searchPhotoFaceInFile(
                user_key=session_ctx["user_key"],
                cookies=session_ctx["cookies"],
                base_url=session_ctx["base_url"],
                limit=limit,
                offset=offset,
                skip_face_ids=normalized_skip_face_ids,
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
            "face_matches": face_matches
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
        mapping_saved = False
        if save_mapping and isinstance(source_name, str) and source_name.strip():
            mapping_saved = IMGDATA.saveNameMapping(
                source_name=source_name.strip(),
                target_name=person_name.strip(),
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_assign_match_bootstrap_required")

    return {
        "success": True,
        "data": {
            "face_id": face_id,
            "person_id": person_id,
            "result": result,
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
        created_person_id = result.get("id") if isinstance(result, dict) else None
        mapping_saved = False
        if save_mapping and isinstance(source_name, str) and source_name.strip():
            mapping_saved = IMGDATA.saveNameMapping(
                source_name=source_name.strip(),
                target_name=person_name.strip(),
            )
    except (SessionBootstrapRequired, SessionManagerError) as exc:
        return _session_exception_response(exc, bootstrap_message="face_create_match_bootstrap_required")

    return {
        "success": True,
        "data": {
            "face_id": face_id,
            "person_name": person_name.strip(),
            "result": result,
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
            "saved": True,
        },
    }


# KEEP IT FOR DEV
@router.post("/test_request")
async def test_request(request: Request):
    session_ctx, error_response = await _prepare_session_request(request)
    if error_response:
        return error_response

    file_config = IMGDATA.config.readConfig()
    runtime_config_path = str(IMGDATA.config._config_path)
    runtime_mapping_path = str(IMGDATA.name_mappings._mapping_path)
    mapping_debug = IMGDATA.name_mappings.getDebugInfo()
    exiftool_path = str(
        ((file_config.get("files") if isinstance(file_config.get("files"), dict) else {}) or {}).get("PATHEXIFTOOL")
        or "exiftool"
    )

    return {
        "success": True,
        "data": {
            "action": "test_request",
            "debug": {
                "config": file_config,
                "runtime_config_path": runtime_config_path,
                "runtime_mapping_path": runtime_mapping_path,
                "runtime_config_exists": os.path.isfile(runtime_config_path),
                "runtime_mapping_exists": os.path.isfile(runtime_mapping_path),
                "runtime_mapping_readable": bool(mapping_debug.get("readable")),
                "runtime_mapping_count": int(mapping_debug.get("count") or 0),
                "runtime_mapping_read_error": str(mapping_debug.get("last_read_error") or ""),
                "package_dest": os.getenv("SYNOPKG_PKGDEST"),
                "configured_exiftool_path": exiftool_path,
                "configured_exiftool_exists": os.path.isfile(exiftool_path),
                "exiftool_in_path": shutil.which("exiftool"),
            },
        },
    }
