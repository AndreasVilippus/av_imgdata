#!/usr/bin/env python3
from datetime import datetime, timezone
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.worker_api_endpoints import handle_worker_api_request
from services.worker_api_service import WorkerApiError, WorkerApiService


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class TestWorkerApiService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.package_var = Path(self.temp_dir.name)
        self.service = WorkerApiService(package_var=self.package_var)
        self.token = self.service.create_token(token_id="test-worker")["token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_register_heartbeat_claim_result_flow(self):
        registered = self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.1.0-phase-d",
            capabilities=["face_native_embed"],
        )
        self.assertEqual(registered["status"], "registered")

        heartbeat = self.service.heartbeat(token=self.token, worker_id="worker-01", status="ready")
        self.assertEqual(heartbeat["status"], "ok")

        queued = self.service.enqueue_job(
            job_id="job-1",
            job_type="face_native_embed",
            payload={"image_path": "/tmp/test.jpg"},
        )
        self.assertEqual(queued["status"], "queued")

        claimed = self.service.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(claimed["job"]["job_id"], "job-1")

        completed = self.service.record_result(
            token=self.token,
            worker_id="worker-01",
            job_id="job-1",
            result={"faces": []},
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["job"]["result"], {"faces": []})

    def test_claim_and_result_refresh_worker_last_seen(self):
        clock = MutableClock(datetime(2026, 8, 9, 18, 0, 0, tzinfo=timezone.utc))
        service = WorkerApiService(package_var=self.package_var, clock=clock)
        token = service.create_token(token_id="fresh-worker")["token"]
        service.register_worker(
            token=token,
            worker_id="worker-01",
            version="0.10.0",
            capabilities=["face_native_embed"],
        )

        clock.value = datetime(2026, 8, 9, 18, 1, 0, tzinfo=timezone.utc)
        service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        claimed = service.claim_job(
            token=token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        state = service.store.read()
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:01:00Z")
        self.assertEqual(state["workers"]["worker-01"]["status"], "processing")

        clock.value = datetime(2026, 8, 9, 18, 3, 0, tzinfo=timezone.utc)
        service.record_result(
            token=token,
            worker_id="worker-01",
            job_id="job-1",
            result={"faces": []},
        )
        state = service.store.read()
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:03:00Z")
        self.assertEqual(state["workers"]["worker-01"]["status"], "ready")

        clock.value = datetime(2026, 8, 9, 18, 4, 0, tzinfo=timezone.utc)
        empty = service.claim_job(
            token=token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        state = service.store.read()
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:04:00Z")
        self.assertEqual(state["workers"]["worker-01"]["status"], "ready")

    def test_claim_respects_capabilities(self):
        self.service.enqueue_job(job_id="job-1", job_type="face_native_detect", payload={})
        claimed = self.service.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        self.assertEqual(claimed["status"], "empty")

    def test_runtime_capability_is_not_enqueueable_as_processor_job(self):
        with self.assertRaises(WorkerApiError) as ctx:
            self.service.enqueue_job(
                job_id="warm-1",
                job_type="warm_processor_worker",
                payload={},
            )
        self.assertEqual(ctx.exception.code, "job_type_unsupported")

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(WorkerApiError) as ctx:
            self.service.heartbeat(token="not-the-issued-token", worker_id="worker-01")
        self.assertEqual(ctx.exception.code, "unauthorized")

    def test_endpoint_adapter_uses_authorization_header(self):
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        status, payload = handle_worker_api_request(
            "claim",
            headers={"Authorization": "Bearer " + self.token},
            body={"worker_id": "worker-01", "capabilities": ["face_native_embed"]},
            package_var=self.package_var,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "claimed")


if __name__ == "__main__":
    unittest.main()
