import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service() -> ImgDataService:
    return ImgDataService(SessionManager())


def _counter_keys(status):
    return [counter.get("key") for counter in status.get("counters", [])]


def test_checks_findings_status_reports_only_actual_action_counters():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="position_deviations",
        source_mode="findings",
        phase="running",
        save_only=False,
        entries_current=3,
        entries_total=11,
        findings_count=11,
        resolved_count=2,
        ignored_count=0,
        skipped_count=4,
        errors_count=1,
    )

    assert status["schema_version"] == 1
    assert status["operation"] == "checks"
    assert status["action"] == "position_deviations"
    assert status["mode"] == "findings"
    assert status["progress"]["kind"] == "entries"
    assert status["progress"]["current"] == 3
    assert status["progress"]["total"] == 11
    assert _counter_keys(status) == ["resolved", "skipped", "errors"]
    assert "findings" not in _counter_keys(status)
    assert "ignored" not in _counter_keys(status)


def test_face_match_findings_status_reports_errors_without_findings_counter():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="load_photo_face_match_findings",
        source_mode="findings",
        phase="running",
        progress_kind="entries",
        current=8,
        total=20,
        findings_count=20,
        transferred_count=3,
        skipped_count=0,
        errors_count=2,
    )

    assert status["schema_version"] == 1
    assert status["operation"] == "face_match"
    assert status["action"] == "load_photo_face_match_findings"
    assert status["mode"] == "findings"
    assert status["progress"]["kind"] == "entries"
    assert status["progress"]["current"] == 8
    assert status["progress"]["total"] == 20
    assert _counter_keys(status) == ["transferred", "errors"]
    assert "findings" not in _counter_keys(status)
    assert "skipped" not in _counter_keys(status)


def test_status_progress_allows_preparing_zero_total_without_losing_schema():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_file_face_in_sources",
        source_mode="scan",
        phase="preparing",
        save_only=True,
        progress_kind="files",
        current=0,
        total=0,
        findings_count=0,
    )

    assert status["schema_version"] == 1
    assert status["phase"] == "preparing"
    assert status["progress"]["kind"] == "files"
    assert status["progress"]["current"] == 0
    assert status["progress"]["total"] == 0
    assert _counter_keys(status) == ["findings"]
    assert status["counters"][0]["show_when_zero"] is True
