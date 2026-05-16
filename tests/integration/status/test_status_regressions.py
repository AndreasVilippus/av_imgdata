import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service() -> ImgDataService:
    return ImgDataService(SessionManager())


def _counter_keys(status):
    return [counter.get("key") for counter in status.get("counters", [])]


def test_regression_checks_save_only_scan_never_uses_stored_findings_count():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="running",
        save_only=True,
        files_scanned=1,
        total_files=100,
        findings_count=0,
        stored_findings_count=1777,
    )

    assert _counter_keys(status) == ["findings"]
    assert status["counters"][0]["value"] == 0


def test_regression_checks_save_only_scan_never_sends_resolved_ignored_or_transferred():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="running",
        save_only=True,
        files_scanned=1,
        total_files=100,
        findings_count=5,
        resolved_count=4,
        ignored_count=3,
        transferred_count=2,
    )

    assert _counter_keys(status) == ["findings"]


def test_regression_face_match_save_only_scan_never_sends_transferred_or_skipped():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_file_face_in_sources",
        source_mode="scan",
        phase="running",
        save_only=True,
        progress_kind="files",
        current=10,
        total=200,
        findings_count=3,
        transferred_count=5,
        skipped_count=2,
    )

    assert _counter_keys(status) == ["findings"]


def test_regression_face_match_auto_apply_never_sends_findings_counter():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="running",
        save_only=False,
        progress_kind="persons",
        current=10,
        total=200,
        findings_count=99,
        transferred_count=1,
    )

    assert "findings" not in _counter_keys(status)
    assert _counter_keys(status) == ["transferred"]


def test_regression_findings_review_progress_total_represents_entries_not_findings_counter():
    service = _service()

    checks_status = service._buildChecksStatusPayload(
        check_type="duplicate_faces",
        source_mode="findings",
        phase="running",
        save_only=False,
        entries_current=2,
        entries_total=10,
        findings_count=10,
    )
    face_status = service._buildFaceMatchStatusPayload(
        action="load_photo_face_match_findings",
        source_mode="findings",
        phase="running",
        save_only=False,
        progress_kind="entries",
        current=2,
        total=10,
        findings_count=10,
    )

    assert checks_status["progress"]["kind"] == "entries"
    assert checks_status["progress"]["total"] == 10
    assert "findings" not in _counter_keys(checks_status)

    assert face_status["progress"]["kind"] == "entries"
    assert face_status["progress"]["total"] == 10
    assert "findings" not in _counter_keys(face_status)


def test_regression_finished_face_match_save_only_progress_uses_stored_finding_count():
    service = _service()
    service.getFaceMatchFindings = lambda: {"entries": []}

    progress = service._normalizeFaceMatchingProgressForDisplay("user", {
        "action": "search_photo_face_in_file",
        "running": False,
        "finished": True,
        "save_only": True,
        "findings_count": 4,
        "message_key": "face_match:progress_findings_saved",
        "message_params": {"count": 4},
        "result": {"findings_count": 4},
        "resume_cursor": {
            "action": "search_photo_face_in_file",
            "save_only": True,
            "findings_count": 4,
        },
    })

    assert progress["findings_count"] == 0
    assert progress["message_params"]["count"] == 0
    assert progress["result"]["findings_count"] == 0
    assert progress["resume_cursor"]["findings_count"] == 0
