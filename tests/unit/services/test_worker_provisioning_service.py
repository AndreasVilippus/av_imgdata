#!/usr/bin/env python3

from datetime import datetime, timedelta, timezone

import pytest

from services.worker_api_service import WorkerApiError
from services.worker_provisioning_service import WorkerProvisioningService


UTC = timezone.utc


def test_enrollment_is_one_time_and_worker_bound(tmp_path):
    now = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    service = WorkerProvisioningService(package_var=tmp_path, clock=lambda: now)
    created = service.create_enrollment(enrollment_id="windows-01", expires_minutes=15)
    enrolled = service.redeem_enrollment(enrollment_code=created["enrollment_code"], worker_id="worker-01")

    auth = service.require_token(token=enrolled["token"], worker_id="worker-01", scope="models_read")
    assert auth["worker_id"] == "worker-01"

    with pytest.raises(WorkerApiError, match="token_worker_mismatch"):
        service.require_token(token=enrolled["token"], worker_id="worker-02", scope="models_read")

    with pytest.raises(WorkerApiError, match="enrollment_code_used"):
        service.redeem_enrollment(enrollment_code=created["enrollment_code"], worker_id="worker-01")


def test_expired_enrollment_is_rejected(tmp_path):
    current = [datetime(2026, 7, 10, 12, 0, tzinfo=UTC)]
    service = WorkerProvisioningService(package_var=tmp_path, clock=lambda: current[0])
    created = service.create_enrollment(enrollment_id="windows-01", expires_minutes=1)
    current[0] += timedelta(minutes=2)

    with pytest.raises(WorkerApiError, match="enrollment_code_expired"):
        service.redeem_enrollment(enrollment_code=created["enrollment_code"], worker_id="worker-01")
