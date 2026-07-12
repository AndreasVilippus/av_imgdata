#!/usr/bin/env python3
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.config_service import ConfigService
from services.worker_api_service import WorkerApiError, WorkerApiService
from services.worker_provisioning_service import WorkerProvisioningService
from services.worker_runtime_service import (
    WorkerCredentialService,
    WorkerProtocol,
    WorkerRuntimePathService,
    WorkerStateStore,
)


UTC = timezone.utc


def _config(tmp_path: Path, state_path: str = "") -> ConfigService:
    service = ConfigService(str(tmp_path / "config.json"))
    service.writeConfig({"worker_api": {"ENABLED": True, "STATE_PATH": state_path}})
    return service


def test_state_path_priority_explicit_config_environment_default(tmp_path: Path, monkeypatch):
    config = _config(tmp_path, "configured/state.json")
    paths = WorkerRuntimePathService(package_var=tmp_path, config_service=config)
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_STATE_PATH", "environment/state.json")

    assert paths.state_path(Path("explicit/state.json")) == (tmp_path / "explicit/state.json").resolve()
    assert paths.state_path() == (tmp_path / "configured/state.json").resolve()

    config.writeConfig({"worker_api": {"ENABLED": True, "STATE_PATH": ""}})
    assert paths.state_path() == (tmp_path / "environment/state.json").resolve()

    monkeypatch.delenv("AV_IMGDATA_WORKER_API_STATE_PATH")
    assert paths.state_path() == (tmp_path / "worker-api-state.json").resolve()


def test_state_store_migrates_schema_one_without_losing_fields(tmp_path: Path):
    state_path = tmp_path / "worker-api-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "tokens": {"legacy": {"token_hash": "hash", "created_at": "old"}},
        "workers": {"worker-1": {"status": "ready"}},
        "jobs": {},
        "custom": {"keep": True},
    }), encoding="utf-8")

    state = WorkerStateStore(package_var=tmp_path).read()

    assert state["schema_version"] == WorkerProtocol.SCHEMA_VERSION
    assert state["enrollments"] == {}
    assert state["tokens"]["legacy"]["scopes"] == list(WorkerProtocol.DEFAULT_TOKEN_SCOPES)
    assert state["custom"] == {"keep": True}


def test_state_store_distinguishes_missing_invalid_and_read_failure(tmp_path: Path, monkeypatch):
    store = WorkerStateStore(package_var=tmp_path)
    assert store.read() == store.default_state()

    store.state_path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(WorkerApiError, match="state_invalid"):
        store.read()

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied")))
    with pytest.raises(WorkerApiError, match="state_read_failed"):
        store.read()


def test_enrollment_token_is_enforced_by_normal_worker_api(tmp_path: Path):
    now = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    config = _config(tmp_path)
    store = WorkerStateStore(package_var=tmp_path, config_service=config)
    provisioning = WorkerProvisioningService(
        package_var=tmp_path,
        config_service=config,
        state_store=store,
        clock=lambda: now,
    )
    api = WorkerApiService(
        package_var=tmp_path,
        config_service=config,
        state_store=store,
        clock=lambda: now,
    )
    enrollment = provisioning.create_enrollment(enrollment_id="win-1")
    token = provisioning.redeem_enrollment(
        enrollment_code=enrollment["enrollment_code"],
        worker_id="worker-1",
    )["token"]

    api.register_worker(token=token, worker_id="worker-1", version="1.0", capabilities=["face_native_embed"])

    with pytest.raises(WorkerApiError, match="token_worker_mismatch"):
        api.heartbeat(token=token, worker_id="worker-2")


def test_scope_is_enforced_for_worker_api_and_model_download(tmp_path: Path):
    store = WorkerStateStore(package_var=tmp_path)
    credentials = WorkerCredentialService(store)
    token = credentials.issue_token(
        token_id="models-only",
        scopes=[WorkerProtocol.TOKEN_SCOPE_MODELS_READ],
        created_at="2026-07-12T12:00:00Z",
    )["token"]
    api = WorkerApiService(package_var=tmp_path, state_store=store)

    with pytest.raises(WorkerApiError, match="token_scope_missing"):
        api.register_worker(token=token, worker_id="worker-1", version="1.0")

    assert credentials.authenticate(
        token=token,
        worker_id="worker-1",
        scope=WorkerProtocol.TOKEN_SCOPE_MODELS_READ,
    )["scopes"] == [WorkerProtocol.TOKEN_SCOPE_MODELS_READ]


def test_heartbeat_requires_registration_and_preserves_registration_fields(tmp_path: Path):
    api = WorkerApiService(package_var=tmp_path)
    token = api.create_token(token_id="worker") ["token"]

    with pytest.raises(WorkerApiError, match="worker_not_registered"):
        api.heartbeat(token=token, worker_id="worker-1")

    api.register_worker(
        token=token,
        worker_id="worker-1",
        version="1.2.3",
        capabilities=["face_native_embed"],
        metadata={"platform": "windows"},
    )
    heartbeat = api.heartbeat(token=token, worker_id="worker-1", status="busy")

    assert heartbeat["worker"]["version"] == "1.2.3"
    assert heartbeat["worker"]["capabilities"] == ["face_native_embed"]
    assert heartbeat["worker"]["metadata"] == {"platform": "windows"}
    assert heartbeat["worker"]["status"] == "busy"


def test_capabilities_are_whitelisted_and_mapped_to_job_types(tmp_path: Path):
    assert WorkerProtocol.normalize_capabilities(["face_native_embed", "unknown", "face_native_embed"]) == [
        "face_native_embed"
    ]
    assert WorkerProtocol.supported_job_types(["face_native_embed"]) == {"face_native_embed"}

    api = WorkerApiService(package_var=tmp_path)
    with pytest.raises(WorkerApiError, match="job_type_unsupported"):
        api.enqueue_job(job_id="job-1", job_type="unknown", payload={})


def test_admin_status_is_backend_owned_and_reports_enrollment_phases(tmp_path: Path):
    current = [datetime(2026, 7, 12, 12, 0, tzinfo=UTC)]
    config = _config(tmp_path)
    store = WorkerStateStore(package_var=tmp_path, config_service=config)
    provisioning = WorkerProvisioningService(
        package_var=tmp_path,
        config_service=config,
        state_store=store,
        clock=lambda: current[0],
    )
    api = WorkerApiService(
        package_var=tmp_path,
        config_service=config,
        state_store=store,
        clock=lambda: current[0],
    )
    provisioning.create_enrollment(enrollment_id="waiting", expires_minutes=15)
    provisioning.create_enrollment(enrollment_id="expired", expires_minutes=1)
    current[0] += timedelta(minutes=2)

    status = api.admin_status()
    phases = {entry["enrollment_id"]: entry["status"] for entry in status["enrollments"]}

    assert status["schema_version"] == WorkerProtocol.SCHEMA_VERSION
    assert status["component"] == "external_worker"
    assert phases == {"waiting": "waiting", "expired": "expired"}


def test_runtime_status_uses_backend_status_contract(tmp_path: Path):
    api = WorkerApiService(package_var=tmp_path)
    status = api.status()

    assert status == {
        "schema_version": WorkerProtocol.SCHEMA_VERSION,
        "component": "external_worker",
        "phase": "ready",
        "workers": 0,
        "jobs": {"total": 0, "by_status": {}},
    }
