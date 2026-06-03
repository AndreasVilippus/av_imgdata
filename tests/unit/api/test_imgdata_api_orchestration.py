import asyncio
from unittest.mock import Mock

from api import imgdata_api
from api.session_manager import SessionManagerError


SESSION_CTX = {
    "user_key": "user-1",
    "cookies": {"_SSID": "sid-1"},
    "base_url": "https://dsm.example.test",
}


async def _prepared_session(_request):
    return dict(SESSION_CTX), None


def _run(coro):
    return asyncio.run(coro)


def test_session_exception_debug_detail_preserves_structured_synology_api_failure():
    detail = {
        "error": "api_failed",
        "api": "SYNO.FotoTeam.Browse.Person",
        "response": {"success": False, "error": {"code": 117}},
    }

    assert imgdata_api._session_exception_debug_detail(
        SessionManagerError(detail, status_code=502)
    ) == detail


def test_face_matching_action_normalizes_request_and_starts_discovery(monkeypatch):
    async def request_body(_request):
        return {
            "action": "search_photo_face_in_file",
            "auto": True,
            "save_only": True,
            "resume_from_progress": True,
            "limit": "12",
            "offset": "3",
            "skip_face_ids": ["10", "bad", 11],
            "skip_targets": [" target-a ", "", None, "target-b"],
        }

    runtime_config = Mock(return_value={"photos": {"MAX_PHOTOS_PERSONS": 50}})
    start_discovery = Mock(return_value={"running": True})

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "getRuntimeConfig", runtime_config)
    monkeypatch.setattr(imgdata_api.IMGDATA, "startFaceMatchingDiscovery", start_discovery)

    payload = _run(imgdata_api.face_matching_action(object()))

    assert payload["success"] is True
    assert payload["data"]["action"] == "search_photo_face_in_file"
    assert payload["data"]["auto"] is True
    assert payload["data"]["save_only"] is True
    assert payload["data"]["resume_from_progress"] is True
    assert payload["data"]["face_matches"] == {"running": True}
    start_discovery.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        action="search_photo_face_in_file",
        limit=12,
        offset=3,
        skip_face_ids=[10, 11],
        skip_targets=["target-a", "target-b"],
        auto=True,
        save_only=True,
        resume_from_progress=True,
    )


def test_face_matching_action_rejects_unsupported_action_before_service_call(monkeypatch):
    async def request_body(_request):
        return {"action": "unsupported"}

    start_discovery = Mock()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "getRuntimeConfig", Mock(return_value={"photos": {"MAX_PHOTOS_PERSONS": 50}}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "startFaceMatchingDiscovery", start_discovery)

    payload = _run(imgdata_api.face_matching_action(object()))

    assert payload == {
        "success": False,
        "error": {
            "code": 400,
            "message": "unsupported_face_matching_action",
            "details": "unsupported",
        },
    }
    start_discovery.assert_not_called()


def test_config_get_exposes_backend_debug_log_path(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    monkeypatch.delenv("SYNOPKG_PKGVAR", raising=False)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api.IMGDATA, "getRuntimeConfig", Mock(return_value={"debug": {"BACKEND_DEBUG_ENABLED": False}}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "getChecksIgnoreListsStatus", Mock(return_value={}))
    monkeypatch.setattr(imgdata_api.IMGDATA.config, "_config_path", config_path)

    payload = _run(imgdata_api.config_get(object()))

    assert payload["success"] is True
    assert payload["data"]["backend_debug_log_path"] == str(tmp_path / "backend-debug.log")


def test_face_matching_progress_writes_debug_summary_when_enabled(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "debug.log"
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api.IMGDATA.config, "_config_path", config_path)
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getRuntimeConfig",
        Mock(return_value={
            "debug": {
                "BACKEND_DEBUG_ENABLED": True,
                "BACKEND_DEBUG_LOG_PATH": str(log_path),
                "BACKEND_DEBUG_LOG_MAX_BYTES": 1048576,
                "BACKEND_DEBUG_LOG_BACKUPS": 1,
            },
        }),
    )
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFaceMatchingProgress",
        Mock(return_value={
            "operation_id": "op-1",
            "action": "search_photo_face_in_file",
            "running": False,
            "active": False,
            "stale": True,
            "findings_count": 0,
            "transferred_count": 19,
            "status": {"operation": "face_matching", "phase": "idle"},
        }),
    )

    payload = _run(imgdata_api.face_matching_progress(object()))

    assert payload["success"] is True
    log_data = log_path.read_text()
    assert '"event": "face_matching_progress"' in log_data
    assert '"status_phase": "idle"' in log_data
    assert '"transferred_count": 19' in log_data


def test_face_assign_match_assigns_removes_finding_and_saves_mapping(monkeypatch):
    async def request_body(_request):
        return {
            "face_id": "77",
            "person_id": "91",
            "person_name": " Person Target ",
            "save_mapping": True,
            "source_name": "Person Legacy",
        }

    assign = Mock(return_value={"updated": True})
    remove = Mock(return_value={"count": 0, "transferred_count": 1})
    save_mapping = Mock(return_value=True)

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "assignMatchedFaceToKnownPerson", assign)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save_mapping)

    payload = _run(imgdata_api.face_assign_match(object()))

    assert payload["success"] is True
    assert payload["data"]["face_id"] == 77
    assert payload["data"]["person_id"] == 91
    assert payload["data"]["result"] == {"updated": True}
    assert payload["data"]["findings_update"] == {"count": 0, "transferred_count": 1}
    assert payload["data"]["mapping_saved"] is True
    assign.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        face_id=77,
        person_id=91,
        person_name="Person Target",
    )
    remove.assert_called_once_with(face_id=77, increment_transferred_count=True)
    save_mapping.assert_called_once_with(
        source_name="Person Legacy",
        target_name="Person Target",
    )


def test_face_assign_match_validates_ids_before_service_calls(monkeypatch):
    async def request_body(_request):
        return {"face_id": "bad", "person_id": "91", "person_name": "Person Target"}

    assign = Mock()
    remove = Mock()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "assignMatchedFaceToKnownPerson", assign)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)

    payload = _run(imgdata_api.face_assign_match(object()))

    assert payload == {
        "success": False,
        "error": {
            "code": 400,
            "message": "invalid_face_or_person_id",
        },
    }
    assign.assert_not_called()
    remove.assert_not_called()


def test_face_assign_match_reports_synology_api_failure_without_login_code(monkeypatch):
    detail = {
        "error": "api_failed",
        "api": "SYNO.FotoTeam.Browse.Person",
        "response": {"success": False, "error": {"code": 902}},
    }

    async def request_body(_request):
        return {"face_id": "146890", "person_id": "19785", "person_name": "Jelizaveta Vilippus geb. Kromskaja"}

    assign = Mock(side_effect=SessionManagerError(detail, status_code=502))
    remove = Mock()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "assignMatchedFaceToKnownPerson", assign)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)

    payload = _run(imgdata_api.face_assign_match(object()))

    assert payload == {
        "success": False,
        "error": {
            "code": 502,
            "message": "synology_api_error",
            "details": detail,
        },
    }
    remove.assert_not_called()


def test_safe_refresh_uses_snapshot_path_for_name_conflicts(monkeypatch):
    snapshot = Mock(return_value=({"snapshot_update": True}, None))
    refresh = Mock(return_value={"refreshed": True})

    monkeypatch.setattr(imgdata_api, "_snapshot_name_conflicts_mutation_state", snapshot)
    monkeypatch.setattr(imgdata_api, "_refresh_checks_mutation_state", refresh)

    result = imgdata_api._safe_refresh_checks_mutation_state(
        dict(SESSION_CTX),
        check_type="name_conflicts",
        image_path="photo/test.jpg",
        original_face_data={"name": "Old"},
        replacement_face_data={"name": "New"},
        resolved_delta=1,
    )

    assert result == ({"snapshot_update": True}, None)
    snapshot.assert_called_once_with(
        dict(SESSION_CTX),
        check_type="name_conflicts",
        image_path="photo/test.jpg",
        original_face_data={"name": "Old"},
        replacement_face_data={"name": "New"},
        resolved_delta=1,
        ignored_delta=0,
    )
    refresh.assert_not_called()


def test_safe_refresh_uses_full_refresh_for_non_name_conflicts(monkeypatch):
    snapshot = Mock(return_value=({"snapshot_update": True}, None))
    refresh = Mock(return_value={"refreshed": True})

    monkeypatch.setattr(imgdata_api, "_snapshot_name_conflicts_mutation_state", snapshot)
    monkeypatch.setattr(imgdata_api, "_refresh_checks_mutation_state", refresh)

    result = imgdata_api._safe_refresh_checks_mutation_state(
        dict(SESSION_CTX),
        check_type="duplicate_faces",
        image_path="photo/test.jpg",
        original_face_data={"face_id": 1},
        replacement_face_data={"face_id": 2},
        ignored_delta=1,
    )

    assert result == ({"refreshed": True}, None)
    refresh.assert_called_once_with(
        dict(SESSION_CTX),
        check_type="duplicate_faces",
        image_path="photo/test.jpg",
        original_face_data={"face_id": 1},
        replacement_face_data={"face_id": 2},
        ignored_delta=1,
    )
    snapshot.assert_not_called()
