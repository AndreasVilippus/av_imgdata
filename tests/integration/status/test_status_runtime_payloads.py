import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service() -> ImgDataService:
    return ImgDataService(SessionManager())


def _status(payload):
    assert isinstance(payload, dict)
    status = payload.get("status")
    assert isinstance(status, dict), f"Missing status in payload: {payload}"
    return status


def _counter_keys(status):
    return [counter.get("key") for counter in status.get("counters", [])]


def test_runtime_attach_checks_running_save_only_status():
    service = _service()

    payload = service._attachChecksStatusPayload(
        {
            "running": True,
            "finished": False,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "save_only": True,
            "files_scanned": 12,
            "total_files": 30,
            "findings_count": 4,
            "message_key": "checks:progress_scanning",
        },
        check_type="name_conflicts",
    )

    status = _status(payload)
    assert status["schema_version"] == 1
    assert status["operation"] == "checks"
    assert status["action"] == "name_conflicts"
    assert status["mode"] == "scan"
    assert status["phase"] == "running"
    assert status["progress"]["kind"] == "files"
    assert status["progress"]["current"] == 12
    assert status["progress"]["total"] == 30
    assert _counter_keys(status) == ["findings"]


def test_runtime_attach_checks_stopping_status():
    service = _service()

    payload = service._attachChecksStatusPayload(
        {
            "running": True,
            "finished": False,
            "stop_requested": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "save_only": True,
            "files_scanned": 12,
            "total_files": 30,
            "findings_count": 4,
            "message_key": "checks:progress_stopping",
        },
        check_type="name_conflicts",
    )

    status = _status(payload)
    assert status["phase"] == "stopping"
    assert _counter_keys(status) == ["findings"]


def test_runtime_attach_checks_finished_status():
    service = _service()

    payload = service._attachChecksStatusPayload(
        {
            "running": False,
            "finished": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "save_only": True,
            "files_scanned": 30,
            "total_files": 30,
            "findings_count": 5,
            "message_key": "checks:progress_findings_saved",
        },
        check_type="name_conflicts",
    )

    status = _status(payload)
    assert status["phase"] == "finished"
    assert _counter_keys(status) == ["findings"]


def test_runtime_attach_checks_empty_status_keeps_zero_findings_visible():
    service = _service()

    payload = service._attachChecksStatusPayload(
        {
            "running": False,
            "finished": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "save_only": True,
            "files_scanned": 30,
            "total_files": 30,
            "findings_count": 0,
            "message_key": "checks:progress_findings_empty",
        },
        check_type="name_conflicts",
    )

    status = _status(payload)
    assert status["phase"] == "empty"
    assert _counter_keys(status) == ["findings"]
    assert status["counters"][0]["value"] == 0


def test_runtime_attach_checks_failed_status_sends_error_counter_when_present():
    service = _service()

    payload = service._attachChecksStatusPayload(
        {
            "running": False,
            "finished": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "save_only": False,
            "files_scanned": 5,
            "total_files": 30,
            "errors_count": 1,
            "message_key": "checks:progress_failed",
        },
        check_type="name_conflicts",
    )

    status = _status(payload)
    assert status["phase"] == "failed"
    assert _counter_keys(status) == ["errors"]


def test_runtime_checks_blocked_payload_has_status_phase_blocked():
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

    status = _status(payload)
    assert payload["blocked_by_running_scan"] is True
    assert payload["requested_check_type"] == "duplicate_faces"
    assert status["phase"] == "blocked"
    assert status["operation"] == "checks"


def test_runtime_face_match_status_builder_covers_stopping_failed_finished_empty():
    service = _service()

    stopping = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="stopping",
        save_only=True,
        progress_kind="persons",
        current=10,
        total=100,
        findings_count=3,
    )
    failed = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="failed",
        save_only=False,
        progress_kind="persons",
        current=10,
        total=100,
        errors_count=1,
    )
    finished = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="finished",
        save_only=False,
        progress_kind="persons",
        current=100,
        total=100,
        transferred_count=8,
    )
    empty = service._buildFaceMatchStatusPayload(
        action="search_photo_face_in_file",
        source_mode="scan",
        phase="empty",
        save_only=True,
        progress_kind="persons",
        current=100,
        total=100,
        findings_count=0,
    )

    assert stopping["phase"] == "stopping"
    assert _counter_keys(stopping) == ["findings"]

    assert failed["phase"] == "failed"
    assert _counter_keys(failed) == ["errors"]

    assert finished["phase"] == "finished"
    assert _counter_keys(finished) == ["transferred"]

    assert empty["phase"] == "empty"
    assert _counter_keys(empty) == ["findings"]
    assert empty["counters"][0]["value"] == 0
