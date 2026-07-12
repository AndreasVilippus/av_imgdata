#!/usr/bin/env python3

from datetime import datetime, timezone

import pytest

from services.worker_api_service import WorkerApiError, WorkerApiService
from services.worker_provisioning_service import WorkerProvisioningService


UTC = timezone.utc


def _enroll(service: WorkerProvisioningService, enrollment_id: str, worker_id: str):
    created = service.create_enrollment(enrollment_id=enrollment_id, expires_minutes=15)
    return service.redeem_enrollment(
        enrollment_code=created["enrollment_code"],
        worker_id=worker_id,
    )


def test_reenrollment_replaces_previous_worker_tokens(tmp_path):
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    service = WorkerProvisioningService(package_var=tmp_path, clock=lambda: now)

    first = _enroll(service, "first", "windows-worker-01")
    second = _enroll(service, "second", "windows-worker-01")

    assert second["replaced_tokens"] == 1
    with pytest.raises(WorkerApiError, match="unauthorized"):
        service.require_token(token=first["token"], worker_id="windows-worker-01", scope="worker_api")
    assert service.require_token(
        token=second["token"],
        worker_id="windows-worker-01",
        scope="worker_api",
    )["worker_id"] == "windows-worker-01"


def test_delete_worker_removes_bound_tokens_and_requeues_claimed_jobs(tmp_path):
    provisioning = WorkerProvisioningService(package_var=tmp_path)
    enrolled = _enroll(provisioning, "worker-registration", "windows-worker-01")
    api = WorkerApiService(package_var=tmp_path, state_store=provisioning.store)

    api.register_worker(
        token=enrolled["token"],
        worker_id="windows-worker-01",
        version="0.10.0",
        capabilities=["face_native_embed"],
    )
    api.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
    claimed = api.claim_job(
        token=enrolled["token"],
        worker_id="windows-worker-01",
        capabilities=["face_native_embed"],
    )
    assert claimed["status"] == "claimed"

    deleted = api.delete_worker(worker_id="windows-worker-01")

    assert deleted["status"] == "deleted"
    assert deleted["deleted_tokens"] == 1
    assert deleted["requeued_jobs"] == 1
    state = api.store.read()
    assert "windows-worker-01" not in state["workers"]
    assert state["jobs"]["job-1"]["status"] == "queued"
    assert "claimed_by" not in state["jobs"]["job-1"]
    with pytest.raises(WorkerApiError, match="unauthorized"):
        api.credentials.authenticate(token=enrolled["token"], worker_id="windows-worker-01")


def test_delete_unknown_worker_is_explicit(tmp_path):
    api = WorkerApiService(package_var=tmp_path)
    with pytest.raises(WorkerApiError, match="worker_not_found"):
        api.delete_worker(worker_id="missing-worker")
