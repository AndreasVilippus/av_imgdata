from pathlib import Path
from unittest.mock import Mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from imgdata import ImgDataService
from services.face_match_workflow_service import FaceMatchWorkflowService


def make_service():
    service = ImgDataService.__new__(ImgDataService)
    service.face_match_workflow = FaceMatchWorkflowService(service)
    service.photos = Mock()
    service.photos.listFotoTeamPersonKnown.return_value = [{"id": 1, "name": "Person A"}]
    service.photos.sortPersonsForFaceMatch.side_effect = lambda persons: persons
    service.getFaceMatchFindings = Mock(
        return_value={
            "status": "stopped",
            "shared_folder": "/volume1/photo",
            "action": "mark_missing_photos_faces",
            "save_only": True,
            "auto": False,
            "transferred_count": 0,
            "entries": [
                {
                    "action": "mark_missing_photos_faces",
                    "image_path": "/volume1/photo/a.jpg",
                    "source_name": "Person A",
                    "metadata_face": {"name": "Person A"},
                }
            ],
        }
    )
    service._storedFaceMatchEntryExists = Mock(return_value=True)
    service._resolveStoredFaceMatchEntry = Mock(side_effect=lambda **kwargs: dict(kwargs["entry"]))
    service._persistFaceMatchFindingsEntries = Mock()
    return service


def test_get_face_match_finding_entries_does_not_refresh_by_default_with_session_context():
    service = make_service()

    result = service.getFaceMatchFindingEntries(
        user_key="user",
        cookies={"id": "session"},
        base_url="https://dsm.example.test",
        auto=False,
    )

    assert result["count"] == 1
    assert result["entries"][0]["image_path"] == "/volume1/photo/a.jpg"
    service.photos.listFotoTeamPersonKnown.assert_not_called()
    service._storedFaceMatchEntryExists.assert_not_called()
    service._resolveStoredFaceMatchEntry.assert_not_called()
    service._persistFaceMatchFindingsEntries.assert_not_called()


def test_get_face_match_finding_entries_strips_debug_payload_from_response():
    service = make_service()
    service.getFaceMatchFindings.return_value["entries"] = [{
        "action": "search_photo_face_in_file",
        "image_path": "/volume1/photo/a.jpg",
        "lookup_debug": {"candidates": list(range(100))},
        "resume_cursor": {"skip_face_ids": [1]},
        "matched_person": {
            "id": 7,
            "name": "Person A",
            "additional": {
                "thumbnail": {
                    "cache_key": "abc",
                    "extra": "not-needed",
                },
                "large_blob": "not-needed",
            },
            "raw_payload": "not-needed",
        },
    }]

    result = service.getFaceMatchFindingEntries()
    entry = result["entries"][0]

    assert "lookup_debug" not in entry
    assert "resume_cursor" not in entry
    assert entry["matched_person"] == {
        "id": 7,
        "name": "Person A",
        "additional": {
            "thumbnail": {
                "cache_key": "abc",
            },
        },
    }


def test_get_face_match_finding_entries_refresh_true_revalidates_stored_entries():
    service = make_service()

    result = service.getFaceMatchFindingEntries(
        user_key="user",
        cookies={"id": "session"},
        base_url="https://dsm.example.test",
        auto=False,
        refresh=True,
    )

    assert result["count"] == 1
    service.photos.listFotoTeamPersonKnown.assert_called_once()
    service.photos.sortPersonsForFaceMatch.assert_called_once()
    service._storedFaceMatchEntryExists.assert_called_once()
    service._resolveStoredFaceMatchEntry.assert_called_once()


def test_get_face_match_finding_entries_returns_empty_for_other_action():
    service = make_service()

    result = service.getFaceMatchFindingEntries(
        user_key="user",
        cookies={"id": "session"},
        base_url="https://dsm.example.test",
        action="search_photo_face_in_file",
        auto=False,
        refresh=True,
    )

    assert result["count"] == 0
    assert result["entries"] == []
    assert result["action"] == "mark_missing_photos_faces"
    assert result["requested_action"] == "search_photo_face_in_file"
    service.photos.listFotoTeamPersonKnown.assert_not_called()
    service._storedFaceMatchEntryExists.assert_not_called()


def test_face_matching_action_wires_refresh_and_reports_generic_errors_as_json():
    source = (Path(__file__).resolve().parents[1] / "src" / "api" / "imgdata_api.py").read_text(encoding="utf-8")

    assert 'refresh = bool(body.get("refresh"))' in source
    assert "refresh=refresh" in source
    assert "face_matching_action_failed" in source
