#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_worker_services_use_single_state_store_contract():
    api = _read("src/services/worker_api_service.py")
    provisioning = _read("src/services/worker_provisioning_service.py")

    assert "WorkerStateStore" in api
    assert "WorkerStateStore" in provisioning
    assert "def _read_state" not in api
    assert "def _write_state" not in api
    assert "def _read_state" not in provisioning
    assert "def _write_state" not in provisioning
    assert "tempfile.mkstemp" not in api
    assert "tempfile.mkstemp" not in provisioning


def test_worker_credentials_are_not_reimplemented_in_services():
    api = _read("src/services/worker_api_service.py")
    provisioning = _read("src/services/worker_provisioning_service.py")

    assert "WorkerCredentialService" in api
    assert "WorkerCredentialService" in provisioning
    assert "hashlib.sha256" not in api
    assert "hashlib.sha256" not in provisioning
    assert "def _require_token" not in api
    assert "def _hash" not in provisioning


def test_worker_admin_api_delegates_status_semantics_to_backend():
    admin_api = _read("src/api/worker_admin_api.py")

    assert "api.admin_status()" in admin_api
    assert "json.load" not in admin_api
    assert "datetime.fromisoformat" not in admin_api
    assert "code_hash" not in admin_api


def test_worker_cli_uses_canonical_paths_and_store_permissions():
    cli = _read("tools/worker-api-store.py")

    assert "WorkerRuntimePathService" in cli
    assert "repair_runtime_file_permissions" not in cli
    assert "os.chown" not in cli
    assert "os.chmod" not in cli
    assert "DSM_PACKAGE_VAR" not in cli


def test_worker_protocol_is_the_only_capability_default_source():
    runtime = _read("src/services/worker_runtime_service.py")
    api = _read("src/services/worker_api_service.py")

    assert "class WorkerProtocol" in runtime
    assert "JOB_TYPES_BY_CAPABILITY" in runtime
    assert "DEFAULT_CAPABILITIES = WorkerProtocol.CAPABILITIES" in api
    assert "job_type_unsupported" in api


def test_worker_status_remains_backend_owned_and_schema_versioned():
    status_concept = _read("docs/status-concept-integrated.md")
    api = _read("src/services/worker_api_service.py")

    assert "The backend owns status semantics" in status_concept
    assert '"schema_version": WorkerProtocol.SCHEMA_VERSION' in api
    assert '"component": "external_worker"' in api
    assert "def admin_status" in api
