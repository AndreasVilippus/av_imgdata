#!/usr/bin/env python3
"""Install external-worker dispatch into existing GUI-driven face workflows.

The integration wraps established detector/embedder boundaries. Existing GUI
workflows retain orchestration, status, findings, review, and write behavior;
only native processor calls are dispatched externally when a compatible worker
is ready. Local execution remains the pre-enqueue fallback.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from imgdata import ImgDataService
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
        debug_logger: Optional[Callable[..., None]] = None,
    ):
        factory = local_processor_factory or local_detector_factory
        if not callable(factory):
            raise ValueError("local_processor_factory_required")
        self.options = dict(options or {})
        self._local_processor_factory = factory
        self._composition_factory = composition_factory
        self.action = str(action or "face_processing")
        self._debug_logger = debug_logger if callable(debug_logger) else None
        self._local_processor = None
        self.external_worker_operation_id = ""

    def prepare(self) -> None:
        """Preparation stays lazy so external-only runs do not load NAS models."""

    def _build_composition(self) -> WorkerApiCompositionService:
        return self._call_composition_factory()

    def _call_composition_factory(self) -> WorkerApiCompositionService:
        factory = self._composition_factory
        return factory()

    def _build_local_processor(self) -> Any:
        return self._call_local_processor_factory()

    def _call_local_processor_factory(self) -> Any:
        factory = self._local_processor_factory
        return factory()

    def _local(self) -> Any:
        if self._local_processor is None:
            self._local_processor = self._build_local_processor()
        return self._local_processor

    def _operation(self) -> str:
        return "face_match" if self.action == "search_missing_faces_insightface" else "cleanup"

    def set_external_worker_operation_id(self, operation_id: str) -> None:
        self.external_worker_operation_id = str(operation_id or "").strip()

    def _operation_id(self, suffix: str) -> str:
        return self.external_worker_operation_id or f"{self.action}-{suffix}-{uuid.uuid4().hex}"

    def cancel_external_worker_operation(self, operation_id: str, *, reason: str = "operation_cancelled") -> Dict[str, Any]:
        operation_id = str(operation_id or "").strip()
        if not operation_id:
            return {"status": "skipped", "cancelled_jobs": 0}
        composition = self._build_composition()
        if not composition.enabled():
            return {"status": "disabled", "cancelled_jobs": 0}
        return composition.worker_api.cancel_jobs_by_origin(
            origin_filter={"operation_id": operation_id, "action": self.action},
            reason=reason,
        )

    def _debug_log(self, event: str, **fields: Any) -> None:
        logger = self._debug_logger
        if not callable(logger):
            return
        try:
            logger(event, **fields)
        except Exception:
            pass

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

    def _batch_root(self, paths: List[Path]) -> Path:
        if not paths:
            raise ValueError("worker_batch_image_paths_required")
        root = self._photos_root(paths[0])
        for path in paths[1:]:
            if self._photos_root(path) != root:
                raise ValueError("worker_batch_mixed_path_profiles")
        return root


class ExternalWorkerFaceDetectorAdapter(_ExternalWorkerFaceBase):
    """Expose the existing face-detection boundary with external dispatch."""

    def detect(self, image_path: Path) -> List[Dict[str, Any]]:
        source = Path(image_path).expanduser().resolve()
        composition = self._build_composition()
        if not composition.enabled():
            self._debug_log("external_worker_dispatch_local", capability="face_native_detect", action=self.action, reason="worker_api_disabled")
            return self._detect_local(source)
        processor = composition.external_face_processor(nas_root=self._photos_root(source), debug_logger=self._debug_log)
        result = processor.execute_face_detect(
            image_path=source,
            local_execute=lambda: self._detect_local(source),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("detect"),
            source_id=str(source),
            entity_type="image",
            entity_id=str(source),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )
        faces = result.get("faces") if isinstance(result, dict) else []
        return self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])

    def detect_many(self, image_paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        if not paths:
            return {}
        if len(paths) == 1:
            return {str(paths[0]): self.detect(paths[0])}
        composition = self._build_composition()
        if not composition.enabled():
            return self._detect_many_local(paths)
        processor = composition.external_face_processor(nas_root=self._batch_root(paths), debug_logger=self._debug_log)
        if not processor.has_compatible_worker(processor.FACE_DETECT_BATCH_CAPABILITY):
            return {str(path): self.detect(path) for path in paths}
        dispatched = processor.execute_face_detect_batch(
            image_paths=paths,
            local_execute=lambda: self._detect_many_local(paths),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("detect-batch"),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )
        images = dispatched.get("images") if isinstance(dispatched, dict) else {}
        return {
            str(path): self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])
            for path, faces in images.items()
            if isinstance(faces, list)
        }

    def _detect_local(self, source: Path) -> List[Dict[str, Any]]:
        detections = self._local().detect(source)
        return [dict(item) for item in detections if isinstance(item, dict)]

    def _detect_many_local(self, paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
        processor = self._local()
        detect_many = getattr(processor, "detect_many", None)
        if callable(detect_many):
            result = detect_many(paths)
            if isinstance(result, dict):
                return {
                    str(path): [dict(face) for face in faces if isinstance(face, dict)]
                    for path, faces in result.items()
                    if isinstance(faces, list)
                }
        return {str(path): self._detect_local(path) for path in paths}


class ExternalWorkerFaceEmbedderAdapter(_ExternalWorkerFaceBase):
    """Expose recognition processor operations through existing Worker contracts."""

    supports_async_batch_prefetch = True
    supports_async_batch_queue = True

    def detect_and_embed(self, image_path: Path) -> List[Dict[str, Any]]:
        source = Path(image_path).expanduser().resolve()
        composition = self._build_composition()
        if not composition.enabled():
            self._debug_log("external_worker_dispatch_local", capability="face_native_embed", action=self.action, reason="worker_api_disabled")
            return self._embed_local(source)
        processor = composition.external_face_processor(nas_root=self._photos_root(source), debug_logger=self._debug_log)
        result = processor.execute_face_embed(
            image_path=source,
            local_execute=lambda: self._embed_local(source),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("embed"),
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
        """Use the native batch contract without introducing pipeline state."""
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        if not paths:
            return {}
        if len(paths) == 1:
            return {str(paths[0]): self.detect_and_embed(paths[0])}
        composition = self._build_composition()
        if not composition.enabled():
            return self._embed_many_local(paths)
        processor = composition.external_face_processor(nas_root=self._batch_root(paths), debug_logger=self._debug_log)
        if not processor.has_compatible_worker(processor.FACE_EMBED_BATCH_CAPABILITY):
            return {str(path): self.detect_and_embed(path) for path in paths}
        dispatched = processor.execute_face_embed_batch(
            image_paths=paths,
            local_execute=lambda: self._embed_many_local(paths),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("embed-batch"),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )
        images = dispatched.get("images") if isinstance(dispatched, dict) else {}
        normalized: Dict[str, List[Dict[str, Any]]] = {}
        for path, faces in images.items():
            if not isinstance(faces, list):
                continue
            filtered = self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])
            normalized[str(path)] = [face for face in filtered if isinstance(face.get("embedding"), list)]
        return normalized

    def start_detect_and_embed_many(self, image_paths: List[Path]) -> Optional[Dict[str, Any]]:
        paths = [Path(path).expanduser().resolve() for path in list(image_paths or [])]
        if len(paths) <= 1:
            return None
        composition = self._build_composition()
        if not composition.enabled():
            return None
        processor = composition.external_face_processor(nas_root=self._batch_root(paths), debug_logger=self._debug_log)
        if not processor.has_compatible_worker(processor.FACE_EMBED_BATCH_CAPABILITY):
            return None
        return processor.start_face_embed_batch(
            image_paths=paths,
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("embed-batch"),
            det_thresh=float(self.options.get("det_thresh", 0.5)),
            max_num=int(self.options.get("max_num", 0)),
            det_size=self.options.get("det_size") or [640, 640],
        )

    def finish_detect_and_embed_many(self, handle: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        paths = [Path(path).expanduser().resolve() for path in list(handle.get("image_paths") or [])]
        if not paths:
            return {}
        composition = self._build_composition()
        processor = composition.external_face_processor(nas_root=self._batch_root(paths), debug_logger=self._debug_log)
        images = processor.finish_face_batch(handle)
        normalized: Dict[str, List[Dict[str, Any]]] = {}
        for path, faces in images.items():
            if not isinstance(faces, list):
                continue
            filtered = self._filter_faces([dict(face) for face in faces if isinstance(face, dict)])
            normalized[str(path)] = [face for face in filtered if isinstance(face.get("embedding"), list)]
        return normalized

    def detect_and_embed_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Byte previews are not shared-path assets and therefore remain local."""
        return self._local().detect_and_embed_bytes(image_bytes)

    def rank_embeddings(
        self,
        target_embeddings: List[List[float]],
        profile_embeddings: List[List[float]],
    ) -> List[Dict[str, Any]]:
        composition = self._build_composition()
        if not composition.enabled():
            self._debug_log("external_worker_dispatch_local", capability="face_native_rank_embeddings", action=self.action, reason="worker_api_disabled")
            return self._rank_local(target_embeddings, profile_embeddings)
        processor = composition.external_face_processor(nas_root=Path("/"), debug_logger=self._debug_log)
        dispatched = processor.execute_rank_embeddings(
            target_embeddings=target_embeddings,
            profile_embeddings=profile_embeddings,
            local_execute=lambda: self._rank_local(target_embeddings, profile_embeddings),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("rank"),
        )
        result = dispatched.get("result") if isinstance(dispatched, dict) else {}
        ranks = result.get("ranks") if isinstance(result, dict) and isinstance(result.get("ranks"), list) else []
        return [dict(rank) for rank in ranks if isinstance(rank, dict)]

    def profile_math(self, embeddings: List[List[float]]) -> Dict[str, Any]:
        composition = self._build_composition()
        if not composition.enabled():
            self._debug_log("external_worker_dispatch_local", capability="face_native_profile_math", action=self.action, reason="worker_api_disabled")
            return self._profile_math_local(embeddings)
        processor = composition.external_face_processor(nas_root=Path("/"), debug_logger=self._debug_log)
        dispatched = processor.execute_profile_math(
            embeddings=embeddings,
            local_execute=lambda: self._profile_math_local(embeddings),
            policy="external_preferred",
            operation=self._operation(),
            action=self.action,
            mode="scan",
            operation_id=self._operation_id("profile-math"),
        )
        result = dispatched.get("result") if isinstance(dispatched, dict) else {}
        return dict(result) if isinstance(result, dict) else {}

    def _embed_local(self, source: Path) -> List[Dict[str, Any]]:
        faces = self._local().detect_and_embed(source)
        return [dict(item) for item in faces if isinstance(item, dict)]

    def _embed_many_local(self, paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
        processor = self._local()
        detect_many = getattr(processor, "detect_and_embed_many", None)
        if callable(detect_many):
            result = detect_many(paths)
            if isinstance(result, dict):
                return {
                    str(path): [dict(face) for face in faces if isinstance(face, dict)]
                    for path, faces in result.items()
                    if isinstance(faces, list)
                }
        return {str(path): self._embed_local(path) for path in paths}

    def _rank_local(
        self,
        target_embeddings: List[List[float]],
        profile_embeddings: List[List[float]],
    ) -> List[Dict[str, Any]]:
        return self._local().rank_embeddings(target_embeddings, profile_embeddings)

    def _profile_math_local(self, embeddings: List[List[float]]) -> Dict[str, Any]:
        result = self._local().profile_math(embeddings)
        return dict(result) if isinstance(result, dict) else {}

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
    _install_face_match_insightface_integration()


def _install_face_frame_integration() -> None:
    service_class = FaceFrameStandardizationService
    if getattr(service_class, "_external_worker_gui_integration_installed", False):
        return
    original_prepared_detector = service_class._prepared_detector

    def _prepared_detector(self: FaceFrameStandardizationService, options: Dict[str, Any]) -> Any:
        debug_logger = getattr(getattr(self, "backend", None), "_debugLog", None)
        return ExternalWorkerFaceDetectorAdapter(
            options=options,
            action=FaceFrameStandardizationService.ACTION,
            local_processor_factory=lambda: original_prepared_detector(self, options),
            debug_logger=debug_logger if callable(debug_logger) else None,
        )

    service_class._prepared_detector = _prepared_detector
    service_class._external_worker_gui_integration_installed = True


def _install_face_recognition_integration() -> None:
    service_class = FaceRecognitionService
    if getattr(service_class, "_external_worker_gui_integration_installed", False):
        return
    original_prepared_embedder = service_class._prepared_embedder
    original_run = service_class._run

    def _run(
        self: FaceRecognitionService,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        options: Dict[str, Any],
    ) -> None:
        self._external_worker_action = str(action or FaceRecognitionService.ACTION_BUILD)
        try:
            original_run(
                self,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                action=action,
                options=options,
            )
        finally:
            self._external_worker_action = ""

    def _prepared_embedder(self: FaceRecognitionService, options: Dict[str, Any]) -> Any:
        action = str(getattr(self, "_external_worker_action", "") or FaceRecognitionService.ACTION_BUILD)
        return ExternalWorkerFaceEmbedderAdapter(
            options=options,
            action=action,
            local_processor_factory=lambda: original_prepared_embedder(self, options),
            debug_logger=self._debug_log,
        )

    service_class._run = _run
    service_class._prepared_embedder = _prepared_embedder
    service_class._external_worker_gui_integration_installed = True


def _install_face_match_insightface_integration() -> None:
    service_class = ImgDataService
    if getattr(service_class, "_external_worker_face_match_integration_installed", False):
        return
    original_search = service_class.searchMissingPhotosFacesWithInsightFace

    def searchMissingPhotosFacesWithInsightFace(
        self: ImgDataService,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        original_detector_factory = self._createFaceDetector
        original_embedder_factory = self._createFaceEmbedder

        def create_detector(**factory_options: Any) -> ExternalWorkerFaceDetectorAdapter:
            return ExternalWorkerFaceDetectorAdapter(
                options=_normalized_factory_options(factory_options),
                action="search_missing_faces_insightface",
                local_processor_factory=lambda: original_detector_factory(**factory_options),
                debug_logger=self._debugLog,
            )

        def create_embedder(**factory_options: Any) -> ExternalWorkerFaceEmbedderAdapter:
            return ExternalWorkerFaceEmbedderAdapter(
                options=_normalized_factory_options(factory_options),
                action="search_missing_faces_insightface",
                local_processor_factory=lambda: original_embedder_factory(**factory_options),
                debug_logger=self._debugLog,
            )

        self._createFaceDetector = create_detector
        self._createFaceEmbedder = create_embedder
        try:
            return original_search(self, *args, **kwargs)
        finally:
            self._createFaceDetector = original_detector_factory
            self._createFaceEmbedder = original_embedder_factory

    service_class.searchMissingPhotosFacesWithInsightFace = searchMissingPhotosFacesWithInsightFace
    service_class._external_worker_face_match_integration_installed = True


def _normalized_factory_options(factory_options: Dict[str, Any]) -> Dict[str, Any]:
    source = dict(factory_options or {})
    return {
        "det_size": list(source.get("det_size") or [640, 640]),
        "det_thresh": float(source.get("det_thresh", 0.5)),
        "max_num": int(source.get("max_num", 0)),
        "min_width_ratio": float(source.get("min_width_ratio", source.get("min_face_width_ratio", 0.0)) or 0.0),
        "min_height_ratio": float(source.get("min_height_ratio", source.get("min_face_height_ratio", 0.0)) or 0.0),
        "min_area_ratio": float(source.get("min_area_ratio", source.get("min_face_area_ratio", 0.0)) or 0.0),
    }
