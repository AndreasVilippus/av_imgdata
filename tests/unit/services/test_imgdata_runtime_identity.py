from api.session_manager import SessionManager
from imgdata import ImgDataService
from pathlib import Path


def make_service():
    return ImgDataService(SessionManager())


def assert_runtime_identity(progress, *, operation, action, mode="scan"):
    assert progress["operation"] == operation
    assert progress["action"] == action
    assert progress["mode"] == mode
    assert progress["phase"] == "running"
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


def test_file_analysis_progress_has_normalized_runtime_identity():
    service = make_service()
    service._setFileAnalysisProgress(
        action="scan",
        running=True,
    )

    assert_runtime_identity(
        service.getFileAnalysisProgress(),
        operation="file_analysis",
        action="scan",
    )


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
