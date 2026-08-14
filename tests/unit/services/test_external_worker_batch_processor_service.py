#!/usr/bin/env python3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from services.external_worker_batch_processor_service import ExternalWorkerBatchProcessorService
from services.worker_api_service import WorkerApiService


class NativeProcessorStub:
    CONTRACT_VERSION = "1.0"

    @staticmethod
    def _normalize_batch_images(payload):
        result = payload.get("result") if isinstance(payload, dict) else {}
        images = result.get("images") if isinstance(result, dict) else []
        return [dict(item) for item in images if isinstance(item, dict)]

    @staticmethod
    def _normalize_face(face):
        return dict(face) if isinstance(face, dict) else None


class TestExternalWorkerBatchProcessorService:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.package_var = Path(self.temp_dir.name)
        self.photo_root = self.package_var / "photo"
        self.photo_root.mkdir()
        self.image_a = self.photo_root / "album" / "a.jpg"
        self.image_b = self.photo_root / "album" / "b.jpg"
        self.image_a.parent.mkdir()
        self.image_a.write_bytes(b"a")
        self.image_b.write_bytes(b"b")
        self.api = WorkerApiService(package_var=self.package_var)
        self.now = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
        self.service = ExternalWorkerBatchProcessorService(
            self.api,
            NativeProcessorStub(),
            nas_root=self.photo_root,
            clock=lambda: self.now,
            sleeper=lambda _: None,
            wait_timeout_seconds=1,
        )

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_enqueue_embed_batch_uses_relative_shared_paths(self):
        queued = self.service.enqueue_face_embed_batch(
            image_paths=[self.image_a, self.image_b],
            operation="cleanup",
            action="recognition_build_profiles",
            mode="scan",
            operation_id="op-batch-1",
            job_id="embed-batch-1",
        )

        payload = queued["job"]["payload"]
        assert queued["job"]["type"] == "face_native_embed_batch"
        assert payload["input_mode"] == "shared_path"
        assert payload["image_paths"] == ["album/a.jpg", "album/b.jpg"]
        assert payload["source_ids"] == [str(self.image_a), str(self.image_b)]
        assert payload["origin"]["operation_id"] == "op-batch-1"

    def test_completed_embed_batch_is_normalized_and_consumed(self):
        self.service.enqueue_face_embed_batch(
            image_paths=[self.image_a, self.image_b],
            operation="cleanup",
            action="recognition_build_profiles",
            mode="scan",
            operation_id="op-batch-2",
            job_id="embed-batch-2",
        )

        def complete(state):
            job = state["jobs"]["embed-batch-2"]
            job["status"] = "completed"
            job["result"] = {
                "processor_execution": "completed",
                "processor_result": {
                    "contract_version": "1.0",
                    "job_id": "embed-batch-2",
                    "type": "face_native_embed_batch",
                    "status": "completed",
                    "result": {
                        "images": [
                            {"image_path": "a.jpg", "status": "completed", "faces": [{"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}, "embedding": [1.0, 0.0]}]},
                            {"image_path": "b.jpg", "status": "completed", "faces": [{"bbox": {"x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4}, "embedding": [0.0, 1.0]}]},
                        ]
                    },
                },
            }
            return job

        self.api.store.update(complete)
        first = self.service.consume_face_batch_result(
            "embed-batch-2",
            capability=self.service.FACE_EMBED_BATCH_CAPABILITY,
            image_paths=[self.image_a, self.image_b],
        )
        second = self.service.consume_face_batch_result(
            "embed-batch-2",
            capability=self.service.FACE_EMBED_BATCH_CAPABILITY,
            image_paths=[self.image_a, self.image_b],
        )

        assert first == second
        assert first[str(self.image_a)][0]["embedding"] == [1.0, 0.0]
        assert first[str(self.image_b)][0]["embedding"] == [0.0, 1.0]
        stored = self.service.get_job("embed-batch-2")
        assert stored["result_apply_status"] == "consumed"
        assert "result" not in stored

    def test_batch_rejects_path_outside_profile(self):
        outside = self.package_var / "outside.jpg"
        outside.write_bytes(b"x")
        try:
            self.service.enqueue_face_detect_batch(
                image_paths=[self.image_a, outside],
                operation="cleanup",
                action="standardize_face_frames",
                mode="scan",
                operation_id="op-batch-3",
            )
        except ValueError as exc:
            assert str(exc) == "source_path_outside_path_profile"
        else:
            raise AssertionError("outside batch path must be rejected")
