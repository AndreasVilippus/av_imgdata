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


def test_worker_http_and_admin_routes_use_one_composition_root():
    worker_api = _read("src/api/worker_api.py")
    admin_api = _read("src/api/worker_admin_api.py")
    local_router = _read("tools/worker-api-http-router.py")

    assert "WorkerApiCompositionService" in worker_api
    assert "WorkerApiCompositionService" in admin_api
    assert "WorkerApiCompositionService" in local_router
    assert "WorkerApiService(" not in worker_api
    assert "WorkerProvisioningService(" not in worker_api
    assert "json.load" not in admin_api
    assert "datetime.fromisoformat" not in admin_api
    assert "code_hash" not in admin_api


def test_worker_http_error_mapping_is_defined_once():
    composition = _read("src/services/worker_api_composition_service.py")
    fastapi_router = _read("src/api/worker_api.py")
    endpoints = _read("src/services/worker_api_endpoints.py")

    assert "def worker_error_http_status" in composition
    assert "worker_error_http_status(exc.code)" in fastapi_router
    assert "worker_error_http_status(exc.code)" in endpoints
    assert 'status = 401 if' not in endpoints


def test_worker_cli_uses_canonical_paths_and_store_permissions():
    cli = _read("tools/worker-api-store.py")

    assert "WorkerRuntimePathService" in cli
    assert "repair_runtime_file_permissions" not in cli
    assert "os.chown" not in cli
    assert "os.chmod" not in cli
    assert "DSM_PACKAGE_VAR" not in cli


def test_worker_protocol_is_generated_from_one_descriptor():
    runtime = _read("src/services/worker_runtime_service.py")
    generated = _read("src/services/worker_protocol_generated.py")
    generator = _read("tools/generate-worker-protocol.py")

    assert "from services.worker_protocol_generated import" in runtime
    assert "CAPABILITIES = (" in generated
    assert "worker/protocol/worker-protocol.json" in generator
    assert "JOB_TYPES_BY_CAPABILITY" in runtime


def test_worker_cxx_binaries_use_one_shared_runtime_header():
    for source_path in (
        "worker/src/main.cpp",
        "worker/src/api_loop.cpp",
        "worker/src/configure.cpp",
        "worker/src/model_sync.cpp",
    ):
        source = _read(source_path)
        assert '#include "av_imgdata/worker_protocol.h"' in source
        assert '#include "av_imgdata/worker_runtime.h"' in source


def test_worker_status_remains_backend_owned_and_schema_versioned():
    status_concept = _read("docs/status-concept-integrated.md")
    api = _read("src/services/worker_api_service.py")

    assert "The backend owns status semantics" in status_concept
    assert '"schema_version": WorkerProtocol.SCHEMA_VERSION' in api
    assert '"component": "external_worker"' in api
    assert "def admin_status" in api
