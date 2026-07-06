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


def _install_backend_call_recorder(monkeypatch):
    calls = []

    async def recorded_backend_call(func):
        calls.append(func)
        return func()

    monkeypatch.setattr(imgdata_api, "_run_backend_call", recorded_backend_call)
    return calls


def test_session_exception_debug_detail_preserves_structured_synology_api_failure():
    detail = {
        "error": "api_failed",
        "api": "SYNO.FotoTeam.Browse.Person",
        "response": {"success": False, "error": {"code": 117}},
    }

    assert imgdata_api._session_exception_debug_detail(
        SessionManagerError(detail, status_code=502)
    ) == detail


def test_run_backend_call_uses_asyncio_executor(monkeypatch):
    calls = []

    class FakeLoop:
        async def run_in_executor(self, executor, func):
            calls.append(executor)
            return func()

    monkeypatch.setattr(imgdata_api.asyncio, "get_running_loop", lambda: FakeLoop())

    assert _run(imgdata_api._run_backend_call(lambda: "ok")) == "ok"
    assert calls == [None]


def test_face_matching_action_normalizes_request_and_starts_discovery(monkeypatch):
    async def request_body(_request):
        return {
            "action": "search_photo_face_in_file",
            "auto": True,
            "save_only": True,
            "recognize_persons": True,
            "skip_unknown_persons": True,
            "resume_from_progress": True,
            "limit": "12",
            "offset": "3",
            "skip_face_ids": ["10", "bad", 11],
            "skip_targets": [" target-a ", "", None, "target-b"],
        }

    runtime_config = Mock(return_value={"photos": {"MAX_PHOTOS_PERSONS": 50}})
    start_discovery = Mock(return_value={"running": True})

    calls = _install_backend_call_recorder(monkeypatch)
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
    assert len(calls) == 1
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
        recognize_persons=True,
        skip_unknown_persons=True,
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
    _install_backend_call_recorder(monkeypatch)
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


def test_status_routes_run_blocking_service_calls_off_event_loop(monkeypatch):
    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "backend_debug_log", Mock())
    monkeypatch.setattr(imgdata_api.IMGDATA, "status_persons", Mock(return_value={"known": 1, "total": 2}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "status_system", Mock(return_value={"shared_folder": "/volume1/photo"}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "exiftool_status", Mock(return_value={"installed": True, "available": True}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "insightFaceStatus", Mock(return_value={"insightface": {"enabled": True}}))

    status_payload = _run(imgdata_api.status(object()))
    exiftool_payload = _run(imgdata_api.exiftool_status(object()))
    insightface_payload = _run(imgdata_api.insightface_status(object()))

    assert status_payload["success"] is True
    assert exiftool_payload["success"] is True
    assert insightface_payload["success"] is True
    assert len(calls) == 4
    imgdata_api.IMGDATA.status_persons.assert_called_once_with(
        user_key=SESSION_CTX["user_key"],
        cookies=SESSION_CTX["cookies"],
        base_url=SESSION_CTX["base_url"],
        background=True,
    )
    imgdata_api.IMGDATA.status_system.assert_called_once_with(
        user_key=SESSION_CTX["user_key"],
        cookies=SESSION_CTX["cookies"],
        base_url=SESSION_CTX["base_url"],
        background=True,
    )
    imgdata_api.IMGDATA.exiftool_status.assert_called_once_with(background=True)
    imgdata_api.IMGDATA.insightFaceStatus.assert_called_once()


def test_progress_and_findings_routes_run_blocking_service_calls_off_event_loop(monkeypatch):
    async def request_body(_request):
        return {"check_type": "duplicate_faces", "action": "mark_missing_photos_faces"}

    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api, "backend_debug_log", Mock())
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFaceMatchFindingsStatus",
        Mock(return_value={"status": "ready", "action": "mark_missing_photos_faces", "entries": [{}], "transferred_count": 0}),
    )
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFaceMatchingProgress",
        Mock(return_value={"status": {"phase": "idle"}, "running": False, "active": False}),
    )
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFileAnalysisProgress",
        Mock(return_value={"status": {"phase": "idle"}, "running": False, "active": False}),
    )
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getChecksProgress",
        Mock(return_value={"status": {"phase": "idle"}, "entries": [], "findings_count": 0}),
    )
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getChecksFindingsStatus",
        Mock(return_value={
            "statuses": {
                "dimension_issues": {"status": "ready", "count": 1, "save_only": False},
                "duplicate_faces": {"status": "ready", "count": 2, "save_only": True},
            },
        }),
    )
    monkeypatch.setattr(imgdata_api.IMGDATA, "getChecksFindingEntries", Mock(side_effect=AssertionError("status route must not load entries")))

    assert _run(imgdata_api.face_matching_findings_status(object()))["success"] is True
    assert _run(imgdata_api.face_matching_progress(object()))["success"] is True
    assert _run(imgdata_api.file_analysis_progress(object()))["success"] is True
    assert _run(imgdata_api.checks_progress(object()))["success"] is True
    assert _run(imgdata_api.checks_findings_status(object()))["success"] is True

    assert len(calls) == 5
    imgdata_api.IMGDATA.getFaceMatchFindingsStatus.assert_called_once()
    imgdata_api.IMGDATA.getFaceMatchingProgress.assert_called_once_with("user-1", compact_for_response=True)
    imgdata_api.IMGDATA.getFileAnalysisProgress.assert_called_once()
    imgdata_api.IMGDATA.getChecksProgress.assert_called_once_with("user-1", "duplicate_faces")
    imgdata_api.IMGDATA.getChecksFindingsStatus.assert_called_once()
    imgdata_api.IMGDATA.getChecksFindingEntries.assert_not_called()


def test_recognition_review_runs_blocking_service_calls_off_event_loop(monkeypatch):
    async def request_body(_request):
        return {
            "action": "recognition_analyze_unknown_faces",
            "item_id": "item-1",
            "decision": "accepted",
            "operation_mode": "findings",
        }

    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA.face_recognition, "update_review", Mock(return_value={"open": 0}))
    monkeypatch.setattr(imgdata_api.IMGDATA.face_recognition, "sync_review_progress", Mock(return_value={"running": False}))

    payload = _run(imgdata_api.recognition_review(object()))

    assert payload.status_code == 200
    assert len(calls) == 2
    imgdata_api.IMGDATA.face_recognition.update_review.assert_called_once_with(
        action="recognition_analyze_unknown_faces",
        item_id="item-1",
        decision="accepted",
        user_key="user-1",
        operation_mode="findings",
    )
    imgdata_api.IMGDATA.face_recognition.sync_review_progress.assert_called_once_with(
        user_key="user-1",
        action="recognition_analyze_unknown_faces",
        operation_mode="findings",
    )


def test_recognition_suggestions_apply_forwards_assignment_action(monkeypatch):
    async def request_body(_request):
        return {
            "action": "recognition_check_person_assignments",
            "selected_suggestion_ids": ["assign-1"],
            "operation_mode": "findings",
        }

    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA.face_recognition, "apply_suggestions", Mock(return_value={"written_count": 1}))
    monkeypatch.setattr(imgdata_api.IMGDATA.face_recognition, "sync_review_progress", Mock(return_value={"running": False}))

    payload = _run(imgdata_api.recognition_suggestions_apply(object()))

    assert payload.status_code == 200
    assert len(calls) == 2
    imgdata_api.IMGDATA.face_recognition.apply_suggestions.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        selected_ids=["assign-1"],
        operation_mode="findings",
        action="recognition_check_person_assignments",
    )
    imgdata_api.IMGDATA.face_recognition.sync_review_progress.assert_called_once_with(
        user_key="user-1",
        action="recognition_check_person_assignments",
        operation_mode="findings",
    )


def test_cleanup_progress_logs_compact_progress_summary(monkeypatch):
    async def request_body(_request):
        return {"action": "recognition_build_profiles"}

    debug_log = Mock()
    progress = {
        "operation_id": "cleanup-recognition-1",
        "revision": 12,
        "action": "recognition_build_profiles",
        "running": True,
        "finished": False,
        "status": {"operation": "cleanup", "phase": "reading_reference_images"},
        "persons_scanned": 2,
        "persons_total": 214,
        "images_scanned": 42,
        "images_total": 933,
        "profiles_built": 2,
    }
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api, "backend_debug_log", debug_log)
    monkeypatch.setattr(imgdata_api.IMGDATA, "getCleanupProgress", Mock(return_value=progress))

    response = _run(imgdata_api.cleanup_progress(object()))

    assert response.status_code == 200
    imgdata_api.IMGDATA.getCleanupProgress.assert_called_once_with("user-1", "recognition_build_profiles")
    debug_log.assert_called_once()
    assert debug_log.call_args.args == ("cleanup_progress_end",)
    assert debug_log.call_args.kwargs["progress"]["running"] is True
    assert debug_log.call_args.kwargs["progress"]["status_phase"] == "reading_reference_images"
    assert debug_log.call_args.kwargs["persons_total"] == 214
    assert debug_log.call_args.kwargs["profiles_built"] == 2


def test_file_image_runs_synology_status_lookup_off_event_loop(monkeypatch, tmp_path):
    calls = _install_backend_call_recorder(monkeypatch)
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"not-a-real-jpeg")

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api.IMGDATA, "status_system", Mock(return_value={"shared_folder": str(tmp_path)}))
    monkeypatch.setattr(imgdata_api.IMGDATA.files, "extractEmbeddedJpegPreview", Mock(return_value=b"preview"))

    response = _run(imgdata_api.file_image(object(), path=str(image_path)))

    assert response.status_code == 200
    assert len(calls) == 1
    imgdata_api.IMGDATA.status_system.assert_called_once()


def test_file_image_decodes_heic_preview_before_returning_original(monkeypatch, tmp_path):
    calls = _install_backend_call_recorder(monkeypatch)
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"\x00\x00\x00\x18ftypheic")
    decoded = type("Decoded", (), {"success": True, "image_bytes": b"\xff\xd8decoded", "source": "pillow-heif", "error": ""})()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api.IMGDATA, "status_system", Mock(return_value={"shared_folder": str(tmp_path)}))
    monkeypatch.setattr(imgdata_api.IMGDATA.files, "extractEmbeddedJpegPreview", Mock(return_value=None))
    monkeypatch.setattr(imgdata_api.IMGDATA.image_decoder, "decode_to_jpeg", Mock(return_value=decoded))

    response = _run(imgdata_api.file_image(object(), path=str(image_path)))

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.body == b"\xff\xd8decoded"
    assert len(calls) == 2
    imgdata_api.IMGDATA.image_decoder.decode_to_jpeg.assert_called_once_with(str(image_path))


def test_file_image_returns_placeholder_for_incompatible_image_when_preview_fails(monkeypatch, tmp_path):
    calls = _install_backend_call_recorder(monkeypatch)
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"\x00\x00\x00\x18ftypheic")
    decoded = type("Decoded", (), {
        "success": False,
        "image_bytes": b"",
        "source": "pillow-heif",
        "error": "decoder_not_installed",
    })()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api.IMGDATA, "status_system", Mock(return_value={"shared_folder": str(tmp_path)}))
    monkeypatch.setattr(imgdata_api.IMGDATA.files, "extractEmbeddedJpegPreview", Mock(return_value=None))
    monkeypatch.setattr(imgdata_api.IMGDATA.image_decoder, "decode_to_jpeg", Mock(return_value=decoded))
    monkeypatch.setattr(imgdata_api, "backend_debug_log", Mock())

    response = _run(imgdata_api.file_image(object(), path=str(image_path)))

    assert response.status_code == 200
    assert response.media_type == "image/svg+xml"
    assert b"Preview unavailable" in response.body
    assert b"ftypheic" not in response.body
    assert len(calls) == 2
    imgdata_api.backend_debug_log.assert_called_once()


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
