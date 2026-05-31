from services.runtime_operation_service import RuntimeOperationService
from services.runtime_state_service import RuntimeStateService
from services.status_payload_builder import StatusPayloadBuilder


def make_service(*, persistence=None):
    status_builder = StatusPayloadBuilder()
    return RuntimeStateService(
        runtime_operations=RuntimeOperationService(
            timestamp_func=lambda: "2026-05-31T10:00:00+00:00",
            status_builder=status_builder,
        ),
        status_builder=status_builder,
        persistence=persistence,
    )


def test_stamp_progress_adds_normalized_runtime_identity():
    progress = make_service().stamp_progress(
        {
            "running": True,
            "source_mode": "findings",
            "message_key": "face_match:progress_running",
        },
        operation="face_match",
        action="Load_Photo_Face_Match_Findings",
    )

    assert progress["operation"] == "face_match"
    assert progress["action"] == "load_photo_face_match_findings"
    assert progress["mode"] == "findings"
    assert progress["phase"] == "running"
    assert progress["revision"] == 1
    assert progress["last_updated_at"] == "2026-05-31T10:00:00+00:00"


def test_normalize_progress_scopes_stopping_phase_without_incrementing_revision():
    progress = make_service().normalize_progress(
        {
            "running": True,
            "stop_requested": True,
            "revision": 7,
            "source_mode": "scan",
        },
        operation="checks",
        action="name_conflicts",
    )

    assert progress["operation"] == "checks"
    assert progress["action"] == "name_conflicts"
    assert progress["mode"] == "scan"
    assert progress["phase"] == "stopping"
    assert progress["revision"] == 7


def test_stamp_progress_does_not_keep_failed_phase_when_new_run_is_active():
    progress = make_service().stamp_progress(
        {
            "running": True,
            "finished": False,
            "phase": "failed",
        },
        operation="cleanup",
        action="normalize_names",
    )

    assert progress["phase"] == "running"


def test_memory_store_is_owned_per_runtime_state_type():
    service = make_service()

    service.write_memory("checks_progress", "user_name_conflicts", {"running": True})
    service.write_memory("cleanup_progress", "user_normalize_names", {"running": False})

    assert service.read_memory("checks_progress", "user_name_conflicts") == {"running": True}
    assert service.read_memory("cleanup_progress", "user_normalize_names") == {"running": False}
    assert service.memory("checks_progress") is not service.memory("cleanup_progress")


def test_persisted_runtime_state_io_is_delegated_to_persistence_service():
    class Persistence:
        def __init__(self):
            self.written = {}

        def readRuntimeState(self, state_type, state_key):
            return self.written.get((state_type, state_key), {})

        def writeRuntimeState(self, state_type, state_key, payload):
            self.written[(state_type, state_key)] = dict(payload)
            return True

    persistence = Persistence()
    service = make_service(persistence=persistence)

    assert service.persist("face_match_progress", "user", {"running": True}) is True
    assert service.read_persisted("face_match_progress", "user") == {"running": True}


def test_values_store_can_replace_context_without_breaking_existing_reference():
    service = make_service()
    context = service.values("checks_active_context")

    service.replace_values("checks_active_context", {"check_type": "name_conflicts"})

    assert context == {"check_type": "name_conflicts"}
    assert context is service.values("checks_active_context")


def test_singleton_store_can_replace_payload_without_breaking_existing_reference():
    service = make_service()
    progress = service.singleton("file_analysis_progress")

    service.replace_singleton("file_analysis_progress", {"running": True})

    assert progress == {"running": True}
    assert progress is service.singleton("file_analysis_progress")


def test_singleton_store_can_be_replaced_while_state_lock_is_held():
    service = make_service()

    with service.lock("file_analysis_progress"):
        service.replace_singleton("file_analysis_progress", {"running": True})

    assert service.singleton("file_analysis_progress") == {"running": True}


def test_single_value_store_supports_worker_lifecycle():
    service = make_service()
    worker = object()

    service.set_value("file_analysis_threads", "default", worker)

    assert service.get_value("file_analysis_threads", "default") is worker
    assert service.pop_value("file_analysis_threads", "default") is worker
    assert service.get_value("file_analysis_threads", "default") is None


def test_first_blocking_progress_returns_first_non_excluded_running_operation():
    service = make_service()

    progress = service.first_blocking_progress(
        [
            ("file_analysis", {"running": False}),
            ("face_match", {"running": True, "operation_id": "face-match-running"}),
            ("cleanup", {"running": True, "operation_id": "cleanup-running"}),
        ],
        exclude_operation="checks",
    )

    assert progress == {
        "running": True,
        "operation_id": "face-match-running",
        "operation": "face_match",
    }
