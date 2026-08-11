#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import worker_api
from services.worker_api_service import WorkerApiService


class _RequestStub:
    def __init__(self, headers):
        self.headers = headers


class _InvalidJsonRequestStub:
    method = "POST"
    url = SimpleNamespace(path="/worker-api/result")

    def __init__(self):
        self.headers = {
            "content-type": "application/json",
            "content-length": "12345",
            "x-worker-id": "worker-01",
        }

    async def json(self):
        raise ValueError("invalid json")


def _client(tmp_path, monkeypatch, *, enabled: bool) -> TestClient:
    monkeypatch.setenv("SYNOPKG_PKGVAR", str(tmp_path))
    monkeypatch.setenv("AV_IMGDATA_WORKER_API_ENABLED", "1" if enabled else "0")
    worker_api._composition_for.cache_clear()
    app = FastAPI()
    app.include_router(worker_api.router)
    return TestClient(app)


def test_worker_api_router_disabled_returns_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=False)

    response = client.get("/worker-api/status")

    assert response.status_code == 404
    assert response.json()["code"] == "worker_api_disabled"


def test_worker_api_router_registers_heartbeats_and_reports_status(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=True)
    token = WorkerApiService(package_var=tmp_path).create_token()["token"]

    registered = client.post(
        "/worker-api/register",
        headers={"Authorization": "Bearer " + token, "X-Worker-Id": "worker-01"},
        json={"version": "test"},
    )
    assert registered.status_code == 200

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer " + token, "X-Worker-Id": "worker-01"},
        json={"status": "ready"},
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

    registered = client.post(
        "/worker-api/register",
        headers={"Authorization": "Bearer " + token, "X-Worker-Id": "worker-01"},
        json={"version": "test"},
    )
    assert registered.status_code == 200

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer " + token, "X-Worker-Id": "worker-01"},
        json={"status": "ready"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert custom_state.exists()
    assert not (tmp_path / "worker-api-state.json").exists()


def test_worker_api_router_rejects_invalid_token_with_shared_mapping(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, enabled=True)
    WorkerApiService(package_var=tmp_path).create_token()

    response = client.post(
        "/worker-api/heartbeat",
        headers={"Authorization": "Bearer invalid", "X-Worker-Id": "worker-01"},
        json={"status": "ready"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_worker_api_error_response_is_logged_without_sensitive_payload(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(worker_api, "_backend_debug_log", lambda event, **fields: events.append((event, fields)))

    worker_api._log_worker_api_response(
        "result",
        400,
        {"status": "error", "code": "job_claimed_by_other_worker", "message": "job_claimed_by_other_worker"},
        {
            "worker_id": "body-worker",
            "job_id": "job-123",
            "token": "secret",
            "result": {"processor_result": {"embedding": [1, 2, 3]}},
        },
        _RequestStub({"x-worker-id": "header-worker"}),
    )

    assert events == [
        (
            "worker_api_action_failed",
            {
                "action": "result",
                "status_code": 400,
                "response_status": "error",
                "response_code": "job_claimed_by_other_worker",
                "response_message": "job_claimed_by_other_worker",
                "worker_id": "header-worker",
                "job_id": "job-123",
            },
        )
    ]


def test_invalid_worker_api_json_body_is_logged_without_payload(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(worker_api, "_backend_debug_log", lambda event, **fields: events.append((event, fields)))

    body = asyncio.run(worker_api._json_body(_InvalidJsonRequestStub()))

    assert body == {}
    assert events == [
        (
            "worker_api_json_body_invalid",
            {
                "method": "POST",
                "path": "/worker-api/result",
                "content_type": "application/json",
                "content_length": "12345",
                "worker_id": "worker-01",
                "error_type": "ValueError",
            },
        )
    ]


def test_worker_api_success_response_is_not_logged(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(worker_api, "_backend_debug_log", lambda event, **fields: events.append((event, fields)))

    worker_api._log_worker_api_response(
        "result",
        200,
        {"status": "ok"},
        {"worker_id": "body-worker", "job_id": "job-123", "token": "secret"},
        _RequestStub({"x-worker-id": "header-worker"}),
    )

    assert events == []

