#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import sys
import tempfile
import threading
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
            version="0.10.1",
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
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:03:00Z")
        self.assertEqual(state["workers"]["worker-01"]["status"], "ready")

        heartbeat = service.heartbeat(
            token=token,
            worker_id="worker-01",
            status="ready",
            capabilities=["face_native_embed"],
        )
        state = service.store.read()
        self.assertEqual(heartbeat["status"], "ok")
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:04:00Z")

    def test_concurrent_claims_cannot_claim_same_job_twice(self):
        token_1 = self.service.create_token(token_id="worker-1")["token"]
        token_2 = self.service.create_token(token_id="worker-2")["token"]
        self.service.register_worker(
            token=token_1,
            worker_id="worker-1",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.register_worker(
            token=token_2,
            worker_id="worker-2",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        barrier = threading.Barrier(2)

        def claim(token, worker_id):
            barrier.wait(timeout=5)
            return self.service.claim_job(
                token=token,
                worker_id=worker_id,
                capabilities=["face_native_embed"],
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda args: claim(*args), [(token_1, "worker-1"), (token_2, "worker-2")]))

        statuses = sorted(result["status"] for result in results)
        claimed = [result["job"] for result in results if result["status"] == "claimed"]
        state = self.service.store.read()

        self.assertEqual(statuses, ["claimed", "empty"])
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["job_id"], "job-1")
        self.assertEqual(state["jobs"]["job-1"]["status"], "claimed")
        self.assertIn(state["jobs"]["job-1"]["claimed_by"], {"worker-1", "worker-2"})

    def test_concurrent_enrollment_redemption_issues_single_bound_token(self):
        from services.worker_provisioning_service import WorkerProvisioningService

        provisioning = WorkerProvisioningService(package_var=self.package_var, state_store=self.service.store)
        enrollment = provisioning.create_enrollment(enrollment_id="enroll-1")
        barrier = threading.Barrier(2)

        def redeem(worker_id):
            barrier.wait(timeout=5)
            try:
                return provisioning.redeem_enrollment(
                    enrollment_code=enrollment["enrollment_code"],
                    worker_id=worker_id,
                )
            except WorkerApiError as exc:
                return {"status": "error", "code": exc.code, "worker_id": worker_id}

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(redeem, ["worker-1", "worker-2"]))

        enrolled = [result for result in results if result["status"] == "enrolled"]
        rejected = [result for result in results if result["status"] == "error"]
        state = self.service.store.read()

        self.assertEqual(len(enrolled), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["code"], "enrollment_code_used")
        self.assertEqual(len(state["tokens"]), 2)
        enrollment_state = state["enrollments"]["enroll-1"]
        self.assertEqual(enrollment_state["worker_id"], enrolled[0]["worker_id"])
        self.assertTrue(enrollment_state["used_at"])
        bound_tokens = [
            entry for token_id, entry in state["tokens"].items()
            if token_id == enrolled[0]["token_id"]
        ]
        self.assertEqual(bound_tokens[0]["worker_id"], enrolled[0]["worker_id"])

    def test_enrollment_redemption_write_failure_leaves_code_unused_and_no_new_token(self):
        from services.worker_provisioning_service import WorkerProvisioningService

        provisioning = WorkerProvisioningService(package_var=self.package_var, state_store=self.service.store)
        enrollment = provisioning.create_enrollment(enrollment_id="enroll-1")
        original_token_ids = set(self.service.store.read()["tokens"])
        original_json_dumps = self.service.store._json_dumps
        calls = {"count": 0}

        def fail_after_transition(value):
            calls["count"] += 1
            if calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return original_json_dumps(value)

        self.service.store._json_dumps = fail_after_transition
        with self.assertRaises(WorkerApiError) as ctx:
            provisioning.redeem_enrollment(
                enrollment_code=enrollment["enrollment_code"],
                worker_id="worker-1",
            )
        self.service.store._json_dumps = original_json_dumps

        state = self.service.store.read()
        redeemed = provisioning.redeem_enrollment(
            enrollment_code=enrollment["enrollment_code"],
            worker_id="worker-1",
        )

        self.assertEqual(ctx.exception.code, "state_write_failed")
        self.assertEqual(set(state["tokens"]), original_token_ids)
        self.assertIsNone(state["enrollments"]["enroll-1"]["used_at"])
        self.assertIsNone(state["enrollments"]["enroll-1"]["worker_id"])
        self.assertEqual(redeemed["status"], "enrolled")

    def test_restart_preserves_queued_claimed_and_unconsumed_completed_jobs(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(
            job_id="completed",
            job_type="face_native_embed",
            payload={"source": "completed"},
            priority=10,
        )
        self.service.enqueue_job(
            job_id="claimed",
            job_type="face_native_embed",
            payload={"source": "claimed"},
            priority=20,
        )
        self.service.enqueue_job(
            job_id="queued",
            job_type="face_native_embed",
            payload={"source": "queued"},
            priority=30,
        )
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])
        self.service.record_result(
            token=self.token,
            worker_id="worker-01",
            job_id="completed",
            result={"faces": []},
        )
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])

        restarted = WorkerApiService(package_var=self.package_var)
        state = restarted.store.read()
        status = restarted.status()
        listed = restarted.list_jobs(status=["queued", "claimed", "completed"])
        by_id = {job["job_id"]: job for job in listed}

        self.assertEqual(state["jobs"]["queued"]["status"], "queued")
        self.assertEqual(state["jobs"]["claimed"]["status"], "claimed")
        self.assertEqual(state["jobs"]["completed"]["status"], "completed")
        self.assertNotIn("result_consumed_at", state["jobs"]["completed"])
        self.assertEqual(by_id["queued"]["status"], "queued")
        self.assertEqual(by_id["claimed"]["status"], "claimed")
        self.assertEqual(by_id["completed"]["result"], {"faces": []})
        self.assertEqual(status["jobs"]["by_status"], {"completed": 1, "claimed": 1, "queued": 1})

    def test_restart_preserves_claimed_job_without_requeueing(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="claimed", job_type="face_native_embed", payload={})
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])

        restarted = WorkerApiService(package_var=self.package_var)
        state = restarted.store.read()
        empty = restarted.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )

        self.assertEqual(state["jobs"]["claimed"]["status"], "claimed")
        self.assertEqual(state["jobs"]["claimed"]["claimed_by"], "worker-01")
        self.assertEqual(empty["status"], "empty")

    def test_revoked_token_is_rejected_during_active_worker_lifecycle(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])

        state = self.service.store.read()
        state["tokens"]["test-worker"]["revoked"] = True
        self.service.store.write(state)

        with self.assertRaises(WorkerApiError) as heartbeat_ctx:
            self.service.heartbeat(token=self.token, worker_id="worker-01", status="ready")
        with self.assertRaises(WorkerApiError) as result_ctx:
            self.service.record_result(
                token=self.token,
                worker_id="worker-01",
                job_id="job-1",
                result={"faces": []},
            )

        self.assertEqual(heartbeat_ctx.exception.code, "unauthorized")
        self.assertEqual(result_ctx.exception.code, "unauthorized")
        self.assertEqual(self.service.store.read()["jobs"]["job-1"]["status"], "claimed")

    def test_job_result_write_failure_rolls_back_job_and_worker_transition(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])
        original_json_dumps = self.service.store._json_dumps
        calls = {"count": 0}

        def fail_after_transition(value):
            calls["count"] += 1
            if calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return original_json_dumps(value)

        self.service.store._json_dumps = fail_after_transition
        with self.assertRaises(WorkerApiError) as ctx:
            self.service.record_result(
                token=self.token,
                worker_id="worker-01",
                job_id="job-1",
                result={"faces": []},
            )
        self.service.store._json_dumps = original_json_dumps
        state = self.service.store.read()

        self.assertEqual(ctx.exception.code, "state_write_failed")
        self.assertEqual(state["jobs"]["job-1"]["status"], "claimed")
        self.assertNotIn("result", state["jobs"]["job-1"])
        self.assertNotIn("finished_at", state["jobs"]["job-1"])
        self.assertEqual(state["workers"]["worker-01"]["status"], "processing")

    def test_package_upgrade_keeps_existing_sqlite_worker_runtime(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})

        upgraded = WorkerApiService(package_var=self.package_var)
        heartbeat = upgraded.heartbeat(token=self.token, worker_id="worker-01", status="ready")
        claimed = upgraded.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        state = upgraded.store.read()

        self.assertEqual(heartbeat["status"], "ok")
        self.assertEqual(claimed["status"], "claimed")
        self.assertIn("test-worker", state["tokens"])
        self.assertIn("worker-01", state["workers"])
        self.assertEqual(state["jobs"]["job-1"]["status"], "claimed")

    def test_claim_respects_capabilities(self):
        self.service.enqueue_job(job_id="job-1", job_type="face_native_detect", payload={})
        claimed = self.service.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        self.assertEqual(claimed["status"], "empty")

    def test_empty_claim_does_not_write_worker_state(self):
        calls = []
        original_write = self.service.store.write

        def write_spy(state):
            calls.append(True)
            return original_write(state)

        self.service.store.write = write_spy
        claimed = self.service.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )

        self.assertEqual(claimed["status"], "empty")
        self.assertEqual(calls, [])

    def test_repeated_unchanged_heartbeat_is_not_persisted_until_interval(self):
        clock = MutableClock(datetime(2026, 8, 9, 18, 0, 0, tzinfo=timezone.utc))
        service = WorkerApiService(package_var=self.package_var, clock=clock)
        token = service.create_token(token_id="heartbeat-worker")["token"]
        service.register_worker(
            token=token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        calls = []
        original_write = service.store.write

        def write_spy(state):
            calls.append(True)
            return original_write(state)

        service.store.write = write_spy
        clock.value = datetime(2026, 8, 9, 18, 0, 5, tzinfo=timezone.utc)
        heartbeat = service.heartbeat(
            token=token,
            worker_id="worker-01",
            status="registered",
            capabilities=["face_native_embed"],
        )
        state = service.store.read()

        self.assertEqual(heartbeat["worker"]["last_seen_at"], "2026-08-09T18:00:05Z")
        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:00:00Z")
        self.assertEqual(calls, [])

        clock.value = datetime(2026, 8, 9, 18, 0, 11, tzinfo=timezone.utc)
        service.heartbeat(
            token=token,
            worker_id="worker-01",
            status="registered",
            capabilities=["face_native_embed"],
        )
        state = service.store.read()

        self.assertEqual(state["workers"]["worker-01"]["last_seen_at"], "2026-08-09T18:00:11Z")
        self.assertEqual(calls, [True])

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

    def test_status_counts_batch_jobs_and_items_separately(self):
        self.service.enqueue_job(
            job_id="batch-1",
            job_type="face_native_embed_batch",
            payload={
                "image_paths": ["a.jpg", "b.jpg", "c.jpg"],
                "origin": {"operation_id": "op-1", "action": "recognition_build_profiles"},
            },
        )
        self.service.enqueue_job(
            job_id="single-1",
            job_type="face_native_embed",
            payload={"local_path": "d.jpg", "origin": {"operation_id": "op-1"}},
        )

        status = self.service.status()

        self.assertEqual(status["jobs"]["by_status"]["queued"], 2)
        self.assertEqual(status["items"]["by_status"]["queued"], 4)

    def test_list_and_cancel_jobs_by_origin(self):
        self.service.enqueue_job(
            job_id="op-job-1",
            job_type="face_native_embed_batch",
            payload={"image_paths": ["a.jpg", "b.jpg"], "origin": {"operation_id": "op-1", "action": "scan"}},
        )
        self.service.enqueue_job(
            job_id="other-job-1",
            job_type="face_native_embed_batch",
            payload={"image_paths": ["c.jpg"], "origin": {"operation_id": "op-2", "action": "scan"}},
        )

        listed = self.service.list_jobs(
            status=["queued"],
            origin_filter={"operation_id": "op-1"},
        )
        cancelled = self.service.cancel_jobs_by_origin(origin_filter={"operation_id": "op-1"})
        state = self.service.store.read()

        self.assertEqual([job["job_id"] for job in listed], ["op-job-1"])
        self.assertEqual(cancelled["cancelled_jobs"], 1)
        self.assertEqual(state["jobs"]["op-job-1"]["status"], "cancelled")
        self.assertEqual(state["jobs"]["other-job-1"]["status"], "queued")

    def test_cancelled_job_rejects_late_worker_result(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(
            job_id="op-job-1",
            job_type="face_native_embed",
            payload={"origin": {"operation_id": "op-1"}},
        )
        self.service.claim_job(
            token=self.token,
            worker_id="worker-01",
            capabilities=["face_native_embed"],
        )
        self.service.cancel_jobs_by_origin(origin_filter={"operation_id": "op-1"})

        with self.assertRaises(WorkerApiError) as ctx:
            self.service.record_result(
                token=self.token,
                worker_id="worker-01",
                job_id="op-job-1",
                result={"faces": []},
            )

        self.assertEqual(ctx.exception.code, "job_cancelled")

    def test_enqueue_prunes_old_terminal_jobs_and_used_enrollments(self):
        clock = MutableClock(datetime(2026, 8, 9, 18, 0, 0, tzinfo=timezone.utc))
        service = WorkerApiService(package_var=self.package_var, clock=clock)
        old = (clock.value - timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        service.store.write({
            "schema_version": 2,
            "tokens": {},
            "workers": {},
            "jobs": {
                "old-failed": {"job_id": "old-failed", "type": "face_native_embed", "status": "failed", "updated_at": old},
                "old-cancelled": {"job_id": "old-cancelled", "type": "face_native_embed", "status": "cancelled", "updated_at": old},
                "active": {"job_id": "active", "type": "face_native_embed", "status": "queued", "updated_at": old},
            },
            "enrollments": {
                "used": {"created_at": old, "expires_at": old, "used_at": old, "worker_id": "worker-01"},
            },
        })

        service.enqueue_job(job_id="new", job_type="face_native_embed", payload={})
        state = service.store.read()

        self.assertNotIn("old-failed", state["jobs"])
        self.assertNotIn("old-cancelled", state["jobs"])
        self.assertIn("active", state["jobs"])
        self.assertIn("new", state["jobs"])
        self.assertEqual(state["enrollments"], {})

    def test_record_failure_stores_compact_error(self):
        self.service.register_worker(
            token=self.token,
            worker_id="worker-01",
            version="0.10.1",
            capabilities=["face_native_embed"],
        )
        self.service.enqueue_job(job_id="job-1", job_type="face_native_embed", payload={})
        self.service.claim_job(token=self.token, worker_id="worker-01", capabilities=["face_native_embed"])

        result = self.service.record_failure(
            token=self.token,
            worker_id="worker-01",
            job_id="job-1",
            error={
                "code": "processor_failed",
                "message": "x" * 2000,
                "processor_result": {
                    "timing_ms": {"total": 1.2, "batch_size": 8, "failed_images": 8},
                    "result": {"images": [{"faces": []} for _ in range(100)]},
                },
            },
        )

        error = result["job"]["error"]
        self.assertEqual(error["code"], "processor_failed")
        self.assertEqual(len(error["message"]), 1000)
        self.assertEqual(error["timing_ms"], {"total": 1.2, "batch_size": 8, "failed_images": 8})
        self.assertNotIn("processor_result", error)


if __name__ == "__main__":
    unittest.main()
