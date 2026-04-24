from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    def __init__(self, model_name: str = "buffalo_l", model_root: Optional[Path] = None, ctx_id: int = -1, det_size: Tuple[int, int] = (640, 640)):
        self.model_name = model_name
        self.model_root = Path(model_root) if model_root else None
        self.ctx_id = ctx_id
        self.det_size = det_size
        self._app = None

    def _load_app(self):
        if self._app is not None:
            return self._app

        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"insightface could not be imported: {exc}") from exc

        kwargs: Dict[str, Any] = {
            "name": self.model_name,
            "allowed_modules": ["detection"],
        }
        if self.model_root is not None:
            kwargs["root"] = str(self.model_root)
        try:
            app = FaceAnalysis(**kwargs)
        except TypeError as exc:
            if "allowed_modules" not in str(exc):
                raise FaceDetectorUnavailable(f"insightface app could not be initialized: {type(exc).__name__}: {exc}") from exc
            kwargs.pop("allowed_modules", None)
            try:
                app = FaceAnalysis(**kwargs)
            except Exception as fallback_exc:
                raise FaceDetectorUnavailable(self._format_app_init_error(fallback_exc)) from fallback_exc
        except Exception as exc:
            raise FaceDetectorUnavailable(self._format_app_init_error(exc)) from exc
        try:
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
        except TypeError as exc:
            if "det_size" not in str(exc):
                raise FaceDetectorUnavailable(self._format_app_prepare_error(exc)) from exc
            try:
                app.prepare(ctx_id=self.ctx_id)
            except Exception as fallback_exc:
                raise FaceDetectorUnavailable(self._format_app_prepare_error(fallback_exc)) from fallback_exc
        except Exception as exc:
            raise FaceDetectorUnavailable(self._format_app_prepare_error(exc)) from exc
        self._app = app
        return app

    def _model_location_hint(self) -> str:
        root = str(self.model_root) if self.model_root is not None else "~/.insightface"
        return f"model_name={self.model_name}, model_root={root}"

    def _format_app_init_error(self, exc: Exception) -> str:
        detail = str(exc).strip()
        suffix = f": {detail}" if detail else ""
        return f"insightface app could not be initialized ({self._model_location_hint()}): {type(exc).__name__}{suffix}"

    def _format_app_prepare_error(self, exc: Exception) -> str:
        detail = str(exc).strip()
        suffix = f": {detail}" if detail else ""
        return f"insightface detection model could not be prepared ({self._model_location_hint()}): {type(exc).__name__}{suffix}"

    def detect(self, image_path: Path) -> List[Dict[str, Any]]:
        try:
            import cv2
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"opencv-python-headless/cv2 could not be imported: {exc}") from exc

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"image could not be read: {image_path}")

        height, width = image.shape[:2]
        app = self._load_app()
        faces = []
        for detected in app.get(image):
            bbox = getattr(detected, "bbox", None)
            if bbox is None or len(bbox) < 4:
                continue
            x1 = max(0.0, min(float(width), float(bbox[0])))
            y1 = max(0.0, min(float(height), float(bbox[1])))
            x2 = max(0.0, min(float(width), float(bbox[2])))
            y2 = max(0.0, min(float(height), float(bbox[3])))
            if x2 <= x1 or y2 <= y1:
                continue
            score = getattr(detected, "det_score", None)
            face = {
                "x": int(round(x1)),
                "y": int(round(y1)),
                "w": int(round(x2 - x1)),
                "h": int(round(y2 - y1)),
                "bbox": {
                    "x1": x1 / width,
                    "y1": y1 / height,
                    "x2": x2 / width,
                    "y2": y2 / height,
                },
                "center": {
                    "x": ((x1 + x2) / 2) / width,
                    "y": ((y1 + y2) / 2) / height,
                },
            }
            if score is not None:
                face["score"] = float(score)
            faces.append(face)

        return sorted(faces, key=lambda face: (face["y"], face["x"]))
