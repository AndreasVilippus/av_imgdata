#!/usr/bin/env python3
"""Batch extension for the shared external worker processor service.

Batch dispatch stays outside domain workflows. It reuses the established target
selection, queue, waiting and result-consumption rules from
``ExternalWorkerProcessorService`` while adding the two processor-contract batch
operations.

Package and external worker are one versioned release unit. A fresh worker with a
version or capability set that differs from the package contract is incompatible;
there is no downgrade to older worker behavior.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List

from services.external_worker_processor_service import (
    ExternalWorkerProcessorService,
    ExternalWorkerProcessorUnavailable,
)
from services.worker_runtime_service import WorkerProtocol, parse_time


class ExternalWorkerBatchProcessorService(ExternalWorkerProcessorService):
    """Add face-native batch contracts without duplicating domain orchestration."""

    FACE_DETECT_BATCH_CAPABILITY = "face_native_detect_batch"
    FACE_EMBED_BATCH_CAPABILITY = "face_native_embed_batch"

    def has_compatible_worker(self, capability: str = ExternalWorkerProcessorService.FACE_DETECT_CAPABILITY) -> bool:
        """Require the external worker to match the package release contract exactly.

        No fresh worker means external execution is unavailable and callers using
        ``external_preferred`` may use the local package processor. A fresh worker
        with the wrong version or an incomplete/extra active capability set is a
        deployment error and must not silently fall back to another processor shape.
        """
        expected_capability = str(capability or self.FACE_DETECT_CAPABILITY)
        expected_capabilities = set(WorkerProtocol.CAPABILITIES)
        state = self.store.read()
        now = self._now()
        fresh_workers: List[Dict[str, Any]] = []

        for raw in state.get("workers", {}).values():
            worker = raw if isinstance(raw, dict) else {}
            last_seen = parse_time(worker.get("last_seen_at"))
            if (now - last_seen).total_seconds() <= self.stale_after_seconds:
                fresh_workers.append(worker)

        if not fresh_workers:
            return False

        for worker in fresh_workers:
            version = str(worker.get("version") or "").strip()
            capabilities = {str(item) for item in worker.get("capabilities", []) if str(item)}
            metadata = worker.get("metadata") if isinstance(worker.get("metadata"), dict) else {}
            input_modes = metadata.get("input_modes", []) if isinstance(metadata.get("input_modes"), list) else []
            contract_matches = (
                version == WorkerProtocol.WORKER_VERSION
                and capabilities == expected_capabilities
            )
            if not contract_matches:
                continue
            if expected_capability not in capabilities:
                continue
            if expected_capability not in self.VECTOR_CAPABILITIES and "shared_path" not in input_modes:
                continue
            return True

        self._debug_log(
            "external_worker_contract_mismatch",
            required_version=WorkerProtocol.WORKER_VERSION,
            required_capabilities=sorted(expected_capabilities),
            requested_capability=expected_capability,
            fresh_workers=len(fresh_workers),
        )
        raise ExternalWorkerProcessorUnavailable("external_worker_contract_mismatch")

    def execute_face_detect_batch(
        self,
        *,
        image_paths: List[Path],
        local_execute: Callable[[], Dict[str, List[Dict[str, Any]]]],
        policy: str = "local_preferred",
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
    ) -> Dict[str, Any]:
        return self._execute_face_batch(
            capability=self.FACE_DETECT_BATCH_CAPABILITY,
            job_prefix="face-detect-batch",
            image_paths=image_paths,
            local_execute=local_execute,
            policy=policy,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )

    def execute_face_embed_batch(
        self,
        *,
        image_paths: List[Path],
        local_execute: Callable[[], Dict[str, List[Dict[str, Any]]]],
        policy: str = "local_preferred",
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
    ) -> Dict[str, Any]:
        return self._execute_face_batch(
            capability=self.FACE_EMBED_BATCH_CAPABILITY,
            job_prefix="face-embed-batch",
            image_paths=image_paths,
            local_execute=local_execute,
            policy=policy,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )

    def enqueue_face_detect_batch(self, **kwargs: Any) -> Dict[str, Any]:
        return self._enqueue_face_batch(
            capability=self.FACE_DETECT_BATCH_CAPABILITY,
            job_prefix="face-detect-batch",
            **kwargs,
        )

    def enqueue_face_embed_batch(self, **kwargs: Any) -> Dict[str, Any]:
        return self._enqueue_face_batch(
            capability=self.FACE_EMBED_BATCH_CAPABILITY,
            job_prefix="face-embed-batch",
            **kwargs,
        )

    def start_face_embed_batch(self, **kwargs: Any) -> Dict[str, Any]:
        return self._start_face_batch(
            capability=self.FACE_EMBED_BATCH_CAPABILITY,
            job_prefix="face-embed-batch",
            **kwargs,
        )

    def start_face_detect_batch(self, **kwargs: Any) -> Dict[str, Any]:
        return self._start_face_batch(
            capability=self.FACE_DETECT_BATCH_CAPABILITY,
            job_prefix="face-detect-batch",
            **kwargs,
        )

    def _start_face_batch(
        self,
        *,
        capability: str,
        job_prefix: str,
        image_paths: List[Path],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        queued = self._enqueue_face_batch(
            capability=capability,
            job_prefix=job_prefix,
            image_paths=paths,
            **kwargs,
        )
        job = queued.get("job") if isinstance(queued.get("job"), dict) else {}
        return {
            "execution_target": "external_worker",
            "job_id": str(job.get("job_id") or ""),
            "capability": capability,
            "image_paths": paths,
        }

    def finish_face_batch(self, handle: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        job_id = str(handle.get("job_id") or "")
        capability = str(handle.get("capability") or "")
        image_paths = [Path(path) for path in list(handle.get("image_paths") or [])]
        self._wait_for_completed_job(job_id)
        return self.consume_face_batch_result(
            job_id,
            capability=capability,
            image_paths=image_paths,
        )

    def completed_face_batch_jobs(
        self,
        *,
        operation_id: str,
        capability: str = FACE_EMBED_BATCH_CAPABILITY,
        action: str = "",
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        origin_filter: Dict[str, Any] = {"operation_id": operation_id}
        if action:
            origin_filter["action"] = action
        return self.worker_api.list_jobs(
            status=["completed"],
            origin_filter=origin_filter,
            job_type=capability,
            limit=limit,
        )

    def _execute_face_batch(
        self,
        *,
        capability: str,
        job_prefix: str,
        image_paths: List[Path],
        local_execute: Callable[[], Dict[str, List[Dict[str, Any]]]],
        policy: str,
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        det_thresh: float,
        max_num: int,
        det_size: Any,
        priority: int,
    ) -> Dict[str, Any]:
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        if not paths:
            return {"execution_target": "local_native", "images": {}, "job_id": None}

        selected_policy = self._selected_policy(policy)
        if selected_policy in {"local_only", "local_preferred"}:
            self._debug_log(
                "external_worker_dispatch_local",
                capability=capability,
                policy=selected_policy,
                reason="policy",
                images_count=len(paths),
            )
            return {"execution_target": "local_native", "images": local_execute(), "job_id": None}

        if not self.has_compatible_worker(capability):
            if selected_policy == "external_preferred":
                self._debug_log(
                    "external_worker_dispatch_local",
                    capability=capability,
                    policy=selected_policy,
                    reason="compatible_worker_unavailable",
                    images_count=len(paths),
                )
                return {"execution_target": "local_native", "images": local_execute(), "job_id": None}
            raise ExternalWorkerProcessorUnavailable("external_worker_unavailable")

        queued = self._enqueue_face_batch(
            capability=capability,
            job_prefix=job_prefix,
            image_paths=paths,
            operation=operation,
            action=action,
            mode=mode,
            operation_id=operation_id,
            det_thresh=det_thresh,
            max_num=max_num,
            det_size=det_size,
            priority=priority,
        )
        job_id = str(queued["job"]["job_id"])
        self._debug_log(
            "external_worker_dispatch_enqueued",
            capability=capability,
            job_id=job_id,
            action=action,
            operation=operation,
            mode=mode,
            images_count=len(paths),
        )
        images = self.wait_and_consume_face_batch(job_id, capability=capability, image_paths=paths)
        self._debug_log(
            "external_worker_dispatch_completed",
            capability=capability,
            job_id=job_id,
            images_count=len(images),
            faces_count=sum(len(faces) for faces in images.values()),
        )
        return {"execution_target": "external_worker", "images": images, "job_id": job_id}

    def _enqueue_face_batch(
        self,
        *,
        capability: str,
        job_prefix: str,
        image_paths: List[Path],
        operation: str,
        action: str,
        mode: str,
        operation_id: str,
        det_thresh: float = 0.5,
        max_num: int = 0,
        det_size: Any = (640, 640),
        priority: int = 100,
        job_id: str = "",
    ) -> Dict[str, Any]:
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        if not paths:
            raise ValueError("worker_batch_image_paths_required")
        size = list(det_size or (640, 640))
        if len(size) != 2:
            raise ValueError("invalid_det_size")
        identity = self._origin_identity(operation, action, mode, operation_id)
        identifier = str(job_id or f"{job_prefix}-{uuid.uuid4().hex}")
        relative_paths = [self.relative_input_path(path) for path in paths]
        payload = {
            "contract_version": self.native_processor.CONTRACT_VERSION,
            "input_mode": "shared_path",
            "path_profile": self.path_profile,
            "image_paths": relative_paths,
            "source_ids": [str(path) for path in paths],
            "min_confidence": float(det_thresh),
            "max_faces": int(max_num),
            "det_size": [int(size[0]), int(size[1])],
            "origin": {
                **identity,
                "entity_type": "image_batch",
                "entity_id": identifier,
            },
        }
        return self.worker_api.enqueue_job(
            job_id=identifier,
            job_type=capability,
            payload=payload,
            priority=priority,
        )

    def wait_and_consume_face_batch(
        self,
        job_id: str,
        *,
        capability: str,
        image_paths: List[Path],
    ) -> Dict[str, List[Dict[str, Any]]]:
        self._wait_for_completed_job(job_id)
        return self.consume_face_batch_result(
            job_id,
            capability=capability,
            image_paths=image_paths,
        )

    def consume_face_batch_result(
        self,
        job_id: str,
        *,
        capability: str,
        image_paths: List[Path],
    ) -> Dict[str, List[Dict[str, Any]]]:
        job = self._completed_job(job_id, capability)
        stored = job.get("normalized_batch_images")
        if job.get("result_consumed_at") and isinstance(stored, dict):
            return self._copy_batch_result(stored)

        processor_result = self._processor_result(job)
        raw_images = self.native_processor._normalize_batch_images(processor_result)
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        normalized: Dict[str, List[Dict[str, Any]]] = {}
        for index, path in enumerate(paths):
            item = raw_images[index] if index < len(raw_images) and isinstance(raw_images[index], dict) else {}
            faces = item.get("faces") if isinstance(item.get("faces"), list) else []
            normalized[str(path)] = [
                face
                for face in (self.native_processor._normalize_face(raw) for raw in faces)
                if face is not None
            ]

        consumed = self._store_consumed(job_id, "normalized_batch_images", normalized)
        return self._copy_batch_result(consumed if isinstance(consumed, dict) else {})

    @staticmethod
    def _copy_batch_result(value: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        return {
            str(path): [dict(face) for face in faces if isinstance(face, dict)]
            for path, faces in value.items()
            if isinstance(faces, list)
        }
