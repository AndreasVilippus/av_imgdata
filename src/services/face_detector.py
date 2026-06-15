import os
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
    def __init__(
        self,
        model_name: str = "",
        model_root: Optional[Path] = None,
        ctx_id: int = -1,
        det_size: Tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
        max_num: int = 0,
        min_width_ratio: float = 0.0,
        min_height_ratio: float = 0.0,
        min_area_ratio: float = 0.0,
        min_face_width_ratio: Optional[float] = None,
        min_face_height_ratio: Optional[float] = None,
        min_face_area_ratio: Optional[float] = None,
    ):
        self.model_name = str(model_name or "").strip()
        self.model_root = Path(model_root) if model_root else None
        self.ctx_id = ctx_id
        self.det_size = det_size
        self.det_thresh = max(0.0, min(1.0, float(det_thresh)))
        self.max_num = max(0, int(max_num))
        self.min_width_ratio = max(0.0, float(min_face_width_ratio if min_face_width_ratio is not None else min_width_ratio))
        self.min_height_ratio = max(0.0, float(min_face_height_ratio if min_face_height_ratio is not None else min_height_ratio))
        self.min_area_ratio = max(0.0, float(min_face_area_ratio if min_face_area_ratio is not None else min_area_ratio))
        self._app = None

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

    def _resolved_model_root(self) -> Path:
        return self.resolved_model_root(self.model_root)

    def _validate_model_files(self) -> None:
        model_name = str(self.model_name or "").strip()
        if not model_name:
            raise FaceDetectorUnavailable("insightface model name is not configured")
        model_dir = self.model_store_dir(self._resolved_model_root()) / model_name
        if not model_dir.is_dir():
            raise FaceDetectorUnavailable(
                f"insightface model {model_name} not found in {model_dir.parent}"
            )
        onnx_files = sorted(path for path in model_dir.rglob("*.onnx") if path.is_file())
        if not onnx_files:
            raise FaceDetectorUnavailable(
                f"insightface model {model_name} is incomplete in {model_dir}: no ONNX files found"
            )

    def _load_app(self):
        if self._app is not None:
            return self._app

        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise FaceDetectorUnavailable(f"insightface could not be imported: {exc}") from exc

        kwargs: Dict[str, Any] = {
            "allowed_modules": ["detection"],
        }
        if self.model_name:
            kwargs["name"] = self.model_name
        kwargs["root"] = str(self._resolved_model_root())
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
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size, det_thresh=self.det_thresh)
        except TypeError as exc:
            if "det_thresh" in str(exc):
                try:
                    app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
                except TypeError as det_size_exc:
                    if "det_size" not in str(det_size_exc):
                        raise FaceDetectorUnavailable(self._format_app_prepare_error(det_size_exc)) from det_size_exc
                    try:
                        app.prepare(ctx_id=self.ctx_id)
                    except Exception as fallback_exc:
                        raise FaceDetectorUnavailable(self._format_app_prepare_error(fallback_exc)) from fallback_exc
                except Exception as fallback_exc:
                    raise FaceDetectorUnavailable(self._format_app_prepare_error(fallback_exc)) from fallback_exc
            elif "det_size" in str(exc):
                try:
                    app.prepare(ctx_id=self.ctx_id)
                except Exception as fallback_exc:
                    raise FaceDetectorUnavailable(self._format_app_prepare_error(fallback_exc)) from fallback_exc
            else:
                raise FaceDetectorUnavailable(self._format_app_prepare_error(exc)) from exc
        except Exception as exc:
            raise FaceDetectorUnavailable(self._format_app_prepare_error(exc)) from exc
        self._app = app
        return app

    def prepare(self) -> None:
        self._validate_model_files()
        self._load_app()

    def _model_location_hint(self) -> str:
        model_name = self.model_name or "insightface_default"
        return f"model_name={model_name}, model_root={self._resolved_model_root()}, model_store={self.model_store_dir(self._resolved_model_root())}"

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
        try:
            detected_faces = app.get(image, max_num=self.max_num)
        except TypeError as exc:
            if "max_num" not in str(exc):
                raise
            detected_faces = app.get(image)
        for detected in detected_faces:
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
            if score is not None and float(score) < self.det_thresh:
                continue
            if ((x2 - x1) / width) < self.min_width_ratio or ((y2 - y1) / height) < self.min_height_ratio:
                continue
            if (((x2 - x1) * (y2 - y1)) / (width * height)) < self.min_area_ratio:
                continue
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
