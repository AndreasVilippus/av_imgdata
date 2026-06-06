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


def test_get_face_match_finding_entries_repairs_stream_compacted_legacy_file():
    service = make_service()
    entry = {
        "action": "mark_missing_photos_faces",
        "image_path": "/volume1/photo/a.jpg",
        "metadata_face": {"name": "Person A"},
    }
    service.getFaceMatchFindings.return_value = {
        "_stream_compacted": True,
        "status": "finished",
        "shared_folder": "/volume1/photo",
        "action": "mark_missing_photos_faces",
        "save_only": True,
        "auto": False,
        "transferred_count": 0,
        "entries": [entry],
    }

    result = service.getFaceMatchFindingEntries(action="mark_missing_photos_faces")

    assert result["count"] == 1
    service._persistFaceMatchFindingsEntries.assert_called_once_with(
        findings={
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "action": "mark_missing_photos_faces",
            "save_only": True,
            "auto": False,
            "transferred_count": 0,
            "entries": [entry],
        },
        entries=[entry],
        transferred_count=0,
    )


def test_face_match_append_unique_finding_compacts_storage_entry():
    service = make_service()
    entries = []

    appended = service.face_match_workflow.append_unique_finding(entries, {
        "action": "mark_missing_photos_faces",
        "image_path": "/volume1/photo/a.jpg",
        "metadata_face": {"name": "Person A"},
        "lookup_debug": {"large": list(range(100))},
        "resume_cursor": {"skip_targets": ["/volume1/photo/a.jpg"]},
    })

    assert appended is True
    assert len(entries) == 1
    assert "lookup_debug" not in entries[0]
    assert "resume_cursor" not in entries[0]
    assert entries[0]["image_path"] == "/volume1/photo/a.jpg"


def test_face_match_write_findings_compacts_storage_entries():
    service = make_service()
    written = {}
    service._timestamp_now = lambda: "2026-06-05T12:00:00+02:00"
    service.file_analysis = Mock()
    service.file_analysis.writeCheckFindings.side_effect = lambda finding_type, payload: written.update({
        "finding_type": finding_type,
        "payload": payload,
    }) or True

    service.face_match_workflow.write_findings(
        status="running",
        shared_folder="/volume1/photo",
        action="mark_missing_photos_faces",
        auto=False,
        save_only=True,
        transferred_count=0,
        entries=[{
            "action": "mark_missing_photos_faces",
            "image_path": "/volume1/photo/a.jpg",
            "metadata_face": {"name": "Person A"},
            "lookup_debug": {"large": list(range(100))},
            "resume_cursor": {"skip_targets": ["/volume1/photo/a.jpg"]},
        }],
        finished=False,
    )

    entry = written["payload"]["entries"][0]
    assert written["finding_type"] == "face_match"
    assert "lookup_debug" not in entry
    assert "resume_cursor" not in entry
    assert entry["image_path"] == "/volume1/photo/a.jpg"


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


def test_get_face_match_finding_entries_auto_stops_at_first_manual_entry():
    service = make_service()
    entries = [
        {
            "action": "mark_missing_photos_faces",
            "image_path": "/volume1/photo/a.jpg",
            "source_name": "Manual",
            "metadata_face": {"name": "Manual"},
        },
        {
            "action": "mark_missing_photos_faces",
            "image_path": "/volume1/photo/b.jpg",
            "source_name": "Known",
            "metadata_face": {"name": "Known"},
        },
    ]
    service.getFaceMatchFindings.return_value["entries"] = entries
    service._storedFaceMatchEntryExists.return_value = True
    service._resolveStoredFaceMatchEntry.side_effect = lambda **kwargs: dict(kwargs["entry"])
    service.resolveOrCreatePhotosPersonForMetadataFace = Mock(return_value={"updated": False})
    service._shouldStopFaceMatching = Mock(return_value=False)
    service._setFaceMatchingProgressMessage = Mock()
    service._setFaceMatchingProgress = Mock()

    result = service.getFaceMatchFindingEntries(
        user_key="user",
        cookies={"id": "session"},
        base_url="https://dsm.example.test",
        auto=True,
    )

    assert result["count"] == 2
    assert service._storedFaceMatchEntryExists.call_count == 1
    assert service._resolveStoredFaceMatchEntry.call_count == 1
    service.resolveOrCreatePhotosPersonForMetadataFace.assert_called_once()
    assert result["entries"][0]["image_path"] == "/volume1/photo/a.jpg"
    assert result["entries"][1]["image_path"] == "/volume1/photo/b.jpg"
    assert service._setFaceMatchingProgressMessage.call_args.kwargs["running"] is False
    assert service._setFaceMatchingProgressMessage.call_args.args[1] == "face_match:progress_review_required"


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
