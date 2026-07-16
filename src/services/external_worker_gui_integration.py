#!/usr/bin/env python3
"""Install external-worker dispatch into existing GUI-driven face workflows.

The integration wraps the established detector/embedder boundaries. Existing GUI
workflows retain their orchestration, statuses, findings, review and write behavior;
only native processor calls are dispatched externally when a compatible worker is
ready. Local execution remains the pre-enqueue fallback.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.face_frame_standardization_service import FaceFrameStandardizationService
from services.face_recognition_service import FaceRecognitionService
from services.worker_api_composition_service import WorkerApiCompositionService


class _ExternalWorkerFaceBase:
    def __init__(
        self,
        *,
        options: Dict[str, Any],
        local_processor_factory: Optional[Callable[[], Any]] = None,
        local_detector_factory: Optional[Callable[[], Any]] = None,
        action: str = "standardize_face_frames",
        composition_factory: Callable[[], WorkerApiCompositionService] = WorkerApiCompositionService,
    ):
        factory = local_processor_factory or local_detector_factory
        if not callable(factory):
            raise ValueError("local_processor_factory_required")
        self.options = dict(options or {})
        self.local_processor_factory = factory
        self.composition_factory = composition_factory
        self.action = str(action or "face_processing")
        self._local_processor = None

    def prepare(self) -> None:
        """Preparation stays lazy so external-only runs do not load NAS models."""

    def _build_composition(self) -> WorkerApiCompositionService:
        factory = self.composition_factory
        return factory()

    def _build_local_processor(self) -> Any:
        factory = self.local_processor_factory
        return factory()

    def _local(self) -> Any:
        if self._local_processor is None:
            self._local_processor = self._build_local_processor()
        return self._local_processor

    def _filter_faces(self, faces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        min_width = float(self.options.get("min_width_ratio", 0.0) or 0.0)
        min_height = float(self.options.get("min_height_ratio", 0.0) or 0.0)
        min_area = float(self.options.get("min_area_ratio", 0.0) or 0.0)
        filtered: List[Dict[str, Any]] = []
        for raw in faces:
            face = dict(raw) if isinstance(raw, dict) else {}
            bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
            try:
                width = max(0.0, float(bbox.get("x2")) - float(bbox.get("x1")))
                height = max(0.0, float(bbox.get("y2")) - float(bbox.get("y1")))
            except (TypeError, ValueError):
                continue
            if width < min_width or height < min_height or width * height < min_area:
                continue
            filtered.append(face)
        return filtered

    @staticmethod
    def _photos_root(source: Path) -> Path:
        for parent in (source.parent, *source.parents):
            if parent.name.lower() == "photo":
                return parent
        raise ValueError("source_path_outside_photos_share")


class ExternalWorkerFaceDetectorAdapter(_ExternalWorkerFaceBase):
    """Expose the existing ``detect(Path)`` boundary with external dispatch."""

    def detect(self, image_path: Path) -> List[Dict[str, Any]]:
        source = Path(image_path).expanduser().resolve()
        composition = self._build_composition()
        if not composition.enabled():
            return self._detect_local(source)
        processor = composition.external_face_processor(nas_root=self._photos_root(source))
        result = processor.execute_face_detect(
            image_path=source,
            local_execute=lambda: self._detect_local(source),
            policy="external_preferred",
            operation="cleanup",
            action=self.action,
            mode="scan",
            operation_id=f"{self.action}-detect-{uuid.uuid4().hex}",
            source_id=str(source),
            entity_type="image",
            entity_id=str(source),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )
        faces = result.get("faces") if isinstance(result, dict) else []
        return self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])

    def _detect_local(self, source: Path) -> List[Dict[str, Any]]:
        detections = self._local().detect(source)
        return [dict(item) for item in detections if isinstance(item, dict)]


class ExternalWorkerFaceEmbedderAdapter(_ExternalWorkerFaceBase):
    """Expose recognition's detect-and-embed boundary through face_native_embed."""

    def detect_and_embed(self, image_path: Path) -> List[Dict[str, Any]]:
        source = Path(image_path).expanduser().resolve()
        composition = self._build_composition()
        if not composition.enabled():
            return self._embed_local(source)
        processor = composition.external_face_processor(nas_root=self._photos_root(source))
        result = processor.execute_face_embed(
            image_path=source,
            local_execute=lambda: self._embed_local(source),
            policy="external_preferred",
            operation="cleanup",
            action=self.action,
            mode="scan",
            operation_id=f"{self.action}-embed-{uuid.uuid4().hex}",
            source_id=str(source),
            entity_type="image",
            entity_id=str(source),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )
        faces = result.get("faces") if isinstance(result, dict) else []
        normalized = self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])
        return [face for face in normalized if isinstance(face.get("embedding"), list)]

    def detect_and_embed_many(self, image_paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
        """Keep the existing batch interface without introducing pipeline state."""
        return {str(Path(path)): self.detect_and_embed(Path(path)) for path in list(image_paths or [])}

    def detect_and_embed_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Byte previews are not shared-path assets and therefore remain local."""
        return self._local().detect_and_embed_bytes(image_bytes)

    def _embed_local(self, source: Path) -> List[Dict[str, Any]]:
        faces = self._local().detect_and_embed(source)
        return [dict(item) for item in faces if isinstance(item, dict)]

    @staticmethod
    def _iou(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        try:
            x1 = max(float(left["x1"]), float(right["x1"]))
            y1 = max(float(left["y1"]), float(right["y1"]))
            x2 = min(float(left["x2"]), float(right["x2"]))
            y2 = min(float(left["y2"]), float(right["y2"]))
            intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            left_area = max(0.0, float(left["x2"]) - float(left["x1"])) * max(0.0, float(left["y2"]) - float(left["y1"]))
            right_area = max(0.0, float(right["x2"]) - float(right["x1"])) * max(0.0, float(right["y2"]) - float(right["y1"]))
        except (KeyError, TypeError, ValueError):
            return 0.0
        union = left_area + right_area - intersection
        return intersection / union if union > 0.0 else 0.0


def install_external_worker_gui_integration() -> None:
    """Patch shared processor seams once for GUI-started face workflows."""
    _install_face_frame_integration()
    _install_face_recognition_integration()


def _install_face_frame_integration() -> None:
    service_class = FaceFrameStandardizationService
    if getattr(service_class, "_external_worker_gui_integration_installed", False):
        return
    original_prepared_detector = service_class._prepared_detector

    def _prepared_detector(self: FaceFrameStandardizationService, options: Dict[str, Any]) -> Any:
        return ExternalWorkerFaceDetectorAdapter(
            options=options,
            action=FaceFrameStandardizationService.ACTION,
            local_processor_factory=lambda: original_prepared_detector(self, options),
        )

    service_class._prepared_detector = _prepared_detector
    service_class._external_worker_gui_integration_installed = True


def _install_face_recognition_integration() -> None:
    service_class = FaceRecognitionService
    if getattr(service_class, "_external_worker_gui_integration_installed", False):
        return
    original_prepared_embedder = service_class._prepared_embedder
    original_run = service_class._run

    def _run(self: FaceRecognitionService, *, user_key: str, cookies: Dict[str, str], base_url: str, action: str, options: Dict[str, Any]) -> None:
        self._external_worker_action = str(action or FaceRecognitionService.ACTION_BUILD)
        try:
            original_run(self, user_key=user_key, cookies=cookies, base_url=base_url, action=action, options=options)
        finally:
            self._external_worker_action = ""

    def _prepared_embedder(self: FaceRecognitionService, options: Dict[str, Any]) -> Any:
        action = str(getattr(self, "_external_worker_action", "") or FaceRecognitionService.ACTION_BUILD)
        return ExternalWorkerFaceEmbedderAdapter(
            options=options,
            action=action,
            local_processor_factory=lambda: original_prepared_embedder(self, options),
        )

    service_class._run = _run
    service_class._prepared_embedder = _prepared_embedder
    service_class._external_worker_gui_integration_installed = True
