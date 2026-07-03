import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FaceDetectorUnavailable(RuntimeError):
    pass


def default_haar_cascade_path() -> Path:
    return Path(__file__).resolve().parents[1] / "face_detection_models" / "haarcascade_frontalface_default.xml"


class OpenCvHaarFaceDetector:
    def __init__(self, cascade_path: Optional[Path] = None):
        self.cascade_path = Path(cascade_path) if cascade_path else default_haar_cascade_path()

    def detect(self, image_path: Path, *, scale_factor: float = 1.1, min_neighbors: int = 4, min_size: int = 24) -> List[Dict[str, Any]]:
        try:
            import cv2
        except ImportError as exc:
            raise FaceDetectorUnavailable("opencv-python-headless is required for Haar face detection") from exc

        if not self.cascade_path.exists():
            raise FaceDetectorUnavailable(f"face detection model not found: {self.cascade_path}")

        cascade = cv2.CascadeClassifier(str(self.cascade_path))
        if cascade.empty():
            raise FaceDetectorUnavailable(f"face detection model could not be loaded: {self.cascade_path}")

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"image could not be read: {image_path}")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rectangles = cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=(min_size, min_size),
        )
        height, width = gray.shape[:2]
        faces = []
        for x, y, w, h in rectangles:
            faces.append({
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "bbox": {
                    "x1": float(x) / width,
                    "y1": float(y) / height,
                    "x2": float(x + w) / width,
                    "y2": float(y + h) / height,
                },
                "center": {
                    "x": float(x + (w / 2)) / width,
                    "y": float(y + (h / 2)) / height,
                },
            })

        return sorted(faces, key=lambda face: (face["y"], face["x"]))


class InsightFaceDetector:
    """Model-store helper retained for native InsightFace-compatible ONNX models."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise FaceDetectorUnavailable("Python InsightFace integration has been removed; use the native face processor")

    @staticmethod
    def resolved_model_root(model_root: Optional[Path] = None) -> Path:
        if model_root is not None:
            return Path(model_root).expanduser().resolve()
        return Path(os.path.expanduser("~/.insightface")).resolve()

    @classmethod
    def model_store_dir(cls, model_root: Optional[Path] = None) -> Path:
        return cls.resolved_model_root(model_root) / "models"

    @classmethod
    def available_models(cls, model_root: Optional[Path] = None) -> Dict[str, Any]:
        resolved_root = cls.resolved_model_root(model_root)
        model_store = cls.model_store_dir(resolved_root)
        models: List[Dict[str, Any]] = []
        if model_store.is_dir():
            for entry in sorted(model_store.iterdir(), key=lambda path: path.name.lower()):
                if not entry.is_dir():
                    continue
                onnx_files = sorted(path.name for path in entry.rglob("*.onnx") if path.is_file())
                if not onnx_files:
                    continue
                models.append({
                    "name": entry.name,
                    "installed": True,
                    "path": str(entry),
                    "onnx_files": onnx_files,
                })
        return {
            "root": str(resolved_root),
            "model_store": str(model_store),
            "models": sorted(models, key=lambda item: item["name"].lower()),
        }
