#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector
from services.face_embedder import InsightFaceEmbedder


class NativeFaceProcessorUnavailable(FaceDetectorUnavailable):
    pass


class NativeFaceProcessorService:
    """Adapter for a package-shipped native face processor executable."""

    CONTRACT_VERSION = "1.0"

    def __init__(self, config_service: Any, *, package_root: Optional[Path] = None, debug_logger: Optional[Callable[..., None]] = None):
        self.config_service = config_service
        self.package_root = Path(package_root) if package_root else Path(os.getenv("SYNOPKG_PKGDEST", "/var/packages/AV_ImgData/target"))
        self._debug_logger = debug_logger if callable(debug_logger) else None

    def set_debug_logger(self, debug_logger: Optional[Callable[..., None]]) -> None:
        self._debug_logger = debug_logger if callable(debug_logger) else None

    def _debug_log(self, event: str, **fields: Any) -> None:
        logger = self._debug_logger
        if not callable(logger):
            return
        try:
            logger(event, **fields)
        except Exception:
            pass

    def config(self) -> Dict[str, Any]:
        try:
            root = self.config_service.readMergedConfig()
        except Exception:
            root = {}
        processors = root.get("native_processors") if isinstance(root.get("native_processors"), dict) else {}
        config = processors.get("FACE_PROCESSOR") if isinstance(processors.get("FACE_PROCESSOR"), dict) else {}
        return config

    def enabled(self) -> bool:
        return bool(self.config().get("ENABLED", False))

    def executable_path(self) -> Path:
        configured = str(self.config().get("PATH") or "bin/av-imgdata-face-processor").strip()
        path = Path(configured)
        if path.is_absolute():
            return path
        return (self.package_root / path).resolve()

    def timeout_seconds(self) -> int:
        try:
            return max(1, min(3600, int(self.config().get("TIMEOUT_SECONDS", 120))))
        except Exception:
            return 120

    def model_root(self, fallback: Optional[Path] = None) -> Path:
        configured = str(self.config().get("MODEL_ROOT") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(fallback).expanduser().resolve() if fallback else InsightFaceDetector.resolved_model_root(None)

    def model_name(self, fallback: str = "") -> str:
        configured = str(self.config().get("MODEL_NAME") or "").strip()
        return configured or str(fallback or "").strip()

    def status(self, *, model_root: Optional[Path] = None, model_name: str = "") -> Dict[str, Any]:
        config = self.config()
        path = self.executable_path()
        enabled = bool(config.get("ENABLED", False))
        result: Dict[str, Any] = {
            "enabled": enabled,
            "path": str(path),
            "present": path.is_file(),
            "executable": os.access(str(path), os.X_OK),
            "available": False,
            "reason": "disabled" if not enabled else "",
        }
        if not enabled:
            return result
        if not result["present"]:
            result["reason"] = "binary_missing"
            return result
        if not result["executable"]:
            result["reason"] = "binary_not_executable"
            return result
        version = self._run_simple([str(path), "version"])
        result["version_result"] = version
        if not version["ok"]:
            result["reason"] = "version_failed"
            result["last_error"] = version.get("output", "")
            return result
        result["version"] = version.get("output", "").strip()
        version_lower = result["version"].lower()
        if "skeleton" in version_lower:
            result["backend"] = "skeleton"
        elif "python-bridge" in version_lower or "python_bridge" in version_lower:
            result["backend"] = "python_bridge"
        else:
            result["backend"] = "native"
        probe_root = self.model_root(model_root)
        probe_name = self.model_name(model_name)
        result["model_root"] = str(probe_root)
        result["model_name"] = probe_name
        if probe_name:
            probe = self._run_simple([str(path), "probe", "--model-root", str(probe_root), "--model-name", probe_name])
            result["probe_result"] = probe
            if not probe["ok"]:
                result["reason"] = "probe_failed"
                result["last_error"] = probe.get("output", "")
                return result
            probe_output = str(probe.get("output") or "").lower()
            if "skeleton" in probe_output:
                result["backend"] = "skeleton"
            elif "python-bridge" in probe_output or "python_bridge" in probe_output:
                result["backend"] = "python_bridge"
        if result.get("backend") == "skeleton":
            result["inference_available"] = False
            result["reason"] = "skeleton_no_inference"
            result["last_error"] = "native face processor skeleton does not run inference"
            return result
        result["inference_available"] = True
        result["available"] = True
        result["reason"] = "ready"
        return result

    def create_detector(self, **kwargs: Any) -> "NativeFaceDetector":
        return NativeFaceDetector(self, **kwargs)

    def create_embedder(self, **kwargs: Any) -> "NativeFaceEmbedder":
        return NativeFaceEmbedder(self, **kwargs)

    def _run_simple(self, command: List[str]) -> Dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout_seconds(),
            )
        except Exception as exc:
            return {"ok": False, "output": f"{type(exc).__name__}: {exc}"}
        return {"ok": completed.returncode == 0, "returncode": completed.returncode, "output": completed.stdout.strip()}

    def run_faces(self, command: str, image_path: Path, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        executable = self.executable_path()
        started_at = time.monotonic()
        image_path = Path(image_path)
        image_hash = hashlib.sha256(str(image_path).encode("utf-8", errors="replace")).hexdigest()[:16]
        self._debug_log(
            "native_face_processor_run_start",
            command=command,
            image_path_hash=image_hash,
            executable=str(executable),
        )
        with tempfile.TemporaryDirectory(prefix="av-imgdata-native-face-") as tmpdir:
            workdir = Path(tmpdir)
            input_path = workdir / "job-input.json"
            output_path = workdir / "processor-result.json"
            input_path.write_text(json.dumps(self._job_input(command, image_path, options), ensure_ascii=False, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [str(executable), command, "--input", str(input_path), "--output", str(output_path), "--workdir", str(workdir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout_seconds(),
            )
            if completed.returncode != 0:
                self._debug_log(
                    "native_face_processor_run_failed",
                    command=command,
                    image_path_hash=image_hash,
                    returncode=completed.returncode,
                    duration_ms=round((time.monotonic() - started_at) * 1000, 2),
                    output=(completed.stdout or "").strip()[-500:],
                )
                raise NativeFaceProcessorUnavailable(
                    f"native face processor {command} failed with exit {completed.returncode}: {completed.stdout.strip()}"
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._debug_log(
                    "native_face_processor_run_failed",
                    command=command,
                    image_path_hash=image_hash,
                    returncode=completed.returncode,
                    duration_ms=round((time.monotonic() - started_at) * 1000, 2),
                    output=f"invalid_result_json: {exc}",
                )
                raise NativeFaceProcessorUnavailable(f"native face processor did not write valid result JSON: {exc}") from exc
        faces = self._normalize_faces(payload)
        self._debug_log(
            "native_face_processor_run_finished",
            command=command,
            image_path_hash=image_hash,
            returncode=completed.returncode,
            duration_ms=round((time.monotonic() - started_at) * 1000, 2),
            faces_count=len(faces),
            processor_backend=(payload.get("processor") or {}).get("backend") if isinstance(payload, dict) and isinstance(payload.get("processor"), dict) else "",
        )
        return faces

    def _job_input(self, command: str, image_path: Path, options: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_version": self.CONTRACT_VERSION,
            "job_id": str(options.get("job_id") or "local"),
            "type": f"face_native_{command}",
            "input": {
                "image_path": str(image_path),
                "source_id": str(options.get("source_id") or image_path),
            },
            "options": {
                "model_root": str(options.get("model_root") or ""),
                "model_name": str(options.get("model_name") or ""),
                "min_confidence": float(options.get("det_thresh", 0.5)),
                "max_faces": int(options.get("max_num", 0)),
                "det_size": list(options.get("det_size") or (640, 640)),
                "normalize_coordinates": True,
            },
        }

    def _normalize_faces(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            raise NativeFaceProcessorUnavailable("native face processor result is not an object")
        if str(payload.get("status") or "").lower() not in {"completed", "success", "ok"}:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            message = str(error.get("message") or error.get("code") or payload.get("status") or "native processor failed")
            raise NativeFaceProcessorUnavailable(message)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        faces = result.get("faces") if isinstance(result.get("faces"), list) else []
        return [face for face in (self._normalize_face(face) for face in faces) if face is not None]

    def _normalize_face(self, face: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(face, dict):
            return None
        bbox = self._normalize_bbox(face)
        if not bbox:
            return None
        normalized: Dict[str, Any] = {
            "bbox": bbox,
            "score": float(face.get("confidence", face.get("score", 0.0)) or 0.0),
        }
        embedding = self._normalize_embedding(face.get("embedding"))
        if embedding:
            normalized["embedding"] = embedding
        normalized["x"] = int(round(float(bbox["x1"])))
        normalized["y"] = int(round(float(bbox["y1"])))
        normalized["w"] = int(round(max(0.0, float(bbox["x2"]) - float(bbox["x1"]))))
        normalized["h"] = int(round(max(0.0, float(bbox["y2"]) - float(bbox["y1"]))))
        normalized["center"] = {
            "x": (float(bbox["x1"]) + float(bbox["x2"])) / 2,
            "y": (float(bbox["y1"]) + float(bbox["y2"])) / 2,
        }
        return normalized

    @staticmethod
    def _normalize_bbox(face: Dict[str, Any]) -> Optional[Dict[str, float]]:
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else None
        if bbox:
            try:
                return {
                    "x1": float(bbox["x1"]),
                    "y1": float(bbox["y1"]),
                    "x2": float(bbox["x2"]),
                    "y2": float(bbox["y2"]),
                }
            except Exception:
                return None
        box = face.get("box") if isinstance(face.get("box"), dict) else None
        if box and str(box.get("unit") or "normalized").lower() == "normalized":
            try:
                x = float(box["x"])
                y = float(box["y"])
                return {
                    "x1": x,
                    "y1": y,
                    "x2": x + float(box["width"]),
                    "y2": y + float(box["height"]),
                }
            except Exception:
                return None
        return None

    @staticmethod
    def _normalize_embedding(value: Any) -> List[float]:
        if isinstance(value, list):
            return [float(item) for item in value]
        if isinstance(value, dict):
            raw = value.get("value")
            if str(value.get("encoding") or "").lower() == "float32-le-base64" and isinstance(raw, str):
                decoded = base64.b64decode(raw)
                return [float(item[0]) for item in struct.iter_unpack("<f", decoded)]
        return []


class NativeFaceDetector:
    def __init__(
        self,
        service: NativeFaceProcessorService,
        model_name: str = "",
        model_root: Optional[Path] = None,
        det_size: Any = (640, 640),
        det_thresh: float = 0.5,
        max_num: int = 0,
        min_width_ratio: float = 0.0,
        min_height_ratio: float = 0.0,
        min_area_ratio: float = 0.0,
        **_: Any,
    ):
        self.service = service
        self.model_root = service.model_root(model_root)
        self.model_name = service.model_name(model_name)
        self.options = {
            "model_root": str(self.model_root),
            "model_name": self.model_name,
            "det_size": tuple(det_size),
            "det_thresh": det_thresh,
            "max_num": max_num,
            "min_width_ratio": min_width_ratio,
            "min_height_ratio": min_height_ratio,
            "min_area_ratio": min_area_ratio,
        }

    def prepare(self) -> None:
        status = self.service.status(model_root=self.model_root, model_name=self.model_name)
        if not status.get("available"):
            raise NativeFaceProcessorUnavailable(str(status.get("reason") or "native face processor unavailable"))

    def detect(self, image_path: Path) -> List[Dict[str, Any]]:
        return self.service.run_faces("detect", Path(image_path), self.options)


class NativeFaceEmbedder(NativeFaceDetector):
    def detect_and_embed(self, image_path: Path) -> List[Dict[str, Any]]:
        return self.service.run_faces("embed", Path(image_path), self.options)

    def detect_and_embed_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        if not image_bytes:
            raise ValueError("image preview is empty")
        with tempfile.NamedTemporaryFile(prefix="av-imgdata-native-preview-", suffix=".jpg") as handle:
            handle.write(image_bytes)
            handle.flush()
            return self.detect_and_embed(Path(handle.name))

    @staticmethod
    def _iou(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        return InsightFaceEmbedder._iou(left, right)

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
