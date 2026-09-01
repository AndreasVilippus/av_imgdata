from api.session_manager import SessionManager
from datetime import datetime, timedelta, timezone
from imgdata import ImgDataService
from pathlib import Path


def make_service():
    return ImgDataService(SessionManager())


def assert_runtime_identity(progress, *, operation, action, mode="scan", phase="running"):
    assert progress["operation"] == operation
    assert progress["action"] == action
    assert progress["mode"] == mode
    assert progress["phase"] == phase
    assert progress["operation_id"]
    assert progress["revision"] == 1
    assert progress["last_updated_at"]


def test_face_match_progress_has_normalized_runtime_identity():
    service = make_service()
    service._setFaceMatchingProgress(
        "user",
        action="search_photo_face_in_file",
        source_mode="scan",
        running=True,
    )

    assert_runtime_identity(
        service.getFaceMatchingProgress("user"),
        operation="face_match",
        action="search_photo_face_in_file",
    )


def test_checks_progress_has_normalized_runtime_identity():
    service = make_service()
    service._setChecksProgress(
        "user",
        check_type="name_conflicts",
        source_mode="scan",
        running=True,
    )

    assert_runtime_identity(
        service.getChecksProgress("user", "name_conflicts"),
        operation="checks",
        action="name_conflicts",
    )


def test_cleanup_progress_has_normalized_runtime_identity():
    service = make_service()
    service._setCleanupProgress(
        "user",
        action="normalize_names",
        running=True,
    )

    assert_runtime_identity(
        service.getCleanupProgress("user"),
        operation="cleanup",
        action="normalize_names",
    )


def test_cleanup_progress_preserves_schema_status_mode_as_runtime_identity():
    service = make_service()
    state_key = service._cleanupStateKey("user", "recognition_analyze_unknown_faces")
    service.runtime_state.memory("cleanup_progress")[state_key] = {
        "action": "recognition_analyze_unknown_faces",
        "running": False,
        "finished": True,
        "status": {
            "schema_version": 1,
            "operation": "cleanup",
            "action": "recognition_analyze_unknown_faces",
            "mode": "findings",
            "phase": "review_required",
        },
    }

    progress = service.getCleanupProgress("user", "recognition_analyze_unknown_faces")

    assert progress["operation"] == "cleanup"
    assert progress["action"] == "recognition_analyze_unknown_faces"
    assert progress["mode"] == "findings"
    assert progress["status"]["mode"] == "findings"


def test_cleanup_progress_marks_resume_available_when_cursor_is_present():
    service = make_service()
    state_key = service._cleanupStateKey("user", "recognition_analyze_unknown_faces")
    service.runtime_state.memory("cleanup_progress")[state_key] = {
        "action": "recognition_analyze_unknown_faces",
        "running": False,
        "finished": True,
        "phase": "review_required",
        "resume_cursor": {
            "resume_start_person_index": 14,
            "resume_person_id": 42804,
            "resume_progress_counts": {
                "persons_scanned": 14,
                "persons_total": 1586,
            },
        },
    }

    progress = service.getCleanupProgress("user", "recognition_analyze_unknown_faces")

    assert progress["resume_available"] is True
    assert progress["resume_cursor"]["resume_person_id"] == 42804


def test_cleanup_progress_prefers_current_memory_state_over_stale_persistence():
    service = make_service()
    state_key = service._cleanupStateKey("user", "standardize_face_frames")
    service.runtime_state.memory("cleanup_progress")[state_key] = {
        "action": "standardize_face_frames",
        "running": False,
        "finished": True,
        "current_path": "/photo/current.jpg",
        "revision": 3,
    }
    service.file_analysis.readRuntimeState = lambda *_args: {
        "action": "standardize_face_frames",
        "running": True,
        "finished": False,
        "current_path": "/photo/stale.jpg",
        "revision": 1,
    }

    progress = service.getCleanupProgress("user", "standardize_face_frames")

    assert progress["current_path"] == "/photo/current.jpg"
    assert progress["revision"] == 3


def test_cleanup_progress_reconnects_to_single_running_memory_state_for_new_user_key():
    service = make_service()
    old_state_key = service._cleanupStateKey("old-user", "recognition_analyze_unknown_faces")
    service.runtime_state.memory("cleanup_progress")[old_state_key] = {
        "action": "recognition_analyze_unknown_faces",
        "operation": "cleanup",
        "running": True,
        "finished": False,
        "images_scanned": 185,
        "images_total": 985,
        "operation_id": "cleanup-recognition_analyze_unknown_faces-1",
        "revision": 995,
    }

    progress = service.getCleanupProgress("new-user", "recognition_check_person_assignments")

    assert progress["running"] is True
    assert progress["action"] == "recognition_analyze_unknown_faces"
    assert progress["operation_id"] == "cleanup-recognition_analyze_unknown_faces-1"
    assert progress["images_scanned"] == 185


def test_cleanup_progress_does_not_reconnect_to_single_finished_foreign_memory_state():
    service = make_service()
    old_state_key = service._cleanupStateKey("old-user", "recognition_analyze_unknown_faces")
    service.runtime_state.memory("cleanup_progress")[old_state_key] = {
        "action": "recognition_analyze_unknown_faces",
        "operation": "cleanup",
        "running": False,
        "finished": True,
        "images_scanned": 185,
        "images_total": 985,
        "operation_id": "cleanup-recognition_analyze_unknown_faces-1",
        "revision": 995,
    }

    progress = service.getCleanupProgress("new-user", "recognition_check_person_assignments")

    assert progress["running"] is False
    assert progress["action"] == "recognition_check_person_assignments"
    assert progress.get("operation_id", "") == ""
    assert progress.get("images_scanned", 0) == 0


def test_cleanup_progress_marks_stale_stopping_state_terminal_after_restart():
    service = make_service()
    state_key = service._cleanupStateKey("user", "recognition_analyze_unknown_faces")
    service.file_analysis.writeRuntimeState(
        "cleanup_progress",
        state_key,
        {
            "action": "recognition_analyze_unknown_faces",
            "operation": "cleanup",
            "running": True,
            "finished": False,
            "stop_requested": True,
            "message_key": "cleanup:progress_stopping",
            "phase": "stopping",
            "last_updated_at": (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat(),
            "operation_id": "cleanup-recognition_analyze_unknown_faces-1",
            "revision": 12,
        },
    )

    progress = service.getCleanupProgress("user", "recognition_analyze_unknown_faces")

    assert progress["running"] is False
    assert progress["finished"] is True
    assert progress["stale"] is True
    assert progress["stop_requested"] is True
    assert progress["phase"] == "stopped"
    assert progress["message_key"] == "cleanup:progress_stopped"


def test_active_recognition_cleanup_progress_replaces_idle_message_in_backend():
    service = make_service()
    state_key = service._cleanupStateKey("user", "recognition_analyze_unknown_faces")
    service.runtime_state.memory("cleanup_progress")[state_key] = {
        "action": "recognition_analyze_unknown_faces",
        "operation": "cleanup",
        "running": True,
        "active": True,
        "finished": False,
        "message_key": "",
        "message": "No action running.",
        "status": {
            "schema_version": 1,
            "operation": "cleanup",
            "action": "recognition_analyze_unknown_faces",
            "mode": "scan",
            "phase": "running",
        },
        "operation_id": "cleanup-recognition_analyze_unknown_faces-1",
        "revision": 3,
    }

    progress = service.getCleanupProgress("user", "recognition_analyze_unknown_faces")

    assert progress["running"] is True
    assert progress["action"] == "recognition_analyze_unknown_faces"
    assert progress["message_key"] == "cleanup:progress_checking_person_short"
    assert progress["message"] == "Checking person..."


def test_file_analysis_progress_has_normalized_runtime_identity():
    service = make_service()
    service._setFileAnalysisProgress(
        action="scan",
        running=True,
        status="running",
        phase="analysis",
        files_analyzed=3,
        files_matched_total=10,
    )

    progress = service.getFileAnalysisProgress()

    assert_runtime_identity(progress, operation="file_analysis", action="scan", phase="analysis")
    assert progress["status_text"] == "running"
    assert progress["status"]["schema_version"] == 1
    assert progress["status"]["operation"] == "file_analysis"
    assert progress["status"]["action"] == "scan"
    assert progress["status"]["mode"] == "scan"
    assert progress["status"]["phase"] == "analysis"
    assert progress["status"]["progress"]["current"] == 3
    assert progress["status"]["progress"]["total"] == 10


def test_runtime_progress_stores_are_owned_only_by_runtime_state_service():
    service = make_service()

    for attribute in (
        "_face_matching_progress",
        "_checks_progress",
        "_cleanup_progress",
        "_face_matching_threads",
        "_checks_threads",
        "_cleanup_threads",
        "_checks_stop_requests",
        "_checks_active_context",
        "_file_analysis_progress",
        "_file_analysis_thread",
    ):
        assert not hasattr(service, attribute)


def test_file_analysis_worker_is_backed_by_runtime_state_service():
    service = make_service()
    worker = object()

    service.runtime_state.set_value("file_analysis_threads", "default", worker)

    assert service.runtime_state.get_value("file_analysis_threads", "default") is worker

    service.runtime_state.pop_value("file_analysis_threads", "default", None)

    assert service.runtime_state.get_value("file_analysis_threads", "default") is None


def test_imgdata_service_has_no_runtime_state_compatibility_aliases():
    source = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("src/imgdata.py", "src/api/imgdata_api.py")
    )

    for attribute in (
        "_face_matching_progress",
        "_face_matching_threads",
        "_checks_progress",
        "_checks_stop_requests",
        "_checks_active_context",
        "_checks_threads",
        "_cleanup_progress",
        "_cleanup_threads",
        "_file_analysis_progress",
        "_file_analysis_thread",
    ):
        assert f"self.{attribute}" not in source
        assert f"IMGDATA.{attribute}" not in source
