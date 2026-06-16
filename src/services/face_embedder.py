#!/usr/bin/env python3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector


class InsightFaceEmbedder(InsightFaceDetector):
    """Loads InsightFace detection and recognition without changing detector behavior."""

    def _load_app(self):
        if self._app is not None:
            return self._app
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"insightface could not be imported: {exc}") from exc

        kwargs: Dict[str, Any] = {
            "allowed_modules": ["detection", "recognition"],
            "root": str(InsightFaceDetector._resolved_model_root(self)),
        }
        if self.model_name:
            kwargs["name"] = self.model_name
        try:
            app = FaceAnalysis(**kwargs)
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size, det_thresh=self.det_thresh)
        except Exception as exc:
            raise FaceDetectorUnavailable(
                f"insightface recognition model could not be prepared ({InsightFaceDetector._model_location_hint(self)}): "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        self._app = app
        return app

    def detect_and_embed(self, image_path: Path) -> List[Dict[str, Any]]:
        try:
            import cv2
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"opencv-python-headless/cv2 could not be imported: {exc}") from exc

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"image could not be read: {image_path}")
        return self._detect_and_embed_image(image)

    def detect_and_embed_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            import cv2
            import numpy
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"opencv-python-headless/cv2 and numpy are required: {exc}") from exc
        if not image_bytes:
            raise ValueError("image preview is empty")
        image = cv2.imdecode(numpy.frombuffer(image_bytes, dtype=numpy.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("image preview could not be decoded")
        return self._detect_and_embed_image(image)

    def _detect_and_embed_image(self, image: Any) -> List[Dict[str, Any]]:
        height, width = image.shape[:2]
        try:
            faces = self._load_app().get(image, max_num=self.max_num)
        except TypeError as exc:
            if "max_num" not in str(exc):
                raise
            faces = self._load_app().get(image)
        result: List[Dict[str, Any]] = []
        for face in faces:
            bbox = getattr(face, "bbox", None)
            embedding = getattr(face, "normed_embedding", None)
            if bbox is None or len(bbox) < 4 or embedding is None:
                continue
            x1, y1 = max(0.0, float(bbox[0])), max(0.0, float(bbox[1]))
            x2, y2 = min(float(width), float(bbox[2])), min(float(height), float(bbox[3]))
            if x2 <= x1 or y2 <= y1:
                continue
            if ((x2 - x1) / width) < self.min_width_ratio or ((y2 - y1) / height) < self.min_height_ratio:
                continue
            result.append({
                "bbox": {"x1": x1 / width, "y1": y1 / height, "x2": x2 / width, "y2": y2 / height},
                "score": float(getattr(face, "det_score", 0.0) or 0.0),
                "embedding": [float(value) for value in embedding],
            })
        return result

    @staticmethod
    def _iou(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        x1, y1 = max(float(left["x1"]), float(right["x1"])), max(float(left["y1"]), float(right["y1"]))
        x2, y2 = min(float(left["x2"]), float(right["x2"])), min(float(left["y2"]), float(right["y2"]))
        intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        left_area = max(0.0, float(left["x2"]) - float(left["x1"])) * max(0.0, float(left["y2"]) - float(left["y1"]))
        right_area = max(0.0, float(right["x2"]) - float(right["x1"])) * max(0.0, float(right["y2"]) - float(right["y1"]))
        union = left_area + right_area - intersection
        return intersection / union if union > 0 else 0.0

    def embed_matched_face(
        self,
        image_path: Path,
        photos_bbox: Dict[str, Any],
        *,
        min_iou: float = 0.35,
    ) -> Optional[Dict[str, Any]]:
        candidates = self.detect_and_embed(image_path)
        if not candidates:
            return None
        best = max(candidates, key=lambda candidate: self._iou(photos_bbox, candidate["bbox"]))
        iou = self._iou(photos_bbox, best["bbox"])
        return {**best, "iou": iou} if iou >= float(min_iou) else None
