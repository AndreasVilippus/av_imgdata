#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

PROJECT_DIR = Path(__file__).resolve().parents[3]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(method: str, url: str, payload: Dict[str, Any] | None = None, token: str = "") -> Tuple[int, Dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_worker_api_http_router_lifecycle(tmp_path: Path) -> None:
    package_var = tmp_path / "var"
    token_tool = PROJECT_DIR / "tools" / "worker-api-store.py"
    created = subprocess.run(
        [sys.executable, str(token_tool), "--package-var", str(package_var), "create-token"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    token = json.loads(created.stdout)["token"]

    port = free_port()
    router = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_DIR / "tools" / "worker-api-http-router.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--package-var",
            str(package_var),
            "--quiet",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert router.stdout is not None
        line = router.stdout.readline().strip()
        if not line:
            try:
                _, stderr = router.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                router.kill()
                _, stderr = router.communicate(timeout=5)
            raise AssertionError(f"worker api router did not start: {stderr.strip()}")
        assert json.loads(line)["status"] == "listening"
        base_url = f"http://127.0.0.1:{port}/worker-api"

        status, payload = request(
            "POST",
            base_url + "/register",
            {"worker_id": "worker-01", "version": "test"},
            token,
        )
        assert status == 200
        assert payload["status"] == "registered"

        status, payload = request("POST", base_url + "/heartbeat", {"worker_id": "worker-01", "status": "ready"}, token)
        assert status == 200
        assert payload["status"] == "ok"

        subprocess.run(
            [
                sys.executable,
                str(token_tool),
                "--package-var",
                str(package_var),
                "enqueue",
                "--job-id",
                "job-1",
                "--type",
                "face_native_detect",
                "--payload",
                '{"local_path":"tests/images/test_raw.jpg"}',
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        status, payload = request(
            "POST",
            base_url + "/claim",
            {"worker_id": "worker-01", "capabilities": ["face_native_detect"]},
            token,
        )
        assert status == 200
        assert payload["status"] == "claimed"
        assert payload["job"]["job_id"] == "job-1"

        status, payload = request("GET", base_url + "/status")
        assert status == 200
        assert payload["status"] == "ok"
        assert payload["service"]["jobs"]["by_status"]["claimed"] == 1
    finally:
        router.terminate()
        try:
            router.wait(timeout=5)
        except subprocess.TimeoutExpired:
            router.kill()
            router.wait(timeout=5)
