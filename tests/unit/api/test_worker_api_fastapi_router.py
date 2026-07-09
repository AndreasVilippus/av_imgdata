#!/usr/bin/env python3
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.worker_api import router
from services.worker_api_service import WorkerApiService


def _client(tmp_path, monkeypatch, *, enabled: bool) -> TestClient:
    monkeypatch.setenv("SYNOPKG_PKGVAR", str(tmp_path))
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_ENABLED", "1" if enabled else "0")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_worker_api_router_disabled_returns_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=False)

    response = client.get("/worker-api/status")

    assert response.status_code == 404
    assert response.json()["code"] == "worker_api_disabled"


def test_worker_api_router_heartbeat_and_status_when_enabled(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=True)
    token = WorkerApiService(package_var=tmp_path).create_token()["token"]

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer " + token},
        json={"worker_id": "worker-01", "status": "ready"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    status = client.get("/worker-api/status")
    assert status.status_code == 200
    assert status.json()["service"]["workers"] == 1


def test_worker_api_router_uses_state_path_env_override(tmp_path, monkeypatch) -> None:
    custom_state = tmp_path / "runtime" / "worker-api-state.json"
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_STATE_PATH", str(custom_state))
    client = _client(tmp_path, monkeypatch, enabled=True)
    token = WorkerApiService(package_var=tmp_path, state_path=custom_state).create_token()["token"]

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer " + token},
        json={"worker_id": "worker-01", "status": "ready"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert custom_state.exists()
    assert not (tmp_path / "worker-api-state.json").exists()


def test_worker_api_router_rejects_invalid_token(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=True)
    WorkerApiService(package_var=tmp_path).create_token()

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer invalid"},
        json={"worker_id": "worker-01", "status": "ready"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
