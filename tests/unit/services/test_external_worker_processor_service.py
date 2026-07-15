#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.external_worker_processor_service import (
    ExternalWorkerProcessorService,
    ExternalWorkerProcessorUnavailable,
)
from services.worker_api_service import WorkerApiService


class NativeProcessorStub:
    CONTRACT_VERSION = "1.0"

    @staticmethod
    def _normalize_faces(payload):
        if payload.get("status") != "completed":
            raise RuntimeError("processor failed")
        faces = payload.get("result", {}).get("faces", [])
        return [dict(face) for face in faces]


class TestExternalWorkerProcessorService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.package_var = Path(self.temp_dir.name)
        self.photo_root = self.package_var / "photo"
        self.photo_root.mkdir()
        self.image_path = self.photo_root / "2026" / "test.heic"
        self.image_path.parent.mkdir()
        self.image_path.write_bytes(b"test")
        self.api = WorkerApiService(package_var=self.package_var)
        self.now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        self.service = ExternalWorkerProcessorService(
            self.api,
            NativeProcessorStub(),
            nas_root=self.photo_root,
            clock=lambda: self.now,
            sleeper=lambda _: None,
            wait_timeout_seconds=1,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_local_preferred_preserves_local_execution(self):
        calls = []
        result = self.service.execute_face_detect(
            image_path=self.image_path,
            local_execute=lambda: calls.append("local") or [{"bbox": {}}],
            policy="local_preferred",
            operation="face_match",
            action="detect",
            mode="scan",
            operation_id="op-1",
        )
        self.assertEqual(calls, ["local"])
        self.assertEqual(result["execution_target"], "local_native")
        self.assertIsNone(result["job_id"])

    def test_enqueue_uses_relative_shared_path_and_status_identity(self):
        queued = self.service.enqueue_face_detect(
            image_path=self.image_path,
            operation="face_match",
            action="detect",
            mode="scan",
            operation_id="op-2",
            entity_type="photo",
            entity_id="42",
            job_id="job-1",
        )
        payload = queued["job"]["payload"]
        self.assertEqual(payload["local_path"], "2026/test.heic")
        self.assertEqual(payload["input_mode"], "shared_path")
        self.assertEqual(payload["origin"]["operation"], "face_match")
        self.assertEqual(payload["origin"]["operation_id"], "op-2")
        self.assertEqual(payload["origin"]["entity_id"], "42")

    def test_external_required_rejects_missing_worker_without_local_fallback(self):
        calls = []
        with self.assertRaises(ExternalWorkerProcessorUnavailable):
            self.service.execute_face_detect(
                image_path=self.image_path,
                local_execute=lambda: calls.append("local") or [],
                policy="external_required",
                operation="face_match",
                action="detect",
                mode="scan",
                operation_id="op-3",
            )
        self.assertEqual(calls, [])

    def test_completed_result_is_normalized_and_consumed_idempotently(self):
        self.service.enqueue_face_detect(
            image_path=self.image_path,
            operation="face_match",
            action="detect",
            mode="scan",
            operation_id="op-4",
            job_id="job-2",
        )

        def complete(state):
            job = state["jobs"]["job-2"]
            job["status"] = "completed"
            job["result"] = {
                "processor_execution": "completed",
                "processor_result": {
                    "status": "completed",
                    "result": {"faces": [{"bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}]},
                },
            }
            return job

        self.api.store.update(complete)
        first = self.service.consume_face_detect_result("job-2")
        second = self.service.consume_face_detect_result("job-2")
        self.assertEqual(first, second)
        stored = self.service.get_job("job-2")
        self.assertEqual(stored["result_apply_status"], "consumed")
        self.assertEqual(stored["result_consumer_version"], "1.0")
        self.assertTrue(stored["result_consumed_at"])

    def test_source_outside_profile_is_rejected(self):
        outside = self.package_var / "outside.heic"
        outside.write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "source_path_outside_path_profile"):
            self.service.relative_input_path(outside)


if __name__ == "__main__":
    unittest.main()
