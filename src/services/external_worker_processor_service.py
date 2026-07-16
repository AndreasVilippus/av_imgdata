#!/usr/bin/env python3
"""Shared dispatch and result-consumption path for local and external processors.

The service owns target selection, Worker API job creation, waiting and normalized
result consumption. Domain workflows keep their existing status, findings and write
logic and only call processor-shaped adapters.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.native_face_processor_service import NativeFaceProcessorService
from services.worker_api_service import WorkerApiService
from services.worker_runtime_service import WorkerApiError, parse_time


class ExternalWorkerProcessorUnavailable(RuntimeError):
    """Raised when explicitly requested external execution cannot be completed."""


class ExternalWorkerProcessorService:
    """Create external jobs and consume results without duplicating domain writes."""

    POLICIES = {"local_only", "local_preferred", "external_preferred", "external_required"}
    FACE_DETECT_CAPABILITY = "face_native_detect"
    FACE_EMBED_CAPABILITY = "face_native_embed"
    INPUT_CAPABILITY = "input_shared_path"

    def __init__(
        self,
        worker_api: WorkerApiService,
        native_processor: NativeFaceProcessorService,
        *,
        nas_root: Path,
        path_profile: str = "photos",
        stale_after_seconds: int = 30,
        wait_timeout_seconds: int = 300,
        poll_interval_seconds: float = 0.5,
        clock: Optional[Callable[[], datetime]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ):
        self.worker_api = worker_api
        self.store = worker_api.store
        self.native_processor = native_processor
        self.nas_root = Path(nas_root).expanduser().resolve()
        self.path_profile = str(path_profile or "photos").strip() or "photos"
        self.stale_after_seconds = max(1, int(stale_after_seconds))
        self.wait_timeout_seconds = max(1, int(wait_timeout_seconds))
        self.poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        self._clock = clock
        if sleeper is not None:
            self._sleeper = sleeper

    def _sleeper(self, seconds: float) -> None:
        time.sleep(seconds)

    def execute_face_detect(
        self,
        *,
        image_path: Path,
        local_execute: Callable[[], List[Dict[str, Any]]],
        policy: str = "local_preferred",
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        source_id: str = "",
        entity_type: str = "image",
        entity_id: str = "",
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
    ) -> Dict[str, Any]:
        return self._execute_image_faces(
            capability=self.FACE_DETECT_CAPABILITY,
            job_prefix="face-detect",
            image_path=image_path,
            local_execute=local_execute,
            policy=policy,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            source_id=source_id,
            entity_type=entity_type,
            entity_id=entity_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )

    def execute_face_embed(
        self,
        *,
        image_path: Path,
        local_execute: Callable[[], List[Dict[str, Any]]],
        policy: str = "local_preferred",
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        source_id: str = "",
        entity_type: str = "image",
        entity_id: str = "",
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
    ) -> Dict[str, Any]:
        """Execute detection plus embeddings using the existing native contract."""
        return self._execute_image_faces(
            capability=self.FACE_EMBED_CAPABILITY,
            job_prefix="face-embed",
            image_path=image_path,
            local_execute=local_execute,
            policy=policy,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            source_id=source_id,
            entity_type=entity_type,
            entity_id=entity_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )

    def _execute_image_faces(
        self,
        *,
        capability: str,
        job_prefix: str,
        image_path: Path,
        local_execute: Callable[[], List[Dict[str, Any]]],
        policy: str,
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        source_id: str,
        entity_type: str,
        entity_id: str,
        det_thresh: float,
        max_num: int,
        det_size: Any,
        priority: int,
    ) -> Dict[str, Any]:
        selected_policy = str(policy or "local_preferred").strip().lower()
        if selected_policy not in self.POLICIES:
            raise ValueError("invalid_external_worker_policy")
        if selected_policy in {"local_only", "local_preferred"}:
            return {"execution_target": "local_native", "faces": local_execute(), "job_id": None}
        if not self.has_compatible_worker(capability):
            if selected_policy == "external_preferred":
                return {"execution_target": "local_native", "faces": local_execute(), "job_id": None}
            raise ExternalWorkerProcessorUnavailable("external_worker_unavailable")

        queued = self._enqueue_image_faces(
            capability=capability,
            job_prefix=job_prefix,
            image_path=image_path,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            source_id=source_id,
            entity_type=entity_type,
            entity_id=entity_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )
        job_id = str(queued["job"]["job_id"])
        faces = self.wait_and_consume_faces(job_id, capability=capability)
        return {"execution_target": "external_worker", "faces": faces, "job_id": job_id}

    def enqueue_face_detect(self, **kwargs: Any) -> Dict[str, Any]:
        return self._enqueue_image_faces(
            capability=self.FACE_DETECT_CAPABILITY,
            job_prefix="face-detect",
            **kwargs,
        )

    def enqueue_face_embed(self, **kwargs: Any) -> Dict[str, Any]:
        return self._enqueue_image_faces(
            capability=self.FACE_EMBED_CAPABILITY,
            job_prefix="face-embed",
            **kwargs,
        )

    def _enqueue_image_faces(
        self,
        *,
        capability: str,
        job_prefix: str,
        image_path: Path,
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        source_id: str = "",
        entity_type: str = "image",
        entity_id: str = "",
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
        job_id: str = "",
    ) -> Dict[str, Any]:
        identity = self._origin_identity(operation, action, mode, operation_id)
        relative_path = self.relative_input_path(image_path)
        size = list(det_size or (640, 640))
        if len(size) != 2:
            raise ValueError("invalid_det_size")
        identifier = str(job_id or f"{job_prefix}-{uuid.uuid4().hex}")
        payload = {
            "contract_version": self.native_processor.CONTRACT_VERSION,
            "input_mode": "shared_path",
            "path_profile": self.path_profile,
            "local_path": relative_path,
            "source_id": str(source_id or image_path),
            "min_confidence": float(det_thresh),
            "max_faces": int(max_num),
            "det_size": [int(size[0]), int(size[1])],
            "origin": {
                **identity,
                "entity_type": str(entity_type or "image"),
                "entity_id": str(entity_id or source_id or image_path),
            },
        }
        return self.worker_api.enqueue_job(
            job_id=identifier,
            job_type=capability,
            payload=payload,
            priority=priority,
        )

    def wait_and_consume_face_detect(self, job_id: str) -> List[Dict[str, Any]]:
        return self.wait_and_consume_faces(job_id, capability=self.FACE_DETECT_CAPABILITY)

    def wait_and_consume_face_embed(self, job_id: str) -> List[Dict[str, Any]]:
        return self.wait_and_consume_faces(job_id, capability=self.FACE_EMBED_CAPABILITY)

    def wait_and_consume_faces(self, job_id: str, *, capability: str) -> List[Dict[str, Any]]:
        self._wait_for_completed_job(job_id)
        return self.consume_faces_result(job_id, capability=capability)

    def _wait_for_completed_job(self, job_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.wait_timeout_seconds
        while True:
            job = self.get_job(job_id)
            status = str(job.get("status") or "")
            if status == "completed":
                return job
            if status == "failed":
                error = job.get("error") if isinstance(job.get("error"), dict) else {}
                raise ExternalWorkerProcessorUnavailable(
                    str(error.get("message") or error.get("code") or "external_worker_failed")
                )
            if status in {"cancelled", "expired"}:
                raise ExternalWorkerProcessorUnavailable(f"external_worker_job_{status}")
            if time.monotonic() >= deadline:
                raise ExternalWorkerProcessorUnavailable("external_worker_timeout")
            self._sleeper(self.poll_interval_seconds)

    def consume_face_detect_result(self, job_id: str) -> List[Dict[str, Any]]:
        return self.consume_faces_result(job_id, capability=self.FACE_DETECT_CAPABILITY)

    def consume_face_embed_result(self, job_id: str) -> List[Dict[str, Any]]:
        return self.consume_faces_result(job_id, capability=self.FACE_EMBED_CAPABILITY)

    def consume_faces_result(self, job_id: str, *, capability: str) -> List[Dict[str, Any]]:
        """Normalize a completed face result and mark it consumed atomically."""
        job = self.get_job(job_id)
        if str(job.get("type") or "") != capability:
            raise WorkerApiError("job_type_unsupported")
        if str(job.get("status") or "") != "completed":
            raise WorkerApiError("job_not_completed")

        already_consumed = bool(job.get("result_consumed_at"))
        stored_faces = job.get("normalized_faces") if isinstance(job.get("normalized_faces"), list) else None
        if already_consumed and stored_faces is not None:
            return [dict(face) for face in stored_faces if isinstance(face, dict)]

        worker_result = job.get("result") if isinstance(job.get("result"), dict) else {}
        processor_result = worker_result.get("processor_result") if isinstance(worker_result.get("processor_result"), dict) else {}
        if not processor_result:
            raise ExternalWorkerProcessorUnavailable("external_worker_processor_result_missing")
        faces = self.native_processor._normalize_faces(processor_result)
        now = self._now_iso()

        def mutate(state: Dict[str, Any]):
            current = state.get("jobs", {}).get(job_id)
            if not isinstance(current, dict):
                raise WorkerApiError("job_not_found")
            if current.get("result_consumed_at"):
                existing = current.get("normalized_faces")
                return existing if isinstance(existing, list) else faces
            if str(current.get("status") or "") != "completed":
                raise WorkerApiError("job_not_completed")
            current.update({
                "normalized_faces": faces,
                "result_consumed_at": now,
                "result_consumer_version": "1.0",
                "result_apply_status": "consumed",
                "updated_at": now,
            })
            return faces

        consumed = self.store.update(mutate)
        return [dict(face) for face in consumed if isinstance(face, dict)]

    def get_job(self, job_id: str) -> Dict[str, Any]:
        state = self.store.read()
        job = state.get("jobs", {}).get(str(job_id or ""))
        if not isinstance(job, dict):
            raise WorkerApiError("job_not_found")
        return dict(job)

    def has_compatible_worker(self, capability: str = FACE_DETECT_CAPABILITY) -> bool:
        expected = str(capability or self.FACE_DETECT_CAPABILITY)
        state = self.store.read()
        now = self._now()
        for raw in state.get("workers", {}).values():
            worker = raw if isinstance(raw, dict) else {}
            capabilities = {str(item) for item in worker.get("capabilities", []) if str(item)}
            if expected not in capabilities:
                continue
            metadata = worker.get("metadata") if isinstance(worker.get("metadata"), dict) else {}
            input_modes = metadata.get("input_modes", []) if isinstance(metadata.get("input_modes"), list) else []
            supports_input = self.INPUT_CAPABILITY in capabilities or "shared_path" in input_modes
            if not supports_input:
                continue
            last_seen = parse_time(worker.get("last_seen_at"))
            if (now - last_seen).total_seconds() <= self.stale_after_seconds:
                return True
        return False

    def relative_input_path(self, image_path: Path) -> str:
        source = Path(image_path).expanduser().resolve()
        try:
            relative = source.relative_to(self.nas_root)
        except ValueError as exc:
            raise ValueError("source_path_outside_path_profile") from exc
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("invalid_relative_worker_path")
        return relative.as_posix()

    @staticmethod
    def _origin_identity(operation: str, action: str, mode: str, operation_id: str) -> Dict[str, str]:
        values = {
            "operation": str(operation or "").strip(),
            "action": str(action or "").strip(),
            "mode": str(mode or "").strip(),
            "operation_id": str(operation_id or "").strip(),
        }
        if not all(values.values()):
            raise ValueError("worker_origin_identity_required")
        return values

    def _now(self) -> datetime:
        value = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _now_iso(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
