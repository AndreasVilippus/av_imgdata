#!/usr/bin/env python3

import json

from services.config_service import ConfigService
from services.worker_api_composition_service import (
    WorkerApiCompositionService,
    WorkerApiConfigurationService,
    worker_error_http_status,
)


def test_configuration_prefers_configured_state_path_over_environment(tmp_path, monkeypatch):
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"worker_api": {"ENABLED": True, "STATE_PATH": "configured/state.json"}})
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_STATE_PATH", str(tmp_path / "environment.json"))

    service = WorkerApiConfigurationService(package_var=tmp_path, config_service=config)

    assert service.enabled() is True
    assert service.state_path() == (tmp_path / "configured" / "state.json").resolve()


def test_enabled_environment_override_is_explicit_and_dynamic(tmp_path, monkeypatch):
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"worker_api": {"ENABLED": False}})
    service = WorkerApiConfigurationService(package_var=tmp_path, config_service=config)

    assert service.enabled() is False
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_ENABLED", "true")
    assert service.enabled() is True
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_ENABLED", "false")
    assert service.enabled() is False


def test_composition_shares_one_store_between_api_and_provisioning(tmp_path):
    composition = WorkerApiCompositionService(package_var=tmp_path)

    assert composition.worker_api.store is composition.state_store
    assert composition.provisioning.store is composition.state_store
    assert composition.worker_api.state_path == composition.provisioning.state_path


def test_composition_services_observe_the_same_state(tmp_path):
    composition = WorkerApiCompositionService(package_var=tmp_path)
    enrollment = composition.provisioning.create_enrollment(enrollment_id="worker-01")
    enrolled = composition.provisioning.redeem_enrollment(
        enrollment_code=enrollment["enrollment_code"],
        worker_id="worker-01",
    )
    composition.worker_api.register_worker(
        token=enrolled["token"],
        worker_id="worker-01",
        version="test",
    )

    status = composition.worker_api.admin_status()

    assert status["workers"][0]["worker_id"] == "worker-01"
    assert status["enrollments"][0]["status"] == "enrolled"
    persisted = json.loads(composition.state_store.state_path.read_text(encoding="utf-8"))
    assert set(persisted) >= {"tokens", "workers", "jobs", "enrollments"}


def test_worker_error_http_status_is_shared_and_stable():
    assert worker_error_http_status("unauthorized") == 401
    assert worker_error_http_status("token_worker_mismatch") == 403
    assert worker_error_http_status("worker_not_found") == 404
    assert worker_error_http_status("job_already_exists") == 409
    assert worker_error_http_status("state_read_failed") == 503
    assert worker_error_http_status("state_invalid") == 500
    assert worker_error_http_status("worker_id_required") == 400
