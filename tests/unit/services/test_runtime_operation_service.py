from services.runtime_operation_service import RuntimeOperationService
from services.status_payload_builder import StatusPayloadBuilder


def make_service(now="2026-05-24T10:00:00+00:00"):
    return RuntimeOperationService(
        timestamp_func=lambda: now,
        status_builder=StatusPayloadBuilder(),
        stale_stopping_seconds=120,
    )


def test_stamp_progress_adds_identity_revision_and_timestamp():
    service = make_service()

    progress = service.stamp_progress(
        {"running": True},
        operation_prefix="checks",
        operation_discriminator="name_conflicts",
    )

    assert progress["operation_id"].startswith("checks-name_conflicts-")
    assert progress["revision"] == 1
    assert progress["last_updated_at"] == "2026-05-24T10:00:00+00:00"


def test_stamp_progress_preserves_existing_operation_id_and_increments_revision():
    service = make_service()

    progress = service.stamp_progress(
        {"operation_id": "face_match-existing", "revision": 7},
        operation_prefix="face_match",
    )

    assert progress["operation_id"] == "face_match-existing"
    assert progress["revision"] == 8


def test_stale_stopping_progress_blocks_only_until_timeout():
    service = make_service()

    fresh = {
        "running": True,
        "message_key": "face_match:progress_stopping",
        "last_updated_at": RuntimeOperationService.utc_now_iso(),
    }
    stale = {
        "running": True,
        "status": {"phase": "stopping"},
        "last_updated_at": "2000-01-01T00:00:00+00:00",
    }

    assert service.is_stale_stopping_progress(fresh) is False
    assert service.is_stale_stopping_progress(stale) is True
    assert service.is_blocking_running_progress(stale) is False


def test_blocked_payload_uses_schema_status_without_foreign_counters():
    payload = make_service().blocked_by_running_operation_payload(
        {
            "operation": "face_match",
            "operation_id": "face-match-running",
            "running": True,
            "findings_count": 17,
        },
        requested_operation="checks",
    )

    assert payload["blocked"] is True
    assert payload["running_operation"] == "face_match"
    assert payload["running_operation_id"] == "face-match-running"
    assert payload["status"] == {
        "schema_version": 1,
        "operation": "checks",
        "action": "",
        "mode": "none",
        "phase": "blocked",
        "save_only": False,
        "progress": {},
        "counters": [],
    }
