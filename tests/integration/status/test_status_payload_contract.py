import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service() -> ImgDataService:
    return ImgDataService(SessionManager())


def _counter_keys(status):
    return [counter.get("key") for counter in status.get("counters", [])]


def _counter(status, key):
    for counter in status.get("counters", []):
        if counter.get("key") == key:
            return counter
    raise AssertionError(f"Missing counter: {key}; available={_counter_keys(status)}")


def test_generic_status_builder_methods_exist():
    service = _service()

    for method_name in (
        "_buildStatusCounter",
        "_buildStatusProgress",
        "_buildStatusPayload",
        "_buildChecksStatusPayload",
        "_buildFaceMatchStatusPayload",
    ):
        assert hasattr(service, method_name), f"Missing backend status builder: {method_name}"


def test_build_status_counter_contract():
    service = _service()

    counter = service._buildStatusCounter(
        "findings",
        value=0,
        label_key="checks:counter_findings",
        fallback_label="Funde",
        show_when_zero=True,
    )

    assert counter == {
        "key": "findings",
        "label_key": "checks:counter_findings",
        "fallback_label": "Funde",
        "value": 0,
        "show_when_zero": True,
    }


def test_build_status_progress_contract():
    service = _service()

    progress = service._buildStatusProgress(
        kind="files",
        current=12,
        total=30,
        title_key="checks:label_images",
        fallback_title="Bilder",
        primary_label_key="checks:label_scanned",
        fallback_primary_label="geprüft",
        secondary_label_key="checks:label_remaining",
        fallback_secondary_label="verbleibend",
    )

    assert progress == {
        "kind": "files",
        "title_key": "checks:label_images",
        "fallback_title": "Bilder",
        "current": 12,
        "total": 30,
        "primary_label_key": "checks:label_scanned",
        "fallback_primary_label": "geprüft",
        "secondary_label_key": "checks:label_remaining",
        "fallback_secondary_label": "verbleibend",
    }


def test_build_status_payload_contract():
    service = _service()

    status = service._buildStatusPayload(
        operation="checks",
        action="name_conflicts",
        mode="scan",
        phase="running",
        save_only=True,
        progress=service._buildStatusProgress(
            kind="files",
            current=12,
            total=30,
            title_key="checks:label_images",
            fallback_title="Bilder",
            primary_label_key="checks:label_scanned",
            fallback_primary_label="geprüft",
            secondary_label_key="checks:label_remaining",
            fallback_secondary_label="verbleibend",
        ),
        counters=[
            service._buildStatusCounter(
                "findings",
                value=4,
                label_key="checks:counter_findings",
                fallback_label="Funde",
                show_when_zero=True,
            )
        ],
    )

    assert status["schema_version"] == 1
    assert status["operation"] == "checks"
    assert status["action"] == "name_conflicts"
    assert status["mode"] == "scan"
    assert status["phase"] == "running"
    assert status["save_only"] is True
    assert status["progress"]["kind"] == "files"
    assert _counter_keys(status) == ["findings"]


def test_checks_save_only_scan_status_only_sends_findings_counter():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="running",
        save_only=True,
        files_scanned=120,
        total_files=41070,
        findings_count=7,
        resolved_count=9,
        ignored_count=8,
        skipped_count=6,
    )

    assert status["schema_version"] == 1
    assert status["operation"] == "checks"
    assert status["action"] == "name_conflicts"
    assert status["mode"] == "scan"
    assert status["phase"] == "running"
    assert status["save_only"] is True
    assert status["progress"]["kind"] == "files"
    assert status["progress"]["current"] == 120
    assert status["progress"]["total"] == 41070

    assert _counter_keys(status) == ["findings"]
    findings = _counter(status, "findings")
    assert findings["value"] == 7
    assert findings["show_when_zero"] is True


def test_checks_save_only_scan_status_keeps_findings_zero_visible():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="preparing",
        save_only=True,
        files_scanned=0,
        total_files=0,
        findings_count=0,
    )

    assert _counter_keys(status) == ["findings"]
    findings = _counter(status, "findings")
    assert findings["value"] == 0
    assert findings["show_when_zero"] is True


def test_checks_interactive_scan_does_not_send_stored_findings_or_irrelevant_zero_counters():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="duplicate_faces",
        source_mode="scan",
        phase="running",
        save_only=False,
        files_scanned=50,
        total_files=100,
        findings_count=0,
        resolved_count=0,
        ignored_count=0,
        skipped_count=0,
        stored_findings_count=1777,
    )

    assert status["operation"] == "checks"
    assert status["mode"] == "scan"
    assert status["save_only"] is False
    assert "findings" not in _counter_keys(status)
    assert "resolved" not in _counter_keys(status)
    assert "ignored" not in _counter_keys(status)
    assert "skipped" not in _counter_keys(status)


def test_checks_interactive_scan_sends_resolved_only_when_auto_apply_happened():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="running",
        save_only=False,
        files_scanned=80,
        total_files=100,
        findings_count=0,
        resolved_count=3,
        ignored_count=0,
        skipped_count=0,
    )

    assert _counter_keys(status) == ["resolved"]
    assert _counter(status, "resolved")["value"] == 3


def test_checks_findings_review_status_uses_entries_progress_and_action_counters():
    service = _service()

    status = service._buildChecksStatusPayload(
        check_type="name_conflicts",
        source_mode="findings",
        phase="running",
        save_only=False,
        entries_current=12,
        entries_total=1777,
        findings_count=1777,
        resolved_count=4,
        ignored_count=1,
        skipped_count=0,
    )

    assert status["operation"] == "checks"
    assert status["mode"] == "findings"
    assert status["progress"]["kind"] == "entries"
    assert status["progress"]["current"] == 12
    assert status["progress"]["total"] == 1777

    assert _counter_keys(status) == ["resolved", "ignored"]
    assert _counter(status, "resolved")["value"] == 4
    assert _counter(status, "ignored")["value"] == 1
    assert "findings" not in _counter_keys(status)


def test_checks_blocked_status_keeps_compatibility_flag_and_status_phase():
    service = _service()

    payload = service._buildChecksStartBlockedPayload(
        {
            "running": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "files_scanned": 12,
            "total_files": 30,
            "findings_count": 4,
        },
        requested_check_type="duplicate_faces",
    )

    assert payload["blocked_by_running_scan"] is True
    assert payload["requested_check_type"] == "duplicate_faces"
    assert payload["status"]["schema_version"] == 1
    assert payload["status"]["operation"] == "checks"
    assert payload["status"]["phase"] == "blocked"


def test_face_match_save_only_scan_status_only_sends_findings_counter():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="running",
        save_only=True,
        progress_kind="persons",
        current=42,
        total=600,
        findings_count=23,
        transferred_count=8,
        skipped_count=5,
    )

    assert status["schema_version"] == 1
    assert status["operation"] == "face_match"
    assert status["action"] == "search_photo_face_in_file"
    assert status["mode"] == "scan"
    assert status["save_only"] is True
    assert status["progress"]["kind"] == "persons"
    assert status["progress"]["current"] == 42
    assert status["progress"]["total"] == 600

    assert _counter_keys(status) == ["findings"]
    assert _counter(status, "findings")["value"] == 23
    assert _counter(status, "findings")["show_when_zero"] is True


def test_face_match_auto_apply_status_sends_transferred_not_findings():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="running",
        save_only=False,
        progress_kind="persons",
        current=42,
        total=600,
        findings_count=23,
        transferred_count=8,
        skipped_count=0,
    )

    assert status["operation"] == "face_match"
    assert status["mode"] == "scan"
    assert status["save_only"] is False
    assert _counter_keys(status) == ["transferred"]
    assert _counter(status, "transferred")["value"] == 8
    assert "findings" not in _counter_keys(status)


def test_face_match_auto_apply_status_sends_skipped_only_when_positive():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="running",
        save_only=False,
        progress_kind="persons",
        current=42,
        total=600,
        transferred_count=8,
        skipped_count=2,
    )

    assert _counter_keys(status) == ["transferred", "skipped"]
    assert _counter(status, "skipped")["value"] == 2


def test_face_match_findings_review_status_uses_entries_progress_and_action_counters():
    service = _service()

    status = service._buildFaceMatchStatusPayload(
        action="load_photo_face_match_findings",
        source_mode="findings",
        phase="running",
        save_only=False,
        progress_kind="entries",
        current=5,
        total=88,
        findings_count=88,
        transferred_count=2,
        skipped_count=1,
    )

    assert status["operation"] == "face_match"
    assert status["mode"] == "findings"
    assert status["progress"]["kind"] == "entries"
    assert status["progress"]["current"] == 5
    assert status["progress"]["total"] == 88

    assert _counter_keys(status) == ["transferred", "skipped"]
    assert "findings" not in _counter_keys(status)
