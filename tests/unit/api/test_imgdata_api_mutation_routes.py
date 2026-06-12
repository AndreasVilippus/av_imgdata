import asyncio
import json
from unittest.mock import Mock

from api.session_manager import SessionManagerError
from api import imgdata_api


SESSION_CTX = {
    "user_key": "user-1",
    "cookies": {"_SSID": "sid-1"},
    "base_url": "https://dsm.example.test",
}


async def _prepared_session(_request):
    return dict(SESSION_CTX), None


def _run(coro):
    return asyncio.run(coro)


def _json_response_payload(response):
    if isinstance(response, dict):
        return response
    return json.loads(response.body.decode("utf-8"))


def _install_backend_call_recorder(monkeypatch):
    calls = []

    async def recorded_backend_call(func):
        calls.append(func)
        return func()

    monkeypatch.setattr(imgdata_api, "_run_backend_call", recorded_backend_call)
    return calls


def test_face_matching_findings_status_filters_by_requested_action(monkeypatch):
    async def request_body(_request):
        return {"action": "search_photo_face_in_file"}

    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFaceMatchFindingsStatus",
        Mock(return_value={
            "status": "finished",
            "action": "mark_missing_photos_faces",
            "save_only": True,
            "auto": True,
            "transferred_count": 7,
            "entries": [{"id": 1}],
        }),
    )

    payload = _run(imgdata_api.face_matching_findings_status(object()))

    assert payload["success"] is True
    assert payload["data"]["count"] == 0
    assert payload["data"]["action"] == "mark_missing_photos_faces"
    assert payload["data"]["requested_action"] == "search_photo_face_in_file"
    assert payload["data"]["save_only"] is False
    assert payload["data"]["auto"] is False
    assert len(calls) == 1


def test_face_matching_findings_status_uses_count_without_entries(monkeypatch):
    async def request_body(_request):
        return {"action": "mark_missing_photos_faces"}

    calls = _install_backend_call_recorder(monkeypatch)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(
        imgdata_api.IMGDATA,
        "getFaceMatchFindingsStatus",
        Mock(return_value={
            "status": "running",
            "action": "mark_missing_photos_faces",
            "save_only": True,
            "auto": True,
            "transferred_count": 3,
            "count": 1909,
        }),
    )

    payload = _run(imgdata_api.face_matching_findings_status(object()))

    assert payload["success"] is True
    assert payload["data"]["count"] == 1909
    assert payload["data"]["action"] == "mark_missing_photos_faces"
    assert payload["data"]["save_only"] is True
    assert payload["data"]["auto"] is True
    assert payload["data"]["transferred_count"] == 3
    assert len(calls) == 1


def test_face_matching_action_passes_selected_findings_action_to_loader(monkeypatch):
    async def request_body(_request):
        return {
            "action": "load_photo_face_match_findings",
            "findings_action": "mark_missing_photos_faces",
            "auto": True,
            "refresh": True,
        }

    load_entries = Mock(return_value={"count": 0, "entries": []})

    class FakeLoop:
        async def run_in_executor(self, _executor, func):
            return func()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(imgdata_api.IMGDATA, "getFaceMatchFindingEntriesLocked", load_entries)

    payload = _run(imgdata_api.face_matching_action(object()))

    assert payload["success"] is True
    load_entries.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        action="mark_missing_photos_faces",
        auto=True,
        refresh=True,
    )


def test_face_create_match_creates_person_removes_finding_and_saves_mapping(monkeypatch):
    async def request_body(_request):
        return {
            "face_id": "77",
            "person_name": " Person Target ",
            "save_mapping": True,
            "source_name": "Person Legacy",
        }

    create = Mock(return_value={
        "target_person": {"id": 91, "name": "Person Target"},
        "operation": "photos_create",
        "create_result": {"person_id": 91, "created": True},
    })
    remove = Mock(return_value={"count": 0, "transferred_count": 1})
    save_mapping = Mock(return_value=True)

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "resolveOrCreatePhotosPersonForExistingFace", create)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save_mapping)

    payload = _run(imgdata_api.face_create_match(object()))

    assert payload["success"] is True
    assert payload["data"]["face_id"] == 77
    assert payload["data"]["person_id"] == 91
    assert payload["data"]["result"] == {
        "target_person": {"id": 91, "name": "Person Target"},
        "operation": "photos_create",
        "create_result": {"person_id": 91, "created": True},
    }
    assert payload["data"]["findings_update"] == {"count": 0, "transferred_count": 1}
    assert payload["data"]["mapping_saved"] is True
    create.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="",
        face_id=77,
        person_name="Person Target",
        create_missing_person=True,
    )
    remove.assert_called_once_with(face_id=77, increment_transferred_count=True)
    save_mapping.assert_called_once_with(
        source_name="Person Legacy",
        target_name="Person Target",
    )


def test_face_create_match_validates_person_name_before_service_calls(monkeypatch):
    async def request_body(_request):
        return {"face_id": "77", "person_name": "   "}

    create = Mock()
    remove = Mock()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "createMatchedFaceAsPerson", create)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)

    payload = _run(imgdata_api.face_create_match(object()))

    assert payload == {
        "success": False,
        "error": {
            "code": 400,
            "message": "invalid_person_name",
        },
    }
    create.assert_not_called()
    remove.assert_not_called()


def test_face_create_metadata_match_creates_metadata_face_person_and_cleans_finding(monkeypatch):
    metadata_face = {
        "name": "Person Target",
        "source_format": "MICROSOFT",
        "x": 0.4,
        "y": 0.3,
        "w": 0.2,
        "h": 0.1,
    }

    async def request_body(_request):
        return {
            "image_path": "photo/test.jpg",
            "metadata_face": metadata_face,
            "person_name": " Person Target ",
        }

    create_metadata_person = Mock(return_value={
        "face_id": 107256,
        "item_id": 35535,
        "target_person": {"id": 91, "name": "Person Target"},
        "add_result": {"face_id": 107256, "item_id": 35535},
        "create_result": {"person_id": 91},
    })
    remove_metadata_finding = Mock(return_value={"removed": True})

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "resolveOrCreatePhotosPersonForMetadataFace", create_metadata_person)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", remove_metadata_finding)
    monkeypatch.setattr(imgdata_api.IMGDATA, "recordFaceMatchTransferProgress", Mock(return_value={}))

    payload = _run(imgdata_api.face_create_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["face_id"] == 107256
    assert payload["data"]["person_id"] == 91
    create_metadata_person.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/test.jpg",
        metadata_face=metadata_face,
        person_name="Person Target",
        create_missing_person=True,
    )
    remove_metadata_finding.assert_called_once_with(
        image_path="photo/test.jpg",
        metadata_face=metadata_face,
        increment_transferred_count=True,
    )


def test_face_create_metadata_match_optionally_updates_name_in_file(monkeypatch):
    metadata_face = {"name": "Old Name", "source_format": "MWG_REGIONS"}

    async def request_body(_request):
        return {
            "image_path": "photo/test.jpg",
            "metadata_face": metadata_face,
            "person_name": "New Name",
            "update_metadata_name": True,
        }

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "resolveOrCreatePhotosPersonForMetadataFace", Mock(return_value={
        "face_id": 7,
        "target_person": {"id": 8, "name": "New Name"},
    }))
    replace = Mock(return_value={"updated": True})
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceMetadataFaceName", replace)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", Mock(return_value={"removed": True}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "recordFaceMatchTransferProgress", Mock(return_value={}))

    payload = _run(imgdata_api.face_create_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["metadata_update"] == {"updated": True}
    replace.assert_called_once_with(
        image_path="photo/test.jpg",
        face_data=metadata_face,
        new_name="New Name",
    )


def test_face_delete_metadata_match_deletes_file_face_and_cleans_finding(monkeypatch):
    metadata_face = {"name": "Wrong", "source_format": "MWG_REGIONS"}

    async def request_body(_request):
        return {"image_path": "photo/test.jpg", "metadata_face": metadata_face}

    delete = Mock(return_value={"deleted": True})
    remove = Mock(return_value={"removed": True, "remaining_count": 2})
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "deleteMetadataFace", delete)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", remove)

    payload = _run(imgdata_api.face_delete_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["result"] == {"deleted": True}
    delete.assert_called_once_with(image_path="photo/test.jpg", face_data=metadata_face)
    remove.assert_called_once_with(
        image_path="photo/test.jpg",
        metadata_face=metadata_face,
        increment_transferred_count=False,
    )


def test_face_apply_metadata_match_forwards_oriented_display_face_and_removes_finding(monkeypatch):
    metadata_face = {
        "name": "",
        "source": "embedded_xmp_parsed",
        "source_format": "MWG_REGIONS",
        "x": 0.63764,
        "y": 0.43534,
        "w": 0.24366,
        "h": 0.18274,
        "orientation": 6,
        "display_normalized": True,
        "bbox": {
            "x1": 0.51581,
            "x2": 0.75947,
            "y1": 0.34397,
            "y2": 0.52671,
        },
    }

    async def request_body(_request):
        return {
            "image_path": "photo/hannover/20170422_193209.jpg",
            "metadata_face": metadata_face,
            "person_name": " Kira Bolm ",
        }

    replace = Mock(return_value={
        "updated": True,
        "warning": "",
        "target_path": "photo/hannover/20170422_193209.jpg",
    })
    remove = Mock(return_value={"removed": True, "remaining_count": 40, "transferred_count": 67})

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceMetadataFaceName", replace)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", remove)

    payload = _run(imgdata_api.face_apply_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["person_name"] == "Kira Bolm"
    assert payload["data"]["result"]["updated"] is True
    assert payload["data"]["findings_update"] == {
        "removed": True,
        "remaining_count": 40,
        "transferred_count": 67,
    }
    replace.assert_called_once_with(
        image_path="photo/hannover/20170422_193209.jpg",
        face_data=metadata_face,
        new_name="Kira Bolm",
    )
    remove.assert_called_once_with(
        image_path="photo/hannover/20170422_193209.jpg",
        metadata_face=metadata_face,
        increment_transferred_count=True,
    )


def test_face_apply_metadata_match_keeps_finding_when_oriented_display_face_is_not_found(monkeypatch):
    metadata_face = {
        "name": "",
        "source": "embedded_xmp_parsed",
        "source_format": "MWG_REGIONS",
        "x": 0.63764,
        "y": 0.43534,
        "w": 0.24366,
        "h": 0.18274,
        "orientation": 6,
        "display_normalized": True,
    }

    async def request_body(_request):
        return {
            "image_path": "photo/hannover/20170422_193209.jpg",
            "metadata_face": metadata_face,
            "person_name": "Kira Bolm",
        }

    replace = Mock(return_value={
        "updated": False,
        "warning": "checks:warning_face_replace_not_found",
    })
    remove = Mock()

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceMetadataFaceName", replace)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", remove)

    payload = _run(imgdata_api.face_apply_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["result"]["updated"] is False
    assert payload["data"]["result"]["warning"] == "checks:warning_face_replace_not_found"
    assert payload["data"]["findings_update"] is None
    remove.assert_not_called()


def test_checks_replace_metadata_face_name_uses_snapshot_refresh_for_name_conflicts(monkeypatch):
    face = {
        "source": "photos",
        "source_format": "PHOTOS",
        "face_id": 77,
        "person_id": 11,
        "name": "Person Legacy",
    }

    async def request_body(_request):
        return {
            "image_path": "photo/test.jpg",
            "face": face,
            "new_name": "Person Current",
            "check_type": "name_conflicts",
            "save_mapping": True,
            "source_name": "Person Legacy",
        }

    replace = Mock(return_value={
        "updated": True,
        "operation": "photos_assign",
        "resolved_name": "Person Current",
        "target_person": {"id": 42, "name": "Person Current"},
    })
    safe_refresh = Mock(return_value=({"snapshot_update": True, "count": 0}, None))
    save_mapping = Mock(return_value=True)

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save_mapping)

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    assert payload["data"]["updated"] is True
    assert payload["data"]["findings_update"] == {"snapshot_update": True, "count": 0}
    assert payload["data"]["mapping_saved"] is True
    replace.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/test.jpg",
        face_data=face,
        new_name="Person Current",
        create_missing_person=False,
    )
    safe_refresh.assert_called_once()
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "name_conflicts"
    assert refresh_kwargs["image_path"] == "photo/test.jpg"
    assert refresh_kwargs["original_face_data"] == face
    assert refresh_kwargs["replacement_face_data"]["name"] == "Person Current"
    assert refresh_kwargs["replacement_face_data"]["person_id"] == 42
    assert refresh_kwargs["resolved_delta"] == 1
    save_mapping.assert_called_once_with(
        source_name="Person Legacy",
        target_name="Person Current",
    )


def test_checks_replace_metadata_face_name_forwards_metadata_replacement_to_snapshot(monkeypatch):
    face = {
        "source": "embedded_xmp_parsed",
        "source_format": "MWG_REGIONS",
        "x": 0.41707,
        "y": 0.53581,
        "w": 0.04338,
        "h": 0.02885,
        "name": "Jelizaveta Vilippus geb.  Kromskaja",
    }

    async def request_body(_request):
        return {
            "image_path": "photo/jelizaveta.jpg",
            "face": face,
            "new_name": "Jelizaveta Vilippus geb. Kromskaja",
            "save_mapping": False,
        }

    replace = Mock(return_value={
        "updated": True,
        "operation": "metadata_write",
        "already_updated": True,
    })
    safe_refresh = Mock(return_value=({"snapshot_update": True, "count": 0}, None))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    safe_refresh.assert_called_once()
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "name_conflicts"
    assert refresh_kwargs["image_path"] == "photo/jelizaveta.jpg"
    assert refresh_kwargs["original_face_data"] == face
    assert refresh_kwargs["replacement_face_data"]["name"] == "Jelizaveta Vilippus geb. Kromskaja"
    assert refresh_kwargs["replacement_face_data"]["source_format"] == "MWG_REGIONS"
    assert "person_id" not in refresh_kwargs["replacement_face_data"]
    assert refresh_kwargs["resolved_delta"] == 1


def test_checks_replace_metadata_face_name_uses_requested_review_type_for_refresh(monkeypatch):
    face = {
        "source": "embedded_xmp_parsed",
        "source_format": "MWG_REGIONS",
        "name": "Kaire Vilippus",
    }

    async def request_body(_request):
        return {
            "image_path": "photo/duplicate.jpg",
            "face": face,
            "new_name": "Andreas Vilippus",
            "review_type": "duplicate_faces",
        }

    replace = Mock(return_value={
        "updated": True,
        "operation": "metadata_write",
    })
    safe_refresh = Mock(return_value=({"snapshot_update": True, "count": 0}, None))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    replace.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/duplicate.jpg",
        face_data=face,
        new_name="Andreas Vilippus",
        create_missing_person=False,
    )
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "duplicate_faces"
    assert refresh_kwargs["replacement_face_data"]["name"] == "Andreas Vilippus"
    assert refresh_kwargs["resolved_delta"] == 1


def test_checks_replace_metadata_face_name_refreshes_stale_duplicate_on_not_found(monkeypatch):
    face = {
        "source": "embedded_xmp_parsed",
        "source_format": "ACD",
        "name": "Klaus Heine",
        "x": 0.81373,
        "y": 0.54292,
        "w": 0.10247,
        "h": 0.18215,
    }

    async def request_body(_request):
        return {
            "image_path": "photo/duplicate.jpg",
            "face": face,
            "new_name": "Werner Kodantke",
            "review_type": "duplicate_faces",
        }

    replace = Mock(return_value={
        "updated": False,
        "warning": "checks:warning_face_replace_not_found",
        "operation": "metadata_write",
    })
    safe_refresh = Mock(return_value=({
        "image_path": "photo/duplicate.jpg",
        "image_entries": [],
        "count": 0,
    }, None))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    assert payload["data"]["updated"] is False
    assert payload["data"]["warning"] == "checks:warning_face_replace_not_found"
    assert payload["data"]["findings_update"]["image_entries"] == []
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "duplicate_faces"
    assert refresh_kwargs["image_path"] == "photo/duplicate.jpg"
    assert "original_face_data" not in refresh_kwargs
    assert "replacement_face_data" not in refresh_kwargs
    assert "resolved_delta" not in refresh_kwargs


def test_checks_replace_metadata_face_name_snapshot_removes_nested_metadata_signature_name(monkeypatch):
    image_path = "/volume1/photo/2019/2019.08.29-30 - Kaareli ja Jelizaveta pulm/2019.08.30 - kaareli ja jelizaveta pulm073.jpg"
    face = {
        "h": 0.02885,
        "name": "Jelizaveta Vilippus geb.  Kromskaja",
        "orientation": None,
        "source": "embedded_xmp_parsed",
        "source_format": "MWG_REGIONS",
        "w": 0.04338,
        "x": 0.41707,
        "y": 0.53581,
    }
    entry = {
        "review_type": "name_conflicts",
        "image_path": image_path,
        "face_name": "Jelizaveta Vilippus geb. Kromskaja",
        "left_face_signature": {
            "h": 0.031402,
            "name": "Jelizaveta Vilippus geb. Kromskaja",
            "source": "embedded_xmp_parsed",
            "source_format": "ACD",
            "w": 0.03894,
            "x": 0.412958,
            "y": 0.538349,
        },
        "right_face_signature": dict(face),
    }
    findings = {
        "check_type": "name_conflicts",
        "source_mode": "scan",
        "save_only": True,
        "entries": [entry],
        "count": 1,
    }
    written = {}

    async def request_body(_request):
        return {
            "image_path": image_path,
            "face": face,
            "new_name": "Jelizaveta Vilippus geb. Kromskaja",
            "save_mapping": False,
            "source_name": "Jelizaveta Vilippus geb.  Kromskaja",
        }

    replace = Mock(return_value={
        "updated": True,
        "warning": "",
        "already_updated": True,
        "operation": "metadata_write",
    })

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)
    monkeypatch.setattr(imgdata_api.IMGDATA.file_analysis, "readCheckFindings", Mock(return_value=findings))
    monkeypatch.setattr(
        imgdata_api.IMGDATA.file_analysis,
        "writeCheckFindings",
        Mock(side_effect=lambda finding_type, payload: written.setdefault("payload", payload) or True),
    )
    monkeypatch.setattr(imgdata_api.IMGDATA, "getChecksProgress", Mock(return_value={}))
    monkeypatch.setattr(imgdata_api.IMGDATA.runtime_state, "write", Mock(return_value={}))
    monkeypatch.setattr(imgdata_api.IMGDATA, "_utcNowIso", Mock(return_value="2026-05-15T07:45:00+02:00"))

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    update = payload["data"]["findings_update"]
    assert update["removed_count"] == 1
    assert update["count"] == 0
    assert update["image_entries"] == []
    assert written["payload"]["entries"] == []


def test_checks_replace_metadata_face_name_returns_session_error_details(monkeypatch):
    face = {
        "source": "photos",
        "source_format": "PHOTOS",
        "face_id": 133684,
        "person_id": 8675,
        "name": "Asta Vilippus",
    }
    detail = {
        "error": "api_failed",
        "api": "SYNO.FotoTeam.Browse.Person",
        "response": {"success": False, "error": {"code": 106}},
    }

    async def request_body(_request):
        return {
            "image_path": "photo/Dia_032_033.jpg",
            "face": face,
            "new_name": "Stephanie Kempf",
            "create_missing_person": True,
        }

    replace = Mock(side_effect=SessionManagerError(detail, status_code=401))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "replaceChecksFaceName", replace)

    response = _run(imgdata_api.checks_replace_metadata_face_name(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is False
    assert payload["error"]["code"] == 401
    assert payload["error"]["message"] == "session_manager_error"
    assert payload["error"]["details"] == detail


def test_checks_assign_face_person_forwards_photos_override_to_refresh(monkeypatch):
    face = {
        "source": "photos",
        "source_format": "PHOTOS",
        "face_id": 77,
        "person_id": 11,
        "name": "Person Legacy",
    }

    async def request_body(_request):
        return {
            "image_path": "photo/test.jpg",
            "face": face,
            "review_type": "duplicate_faces",
            "person_id": "42",
            "person_name": " Person Current ",
        }

    assign = Mock(return_value={"updated": True})
    safe_refresh = Mock(return_value=({"count": 0}, None))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "assignChecksFaceToKnownPerson", assign)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)

    response = _run(imgdata_api.checks_assign_face_person(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    assert payload["data"]["updated"] is True
    assert payload["data"]["findings_update"] == {"count": 0}
    assign.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/test.jpg",
        face_data=face,
        person_id=42,
        person_name="Person Current",
    )
    safe_refresh.assert_called_once()
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "duplicate_faces"
    assert refresh_kwargs["image_path"] == "photo/test.jpg"
    assert refresh_kwargs["original_face_data"] == face
    assert refresh_kwargs["replacement_face_data"]["face_id"] == 77
    assert refresh_kwargs["replacement_face_data"]["name"] == "Person Current"
    assert refresh_kwargs["replacement_face_data"]["person_id"] == 42
    assert "resolved_delta" not in refresh_kwargs


def test_checks_assign_face_person_forwards_metadata_override_to_refresh(monkeypatch):
    face = {
        "source": "embedded_xmp_exiftool",
        "source_format": "MICROSOFT",
        "name": "Person Legacy",
    }

    async def request_body(_request):
        return {
            "image_path": "photo/test.jpg",
            "face": face,
            "review_type": "position_deviations",
            "person_id": "42",
            "person_name": " Person Current ",
        }

    assign = Mock(return_value={"updated": True})
    safe_refresh = Mock(return_value=({"count": 0}, None))

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "assignChecksFaceToKnownPerson", assign)
    monkeypatch.setattr(imgdata_api, "_safe_refresh_checks_mutation_state", safe_refresh)

    response = _run(imgdata_api.checks_assign_face_person(object()))
    payload = _json_response_payload(response)

    assert payload["success"] is True
    assign.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/test.jpg",
        face_data=face,
        person_id=42,
        person_name="Person Current",
    )
    refresh_kwargs = safe_refresh.call_args.kwargs
    assert refresh_kwargs["check_type"] == "position_deviations"
    assert refresh_kwargs["image_path"] == "photo/test.jpg"
    assert refresh_kwargs["original_face_data"] == face
    assert refresh_kwargs["replacement_face_data"]["source_format"] == "MICROSOFT"
    assert refresh_kwargs["replacement_face_data"]["name"] == "Person Current"
    assert refresh_kwargs["replacement_face_data"]["person_id"] == 42
    assert "resolved_delta" not in refresh_kwargs


def test_database_name_mappings_forwards_pagination_and_search(monkeypatch):
    async def request_body(_request):
        return {"search": "alias", "page": 2, "page_size": 10}

    calls = _install_backend_call_recorder(monkeypatch)
    list_page = Mock(return_value={"entries": [{"id": 11}], "page": 2, "page_size": 10, "total": 12})
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "listNameMappingsPage", list_page)

    payload = _run(imgdata_api.database_name_mappings(object()))

    assert payload["success"] is True
    assert payload["data"]["list"] == "name_mappings"
    assert payload["data"]["total"] == 12
    list_page.assert_called_once_with(search="alias", page=2, page_size=10)
    assert len(calls) == 1


def test_database_name_mapping_delete_validates_and_deletes(monkeypatch):
    async def request_body(_request):
        return {"id": 42}

    calls = _install_backend_call_recorder(monkeypatch)
    delete = Mock(return_value=True)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "deleteNameMapping", delete)

    payload = _run(imgdata_api.database_name_mapping_delete(object()))

    assert payload == {"success": True, "data": {"id": 42, "deleted": True}}
    delete.assert_called_once_with(42)
    assert len(calls) == 1


def test_database_name_mapping_save_validates_and_saves(monkeypatch):
    async def request_body(_request):
        return {"source_name": "Alias", "target_name": "Person"}

    calls = _install_backend_call_recorder(monkeypatch)
    save = Mock(return_value=True)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save)

    payload = _run(imgdata_api.database_name_mapping_save(object()))

    assert payload == {
        "success": True,
        "data": {"id": None, "source_name": "Alias", "target_name": "Person", "saved": True},
    }
    save.assert_called_once_with(source_name="Alias", target_name="Person")
    assert len(calls) == 1


def test_database_name_mapping_save_updates_existing_mapping_by_id(monkeypatch):
    async def request_body(_request):
        return {"id": 17, "source_name": "Alias", "target_name": "Updated Person"}

    calls = _install_backend_call_recorder(monkeypatch)
    update = Mock(return_value=True)
    save = Mock(return_value=True)
    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "updateNameMappingTarget", update)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save)

    payload = _run(imgdata_api.database_name_mapping_save(object()))

    assert payload["success"] is True
    assert payload["data"]["id"] == 17
    update.assert_called_once_with(17, "Updated Person")
    save.assert_not_called()
    assert len(calls) == 1
