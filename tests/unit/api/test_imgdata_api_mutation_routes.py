import asyncio
import json
from unittest.mock import Mock

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


def test_face_create_match_creates_person_removes_finding_and_saves_mapping(monkeypatch):
    async def request_body(_request):
        return {
            "face_id": "77",
            "person_name": " Person Target ",
            "save_mapping": True,
            "source_name": "Person Legacy",
        }

    create = Mock(return_value={"person_id": 91, "created": True})
    remove = Mock(return_value={"count": 0, "transferred_count": 1})
    save_mapping = Mock(return_value=True)

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "createMatchedFaceAsPerson", create)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingEntry", remove)
    monkeypatch.setattr(imgdata_api.IMGDATA, "saveNameMapping", save_mapping)

    payload = _run(imgdata_api.face_create_match(object()))

    assert payload["success"] is True
    assert payload["data"]["face_id"] == 77
    assert payload["data"]["person_id"] == 91
    assert payload["data"]["result"] == {"person_id": 91, "created": True}
    assert payload["data"]["findings_update"] == {"count": 0, "transferred_count": 1}
    assert payload["data"]["mapping_saved"] is True
    create.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        face_id=77,
        person_name="Person Target",
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

    add_face = Mock(return_value={"face_id": 107256, "item_id": 35535})
    create_person = Mock(return_value={"person_id": 91})
    remove_metadata_finding = Mock(return_value={"removed": True})

    monkeypatch.setattr(imgdata_api, "_prepare_session_request", _prepared_session)
    monkeypatch.setattr(imgdata_api, "_read_request_body", request_body)
    monkeypatch.setattr(imgdata_api.IMGDATA, "addMatchedMetadataFaceToPhotos", add_face)
    monkeypatch.setattr(imgdata_api.IMGDATA, "createMatchedFaceAsPerson", create_person)
    monkeypatch.setattr(imgdata_api.IMGDATA, "removeFaceMatchFindingMetadataEntry", remove_metadata_finding)

    payload = _run(imgdata_api.face_create_metadata_match(object()))

    assert payload["success"] is True
    assert payload["data"]["face_id"] == 107256
    assert payload["data"]["person_id"] == 91
    add_face.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        image_path="photo/test.jpg",
        metadata_face=metadata_face,
    )
    create_person.assert_called_once_with(
        user_key="user-1",
        cookies={"_SSID": "sid-1"},
        base_url="https://dsm.example.test",
        face_id=107256,
        person_name="Person Target",
        item_id=35535,
        image_path="photo/test.jpg",
    )
    remove_metadata_finding.assert_called_once_with(
        image_path="photo/test.jpg",
        metadata_face=metadata_face,
        increment_transferred_count=True,
    )


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
