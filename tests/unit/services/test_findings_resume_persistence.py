from unittest.mock import Mock

from imgdata import ImgDataOperationError, ImgDataService
from services.checks_workflow_service import ChecksWorkflowService
from services.face_match_workflow_service import FaceMatchWorkflowService


def make_service():
    service = ImgDataService.__new__(ImgDataService)
    service.file_analysis = Mock()
    service.face_match_findings = Mock()
    service.checks_workflow = ChecksWorkflowService(service, ImgDataOperationError)
    service.face_match_workflow = FaceMatchWorkflowService(service)
    return service


def test_checks_resume_uses_persisted_entries_and_removes_duplicate_tokens():
    service = make_service()
    duplicate = {
        "review_type": "dimension_issues",
        "image_path": "/volume1/photo/a.jpg",
        "entry_id": "dimension-a",
    }
    service.file_analysis.readCheckFindings.return_value = {
        "check_type": "dimension_issues",
        "save_only": True,
        "entries": [duplicate, dict(duplicate)],
    }

    entries = service._resumeChecksSavedEntries(
        check_type="dimension_issues",
        save_only=True,
        resume_cursor={"path_index": 10},
    )

    assert entries == [duplicate]


def test_face_match_resume_uses_persisted_entries_for_face_and_target_skip_lists():
    service = make_service()
    entry = {
        "action": "search_photo_face_in_file",
        "image_path": "/volume1/photo/a.jpg",
        "face": {"face_id": 42},
        "metadata_face": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},
    }
    service.face_match_findings.read.return_value = {
        "action": "search_photo_face_in_file",
        "save_only": True,
        "entries": [entry, dict(entry)],
    }

    entries = service._resumeFaceMatchSavedEntries(
        action="search_photo_face_in_file",
        save_only=True,
        resume_cursor={"skip_face_ids": []},
    )

    assert len(entries) == 1
    assert service._faceMatchSavedEntryFaceIds(entries) == [42]
    assert len(service._faceMatchSavedEntryTargetTokens(entries)) == 1


def test_checks_failed_terminal_write_preserves_persisted_entries():
    service = make_service()
    entries = [{"review_type": "dimension_issues", "image_path": "/volume1/photo/a.jpg"}]
    service.file_analysis.readCheckFindings.return_value = {
        "save_only": True,
        "shared_folder": "/volume1/photo",
        "entries": entries,
    }
    service.checks_workflow.write_findings = Mock()

    service._writePersistedChecksFindingsStatus(
        check_type="dimension_issues",
        status="failed",
        save_only=True,
    )

    service.checks_workflow.write_findings.assert_called_once_with(
        check_type="dimension_issues",
        status="failed",
        shared_folder="/volume1/photo",
        source_mode="scan",
        save_only=True,
        entries=entries,
    )


def test_face_match_failed_terminal_write_preserves_persisted_entries():
    service = make_service()
    entries = [{"image_path": "/volume1/photo/a.jpg", "face": {"face_id": 42}}]
    service.face_match_findings.read.return_value = {
        "job_id": "job-a",
        "started_at": "2026-05-31T10:00:00+02:00",
        "shared_folder": "/volume1/photo",
        "entries": entries,
    }
    service._writeFaceMatchFindings = Mock()

    service._writePersistedFaceMatchFindingsStatus(
        action="search_photo_face_in_file",
        status="failed",
        auto=False,
        save_only=True,
        transferred_count=3,
    )

    service._writeFaceMatchFindings.assert_called_once_with(
        status="failed",
        shared_folder="/volume1/photo",
        action="search_photo_face_in_file",
        auto=False,
        save_only=True,
        transferred_count=3,
        entries=entries,
        job_id="job-a",
        started_at="2026-05-31T10:00:00+02:00",
    )


def test_missing_photos_save_only_shared_folder_failure_preserves_resumed_entries():
    service = make_service()
    entry = {
        "action": "mark_missing_photos_faces",
        "image_path": "/volume1/photo/a.jpg",
        "metadata_face": {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},
    }
    service.core = Mock()
    service.core.getSharedFolder.return_value = ""
    service.face_match_findings.read.return_value = {
        "action": "mark_missing_photos_faces",
        "save_only": True,
        "entries": [entry],
    }
    service._setFaceMatchingProgressMessage = Mock()
    service._writeFaceMatchFindings = Mock()

    result = service.searchMissingPhotosFaces(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        save_only=True,
        resume_cursor={"action": "mark_missing_photos_faces", "save_only": True},
    )

    assert result["error"] == "shared_folder_not_found"
    assert service._writeFaceMatchFindings.call_args.kwargs["status"] == "failed"
    assert service._writeFaceMatchFindings.call_args.kwargs["entries"] == [entry]
