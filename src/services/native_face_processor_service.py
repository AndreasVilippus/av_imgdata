#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import select
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector
from services.face_embedder import InsightFaceEmbedder
from services.image_decode_service import ImageDecodeService


class NativeFaceProcessorUnavailable(FaceDetectorUnavailable):
    pass


class NativeFaceProcessorService:
    """Adapter for a package-shipped native face processor executable."""

    CONTRACT_VERSION = "1.0"

    def __init__(
        self,
        config_service: Any,
        *,
        package_root: Optional[Path] = None,
        debug_logger: Optional[Callable[..., None]] = None,
        image_decoder: Optional[Any] = None,
    ):
        self.config_service = config_service
        self.package_root = Path(package_root) if package_root else Path(os.getenv("SYNOPKG_PKGDEST", "/var/packages/AV_ImgData/target"))
        self._debug_logger = debug_logger if callable(debug_logger) else None
        self.image_decoder = image_decoder if image_decoder is not None else ImageDecodeService(config_service)
        self._worker_lock = threading.Lock()
        self._worker_process: Optional[Any] = None
        self._worker_key: Optional[Tuple[Any, ...]] = None

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

    def _ort_environment_config(self) -> Dict[str, str]:
        config = self.config()
        try:
            intra_threads = max(0, min(64, int(config.get("ORT_INTRA_THREADS", 0))))
        except Exception:
            intra_threads = 0
        graph_opt_level = str(config.get("ORT_GRAPH_OPT_LEVEL") or "all").strip().lower()
        if graph_opt_level not in {"disable", "basic", "extended", "all"}:
            graph_opt_level = "all"
        return {
            "AV_IMGDATA_ORT_INTRA_THREADS": str(intra_threads),
            "AV_IMGDATA_ORT_GRAPH_OPT_LEVEL": graph_opt_level,
        }

    def _processor_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.update(self._ort_environment_config())
        return env

    def model_root(self, fallback: Optional[Path] = None) -> Path:
        configured = str(self.config().get("MODEL_ROOT") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(fallback).expanduser().resolve() if fallback else InsightFaceDetector.resolved_model_root(None)

    def model_name(self, fallback: str = "") -> str:
        configured = str(self.config().get("MODEL_NAME") or "").strip()
        return configured or str(fallback or "").strip()

    def _python_bridge_debug_enabled(self) -> bool:
        try:
            root = self.config_service.readMergedConfig()
        except Exception:
            return False
        debug = root.get("debug") if isinstance(root.get("debug"), dict) else {}
        return bool(debug.get("BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED", False))

    def _insightface_license_acknowledged(self) -> bool:
        return bool(self.config().get("INSIGHTFACE_LICENSE_ACKNOWLEDGED", False))

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
        if not self._insightface_license_acknowledged():
            result["reason"] = "insightface_license_not_acknowledged"
            result["last_error"] = (
                "InsightFace model license terms must be acknowledged before the native face processor is used"
            )
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
        elif "onnxruntime-smoke" in version_lower or "onnxruntime_smoke" in version_lower:
            result["backend"] = "onnxruntime_smoke"
        else:
            result["backend"] = "native"
        probe_root = self.model_root(model_root)
        probe_name = self.model_name(model_name)
        result["model_root"] = str(probe_root)
        result["model_name"] = probe_name
        if result.get("backend") == "python_bridge":
            if not self._python_bridge_debug_enabled():
                result["inference_available"] = False
                result["hot_path_available"] = False
                result["reason"] = "python_bridge_disabled"
                result["last_error"] = (
                    "python bridge is disabled by default and only enabled when BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED is true"
                )
                return result
            result["inference_available"] = False
            result["hot_path_available"] = False
            result["reason"] = "python_bridge_diagnostic_only"
            result["probe_skipped"] = "python_bridge_status_probe_disabled"
            result["last_error"] = (
                "python bridge starts Python/InsightFace per image and is too slow for production inference; "
                "a native C++ inference backend is required"
            )
            return result
        if result.get("backend") == "skeleton":
            result["inference_available"] = False
            result["hot_path_available"] = False
            result["reason"] = "skeleton_no_inference"
            result["last_error"] = "native face processor skeleton does not run inference"
            return result
        if probe_name:
            probe = self._run_simple([str(path), "probe", "--model-root", str(probe_root), "--model-name", probe_name])
            result["probe_result"] = probe
            if not probe["ok"]:
                result["reason"] = "probe_failed"
                result["last_error"] = probe.get("output", "")
                return result
            probe_output = str(probe.get("output") or "").lower()
            if "heif_decoder=available" in probe_output:
                result["heif_decoder_available"] = True
            elif "heif_decoder=unavailable" in probe_output:
                result["heif_decoder_available"] = False
            if "skeleton" in probe_output:
                result["backend"] = "skeleton"
            elif "python-bridge" in probe_output or "python_bridge" in probe_output:
                result["backend"] = "python_bridge"
            elif "onnxruntime-smoke" in probe_output or "onnxruntime_smoke" in probe_output:
                result["backend"] = "onnxruntime_smoke"
        if result.get("backend") == "python_bridge":
            if not self._python_bridge_debug_enabled():
                result["inference_available"] = False
                result["hot_path_available"] = False
                result["reason"] = "python_bridge_disabled"
                result["last_error"] = (
                    "python bridge is disabled by default and only enabled when BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED is true"
                )
                return result
            result["inference_available"] = False
            result["hot_path_available"] = False
            result["reason"] = "python_bridge_diagnostic_only"
            result["last_error"] = (
                "python bridge starts Python/InsightFace per image and is too slow for production inference; "
                "a native C++ inference backend is required"
            )
            return result
        if result.get("backend") == "onnxruntime_smoke":
            result["inference_available"] = False
            result["hot_path_available"] = False
            result["reason"] = "onnxruntime_smoke_only"
            result["last_error"] = (
                "ONNXRuntime C++ sessions are available, but SCRFD/ArcFace preprocessing and postprocessing "
                "are not complete yet"
            )
            return result
        result["inference_available"] = True
        result["hot_path_available"] = True
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
                env=self._processor_env(),
            )
        except Exception as exc:
            return {"ok": False, "output": f"{type(exc).__name__}: {exc}"}
        return {"ok": completed.returncode == 0, "returncode": completed.returncode, "output": completed.stdout.strip()}

    def run_faces(self, command: str, image_path: Path, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        executable = self.executable_path()
        started_at = time.monotonic()
        image_path = Path(image_path)
        processor_image_path = image_path
        image_hash = hashlib.sha256(str(image_path).encode("utf-8", errors="replace")).hexdigest()[:16]
        self._debug_log(
            "native_face_processor_run_start",
            command=command,
            image_path_hash=image_hash,
            executable=str(executable),
            **self._ort_environment_config(),
        )
        with tempfile.TemporaryDirectory(prefix="av-imgdata-native-face-") as tmpdir:
            workdir = Path(tmpdir)
            input_path = workdir / "job-input.json"
            output_path = workdir / "processor-result.json"
            decoded_input = self._decode_processor_input(image_path, workdir, image_hash=image_hash, command=command)
            if decoded_input is not None:
                processor_image_path = decoded_input
            input_path.write_text(
                json.dumps(self._job_input(command, processor_image_path, options, source_id=image_path), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            completed = self._run_processor_command(executable, command, input_path, output_path, workdir, self._worker_model_key(options))
            payload: Optional[Dict[str, Any]] = None
            result_json_error = ""
            if output_path.exists():
                try:
                    parsed_payload = json.loads(output_path.read_text(encoding="utf-8"))
                    payload = parsed_payload if isinstance(parsed_payload, dict) else None
                    if payload is None:
                        result_json_error = "native result JSON is not an object"
                except Exception as exc:
                    result_json_error = f"invalid_result_json: {exc}"
            if completed.returncode != 0:
                native_error = self._payload_error(payload)
                output = (completed.stdout or "").strip()
                error_summary = self._format_native_error(native_error) or output or result_json_error
                self._debug_log(
                    "native_face_processor_run_failed",
                    command=command,
                    image_path_hash=image_hash,
                    returncode=completed.returncode,
                    duration_ms=round((time.monotonic() - started_at) * 1000, 2),
                    output=output[-500:],
                    result_status=str(payload.get("status") or "") if isinstance(payload, dict) else "",
                    error_code=str(native_error.get("code") or "") if native_error else "",
                    error_message=str(native_error.get("message") or "")[-500:] if native_error else "",
                    processor_backend=(payload.get("processor") or {}).get("backend") if isinstance(payload, dict) and isinstance(payload.get("processor"), dict) else "",
                    result_json_error=result_json_error,
                )
                raise NativeFaceProcessorUnavailable(
                    f"native face processor {command} failed with exit {completed.returncode}: {error_summary}"
                )
            if payload is None:
                self._debug_log(
                    "native_face_processor_run_failed",
                    command=command,
                    image_path_hash=image_hash,
                    returncode=completed.returncode,
                    duration_ms=round((time.monotonic() - started_at) * 1000, 2),
                    output=result_json_error or "native result JSON is missing",
                )
                raise NativeFaceProcessorUnavailable(
                    f"native face processor did not write valid result JSON: {result_json_error or 'missing result file'}"
                )
        faces = self._normalize_faces(payload)
        native_timing = self._payload_timing(payload)
        self._debug_log(
            "native_face_processor_run_finished",
            command=command,
            image_path_hash=image_hash,
            returncode=completed.returncode,
            duration_ms=round((time.monotonic() - started_at) * 1000, 2),
            faces_count=len(faces),
            processor_backend=(payload.get("processor") or {}).get("backend") if isinstance(payload, dict) and isinstance(payload.get("processor"), dict) else "",
            native_timing_ms=native_timing,
            native_total_ms=native_timing.get("total"),
            native_image_decode_ms=native_timing.get("image_decode"),
            native_model_load_ms=native_timing.get("model_load"),
            native_detector_prepare_ms=native_timing.get("detector_prepare"),
            native_detector_run_ms=native_timing.get("detector_run"),
            native_detector_decode_ms=native_timing.get("detector_decode"),
            native_recognizer_prepare_ms=native_timing.get("recognizer_prepare"),
            native_recognizer_run_ms=native_timing.get("recognizer_run"),
            native_recognizer_runs=native_timing.get("recognizer_runs"),
            native_recognized_faces=native_timing.get("recognized_faces"),
            native_recognizer_batch_size=native_timing.get("recognizer_batch_size"),
            native_recognizer_batched=native_timing.get("recognizer_batched"),
            native_recognizer_batch_fallback=native_timing.get("recognizer_batch_fallback"),
            native_reused_models=native_timing.get("reused_models"),
        )
        return faces

    @staticmethod
    def _payload_error(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        error = payload.get("error")
        return error if isinstance(error, dict) else {}

    @staticmethod
    def _format_native_error(error: Dict[str, Any]) -> str:
        if not error:
            return ""
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        if code and message:
            return f"{code}: {message}"
        return message or code

    @staticmethod
    def _payload_timing(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        timing = payload.get("timing_ms")
        if not isinstance(timing, dict):
            return {}
        normalized: Dict[str, Any] = {}
        for key, value in timing.items():
            text_key = str(key or "").strip()
            if not text_key:
                continue
            if isinstance(value, bool):
                normalized[text_key] = value
                continue
            try:
                number = float(value)
            except Exception:
                continue
            if text_key.endswith("_runs") or text_key.endswith("_size") or text_key == "recognized_faces":
                normalized[text_key] = int(number)
            else:
                normalized[text_key] = round(number, 2)
        return normalized

    def _decode_processor_input(self, image_path: Path, workdir: Path, *, image_hash: str, command: str) -> Optional[Path]:
        if image_path.suffix.lower().lstrip(".") not in self._decoder_extensions():
            return None
        decoder = getattr(self, "image_decoder", None)
        if decoder is None or not hasattr(decoder, "decode_to_jpeg"):
            return None
        try:
            decoded = decoder.decode_to_jpeg(str(image_path))
        except Exception as exc:
            self._debug_log(
                "native_face_processor_input_decode_failed",
                command=command,
                image_path_hash=image_hash,
                source="image_decoder",
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        if not getattr(decoded, "success", False) or not getattr(decoded, "image_bytes", b""):
            error = str(getattr(decoded, "error", "") or "")
            if error and error not in {"image_decoder_extension_not_enabled", "image_decoder_disabled"}:
                self._debug_log(
                    "native_face_processor_input_decode_failed",
                    command=command,
                    image_path_hash=image_hash,
                    source=str(getattr(decoded, "source", "") or "image_decoder"),
                    error=error,
                )
            return None
        decoded_path = workdir / "decoded-input.jpg"
        decoded_path.write_bytes(getattr(decoded, "image_bytes"))
        self._debug_log(
            "native_face_processor_input_decoded",
            command=command,
            image_path_hash=image_hash,
            source=str(getattr(decoded, "source", "") or "image_decoder"),
            decoded_suffix=decoded_path.suffix,
            decoded_bytes=decoded_path.stat().st_size,
        )
        return decoded_path

    def _decoder_extensions(self) -> List[str]:
        try:
            root = self.config_service.readMergedConfig()
        except Exception:
            root = {}
        files = root.get("files") if isinstance(root.get("files"), dict) else {}
        raw = files.get("IMAGE_DECODER_EXTENSIONS")
        source = raw if isinstance(raw, list) else ["heic", "heif"]
        normalized: List[str] = []
        for item in source:
            text = str(item or "").strip().lower().lstrip(".")
            if text and text not in normalized:
                normalized.append(text)
        return normalized or ["heic", "heif"]

    def _worker_model_key(self, options: Dict[str, Any]) -> Tuple[Any, ...]:
        return (
            str(self.executable_path()),
            str(options.get("model_root") or ""),
            str(options.get("model_name") or ""),
            tuple(sorted(self._ort_environment_config().items())),
        )

    def _run_processor_command(
        self,
        executable: Path,
        command: str,
        input_path: Path,
        output_path: Path,
        workdir: Path,
        worker_key: Tuple[Any, ...],
    ) -> subprocess.CompletedProcess:
        worker_result = self._try_worker_command(command, input_path, output_path, worker_key)
        if worker_result is not None:
            return worker_result
        return subprocess.run(
            [str(executable), command, "--input", str(input_path), "--output", str(output_path), "--workdir", str(workdir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=self.timeout_seconds(),
            env=self._processor_env(),
        )

    def _try_worker_command(
        self,
        command: str,
        input_path: Path,
        output_path: Path,
        worker_key: Tuple[Any, ...],
    ) -> Optional[subprocess.CompletedProcess]:
        timeout = self.timeout_seconds()
        request_id = hashlib.sha256(f"{input_path}:{time.monotonic()}".encode("utf-8")).hexdigest()[:16]
        with self._worker_lock:
            process = self._ensure_worker(worker_key)
            if process is None or process.stdin is None or process.stdout is None:
                return None
            request = {
                "request_id": request_id,
                "command": command,
                "input": str(input_path),
                "output": str(output_path),
            }
            try:
                process.stdin.write(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._debug_log("native_face_processor_worker_unavailable", reason=f"write_failed:{exc}")
                self._stop_worker_locked()
                return None
            ready, _, _ = select.select([process.stdout], [], [], timeout)
            if not ready:
                self._debug_log("native_face_processor_worker_timeout", command=command, timeout_seconds=timeout)
                self._stop_worker_locked()
                raise subprocess.TimeoutExpired([str(worker_key[0]), "worker"], timeout)
            line = process.stdout.readline()
            if not line:
                returncode = process.poll()
                self._debug_log("native_face_processor_worker_unavailable", reason=f"closed:{returncode}")
                self._stop_worker_locked()
                return None
            try:
                response = json.loads(line)
            except Exception as exc:
                self._debug_log("native_face_processor_worker_unavailable", reason=f"invalid_response:{exc}", output=line[-500:])
                self._stop_worker_locked()
                return None
            if str(response.get("request_id") or "") != request_id:
                self._debug_log("native_face_processor_worker_unavailable", reason="request_id_mismatch", output=line[-500:])
                self._stop_worker_locked()
                return None
            return subprocess.CompletedProcess(
                args=[str(worker_key[0]), "worker", command],
                returncode=int(response.get("returncode") or 0),
                stdout="",
                stderr=None,
            )

    def _ensure_worker(self, worker_key: Tuple[Any, ...]) -> Optional[Any]:
        if self._worker_process is not None and self._worker_process.poll() is None and self._worker_key == worker_key:
            return self._worker_process
        self._stop_worker_locked()
        executable = str(worker_key[0])
        try:
            self._worker_process = subprocess.Popen(
                [executable, "worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=self._processor_env(),
            )
        except Exception as exc:
            self._debug_log("native_face_processor_worker_unavailable", reason=f"start_failed:{type(exc).__name__}: {exc}")
            self._worker_process = None
            self._worker_key = None
            return None
        self._worker_key = worker_key
        self._debug_log("native_face_processor_worker_started", executable=executable, **self._ort_environment_config())
        return self._worker_process

    def _stop_worker_locked(self) -> None:
        process = self._worker_process
        self._worker_process = None
        self._worker_key = None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            pass

    def _job_input(self, command: str, image_path: Path, options: Dict[str, Any], *, source_id: Optional[Path] = None) -> Dict[str, Any]:
        return {
            "contract_version": self.CONTRACT_VERSION,
            "job_id": str(options.get("job_id") or "local"),
            "type": f"face_native_{command}",
            "input": {
                "image_path": str(image_path),
                "source_id": str(options.get("source_id") or source_id or image_path),
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
