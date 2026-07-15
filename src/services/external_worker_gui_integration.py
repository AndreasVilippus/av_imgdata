#!/usr/bin/env python3
"""Install external-worker dispatch into existing GUI-driven face workflows.

The integration deliberately wraps the established detector boundary instead of
copying cleanup, status, findings, or write logic.  A compatible external worker
is preferred when the Worker API is enabled; otherwise the existing local native
detector remains the fallback.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List

from services.external_worker_processor_service import (
    ExternalWorkerProcessorUnavailable,
)
from services.face_frame_standardization_service import FaceFrameStandardizationService
from services.worker_api_composition_service import WorkerApiCompositionService


class ExternalWorkerFaceDetectorAdapter:
    """Expose the existing ``detect(Path)`` boundary with external dispatch."""

    def __init__(
        self,
        *,
        options: Dict[str, Any],
        local_detector_factory: Callable[[], Any],
        composition_factory: Callable[[], WorkerApiCompositionService] = WorkerApiCompositionService,
    ):
        self.options = dict(options or {})
        self.local_detector_factory = local_detector_factory
        self.composition_factory = composition_factory
        self._local_detector = None

    def prepare(self) -> None:
        """Preparation stays lazy so an external-only run need not load DSM models."""

    def detect(self, image_path: Path) -> List[Dict[str, Any]]:
        source = Path(image_path).expanduser().resolve()
        composition = self.composition_factory()
        if not composition.enabled():
            return self._detect_local(source)

        try:
            processor = composition.external_face_processor(nas_root=self._photos_root(source))
            result = processor.execute_face_detect(
                image_path=source,
                local_execute=lambda: self._detect_local(source),
                policy="external_preferred",
                operation="cleanup",
                action=FaceFrameStandardizationService.ACTION,
                mode="scan",
                operation_id=f"cleanup-face-frame-detect-{uuid.uuid4().hex}",
                source_id=str(source),
                entity_type="image",
                entity_id=str(source),
                det_thresh=float(self.options.get("det_thresh", 0.5)),
                max_num=int(self.options.get("max_num", 0)),
                det_size=self.options.get("det_size") or [640, 640],
            )
            faces = result.get("faces") if isinstance(result, dict) else []
            return [dict(face) for face in faces if isinstance(face, dict)]
        except ExternalWorkerProcessorUnavailable:
            # Availability can change between the compatibility check and claim.
            # No local fallback is performed after a job was enqueued by the shared
            # dispatcher; before enqueue, external_preferred already falls back.
            raise

    def _detect_local(self, source: Path) -> List[Dict[str, Any]]:
        if self._local_detector is None:
            self._local_detector = self.local_detector_factory()
        detections = self._local_detector.detect(source)
        return [dict(item) for item in detections if isinstance(item, dict)]

    @staticmethod
    def _photos_root(source: Path) -> Path:
        for parent in (source.parent, *source.parents):
            if parent.name.lower() == "photo":
                return parent
        raise ValueError("source_path_outside_photos_share")


def install_external_worker_gui_integration() -> None:
    """Patch the shared detector seam once for GUI-started face-frame cleanup."""

    service_class = FaceFrameStandardizationService
    if getattr(service_class, "_external_worker_gui_integration_installed", False):
        return

    original_prepared_detector = service_class._prepared_detector

    def _prepared_detector(self: FaceFrameStandardizationService, options: Dict[str, Any]) -> Any:
        return ExternalWorkerFaceDetectorAdapter(
            options=options,
            local_detector_factory=lambda: original_prepared_detector(self, options),
        )

    service_class._prepared_detector = _prepared_detector
    service_class._external_worker_gui_integration_installed = True
