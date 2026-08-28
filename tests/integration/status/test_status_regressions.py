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


def test_regression_checks_save_only_scan_sends_resolved_but_not_ignored_or_transferred():
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

    assert _counter_keys(status) == ["findings", "resolved"]


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


def test_regression_persisted_running_face_match_progress_remains_active_without_local_thread():
    service = _service()

    progress = service._normalizeFaceMatchingProgressForDisplay("user", {
        "action": "search_photo_face_in_file",
        "running": True,
        "finished": False,
        "message_key": "face_match:progress_checking_person",
        "resume_cursor": {
            "action": "search_photo_face_in_file",
            "persons_read": 28,
            "images_read": 71,
            "faces_read": 977,
        },
    })

    assert progress["running"] is True
    assert progress["active"] is True
    assert progress["stale"] is False
    assert progress["stop_requested"] is False


def test_regression_stale_face_match_stop_message_becomes_stopped():
    service = _service()

    progress = service._normalizeFaceMatchingProgressForDisplay("user", {
        "action": "search_photo_face_in_file",
        "running": False,
        "finished": True,
        "message_key": "face_match:progress_stopping",
        "message": "face_match:progress_stopping",
        "stop_requested": False,
    })

    assert progress["running"] is False
    assert progress["active"] is False
    assert progress["stale"] is True
    assert progress["stop_requested"] is False
    assert progress["message_key"] == "face_match:progress_stopped"
    assert progress["message"] == "face_match:progress_stopped"


def test_regression_persisted_face_match_progress_gets_status_payload():
    service = _service()
    service.file_analysis.readRuntimeState = lambda _key, _user: {
        "action": "search_photo_face_in_file",
        "running": False,
        "finished": True,
        "message_key": "face_match:result_no_match",
        "persons_read": 28,
        "persons_total": 28,
    }

    progress = service._getFaceMatchingProgressCore("user")

    assert progress["running"] is False
    assert progress["active"] is False
    assert progress["status"]["schema_version"] == 1
    assert progress["status"]["operation"] == "face_match"
    assert progress["status"]["phase"] == "finished"


def test_regression_persisted_running_file_analysis_progress_survives_backend_restart():
    service = _service()
    service.file_analysis.readRuntimeState = lambda state_type, state_key: {
        "running": True,
        "finished": False,
        "operation_id": "file-analysis-running",
        "revision": 9,
        "files_seen_total": 100,
        "files_matched_total": 40,
        "files_analyzed": 11,
    } if state_type == "file_analysis_progress" and state_key == "default" else {}

    progress = service.getFileAnalysisProgress()

    assert progress["running"] is True
    assert progress["operation"] == "file_analysis"
    assert progress["operation_id"] == "file-analysis-running"
    assert progress["revision"] == 9
    assert progress["status"]["schema_version"] == 1
    assert progress["status"]["operation"] == "file_analysis"
    assert progress["status"]["progress"]["current"] == 11
    assert progress["status"]["progress"]["total"] == 40


def test_regression_persisted_running_checks_progress_survives_backend_restart_with_identity():
    service = _service()
    service.file_analysis.readRuntimeState = lambda state_type, state_key: {
        "running": True,
        "finished": False,
        "source_mode": "scan",
        "check_type": "name_conflicts",
        "operation_id": "checks-name-conflicts-running",
        "revision": 5,
        "files_scanned": 7,
        "total_files": 20,
        "result": {
            "item": {
                "review_type": "name_conflicts",
                "left_face_target": {"source_format": "ACD", "name": "A"},
                "right_face_target": {"source_format": "MWG_REGIONS", "name": "B"},
            }
        },
    } if state_type == "checks_progress" and state_key == "user_name_conflicts" else {}

    progress = service.getChecksProgress("user", "name_conflicts")

    assert progress["running"] is True
    assert progress["operation"] == "checks"
    assert progress["action"] == "name_conflicts"
    assert progress["mode"] == "scan"
    assert progress["operation_id"] == "checks-name-conflicts-running"
    assert progress["revision"] == 5
    assert progress["status"]["schema_version"] == 1
    assert progress["status"]["operation"] == "checks"
    assert progress["status"]["action"] == "name_conflicts"
    assert progress["result"]["item"]["left_face_target"]["source_format"] == "ACD"


def test_regression_persisted_running_cleanup_progress_survives_backend_restart_with_schema():
    service = _service()
    service.file_analysis.readRuntimeState = lambda state_type, state_key: {
        "running": True,
        "finished": False,
        "action": "normalize_names",
        "operation_id": "cleanup-normalize-running",
        "revision": 4,
        "persons_total": 10,
        "persons_scanned": 3,
        "persons_updated": 1,
        "current_name": "Original Name",
    } if state_type == "cleanup_progress" and state_key == "user_normalize_names" else {}

    progress = service.getCleanupProgress("user", "normalize_names")

    assert progress["running"] is True
    assert progress["operation"] == "cleanup"
    assert progress["action"] == "normalize_names"
    assert progress["operation_id"] == "cleanup-normalize-running"
    assert progress["revision"] == 4
    assert progress["current_name"] == "Original Name"
    assert progress["status"]["schema_version"] == 1
    assert progress["status"]["operation"] == "cleanup"
    assert progress["status"]["action"] == "normalize_names"
    assert progress["status"]["progress"]["kind"] == "persons"
    assert progress["status"]["progress"]["current"] == 3


def test_regression_status_attach_preserves_face_match_result_details():
    service = _service()
    payload = service._attachFaceMatchStatusPayload({
        "running": False,
        "finished": True,
        "action": "search_photo_face_in_file",
        "result": {
            "metadata_face": {
                "source_format": "MWG_REGIONS",
                "name": "Person A",
                "x": 0.1,
                "y": 0.2,
                "w": 0.3,
                "h": 0.4,
            },
            "photos_face": {
                "face_id": 123,
                "item_id": 456,
                "person_id": 789,
            },
        },
    })

    assert payload["status"]["schema_version"] == 1
    assert payload["result"]["metadata_face"]["source_format"] == "MWG_REGIONS"
    assert payload["result"]["photos_face"]["face_id"] == 123


def test_regression_status_attach_preserves_checks_result_face_details():
    service = _service()
    payload = service._attachChecksStatusPayload({
        "running": False,
        "finished": True,
        "source_mode": "findings",
        "check_type": "position_deviations",
        "result": {
            "item": {
                "review_type": "position_deviations",
                "left_face_target": {"source_format": "MICROSOFT", "name": "Person A", "face_id": 1},
                "right_face_target": {"source_format": "PHOTOS", "name": "Person A", "face_id": 2},
            }
        },
    }, check_type="position_deviations")

    assert payload["status"]["schema_version"] == 1
    assert payload["status"]["mode"] == "findings"
    assert payload["result"]["item"]["left_face_target"]["source_format"] == "MICROSOFT"
    assert payload["result"]["item"]["right_face_target"]["face_id"] == 2
