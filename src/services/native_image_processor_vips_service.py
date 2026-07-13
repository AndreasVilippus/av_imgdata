#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class NativeImageProcessorVipsUnavailable(Exception):
    """Exception raised when native vips processor is unavailable."""
    pass


class NativeImageProcessorVipsService:
    """Status adapter for the optional libvips image processor executable."""

    def __init__(
        self,
        config_service: Any,
        *,
        package_root: Optional[Path] = None,
        debug_logger: Optional[Callable[..., None]] = None,
    ):
        self.config_service = config_service
        self.package_root = Path(package_root) if package_root else Path(os.getenv("SYNOPKG_PKGDEST", "/var/packages/AV_ImgData/target"))
        self._debug_logger = debug_logger if callable(debug_logger) else None
        self._status_lock = threading.Lock()
        self._status_cache: Optional[Tuple[Tuple[Any, ...], float, Dict[str, Any]]] = None
        self._status_refreshing = False

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
        config = processors.get("IMAGE_PROCESSOR_VIPS") if isinstance(processors.get("IMAGE_PROCESSOR_VIPS"), dict) else {}
        return config

    def enabled(self) -> bool:
        return bool(self.config().get("ENABLED", False))

    def executable_path(self) -> Path:
        configured = str(self.config().get("PATH") or "bin/av-imgdata-image-processor").strip()
        path = Path(configured)
        if path.is_absolute():
            return path
        return (self.package_root / path).resolve()

    def timeout_seconds(self) -> int:
        try:
            return max(1, min(3600, int(self.config().get("TIMEOUT_SECONDS", 120))))
        except Exception:
            return 120

    def supported_formats(self) -> List[str]:
        source = self.config().get("SUPPORTED_FORMATS")
        raw = source if isinstance(source, list) else ["jpeg", "jpg", "png", "webp", "tiff", "heic", "heif"]
        formats: List[str] = []
        for item in raw:
            text = str(item or "").strip().lower().lstrip(".")
            if text and text not in formats:
                formats.append(text)
        return formats

    def status(self, *, force: bool = False, background: bool = False) -> Dict[str, Any]:
        processor_config = self.config()
        path = self.executable_path()
        enabled = bool(processor_config.get("ENABLED", False))
        cache_key = self._status_cache_key(processor_config, path)
        if not force:
            cached = self._cached_status(cache_key)
            if cached is not None:
                return cached
            if background:
                stale = self._cached_status(cache_key, allow_stale=True)
                self.refresh_status_background()
                if stale is not None:
                    return stale
                return self._status_pending(processor_config, path)
        result: Dict[str, Any] = {
            "enabled": enabled,
            "preferred": bool(processor_config.get("PREFERRED", True)),
            "path": str(path),
            "present": path.is_file(),
            "executable": os.access(str(path), os.X_OK),
            "available": False,
            "reason": "vips_disabled" if not enabled else "",
            "backend": "libvips",
            "formats": {name: False for name in self.supported_formats()},
            "fallback": "default_image_backend" if bool(processor_config.get("ALLOW_FALLBACK_TO_DEFAULT", True)) else "none",
        }
        if not enabled:
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)
        if not result["present"]:
            result["reason"] = "vips_binary_missing"
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)
        if not result["executable"]:
            result["reason"] = "vips_binary_not_executable"
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)

        version = self._run_simple([str(path), "version"])
        result["version_result"] = version
        if not version["ok"]:
            result["reason"] = "vips_version_failed"
            result["last_error"] = version.get("output", "")
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)
        result["version"] = version.get("output", "").strip()

        probe = self._run_simple([str(path), "probe"])
        result["probe_result"] = probe
        parsed = self._parse_json_line(probe.get("output", ""))
        if isinstance(parsed, dict):
            result["probe"] = parsed
            backend = str(parsed.get("backend") or "").strip()
            if backend:
                result["backend"] = backend
            probe_formats = parsed.get("formats")
            if isinstance(probe_formats, dict):
                result["formats"] = {
                    str(key): bool(value)
                    for key, value in probe_formats.items()
                    if str(key or "").strip()
                }
        if not probe["ok"]:
            result["reason"] = "vips_probe_failed"
            result["last_error"] = probe.get("output", "")
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)

        if str(result.get("backend") or "").strip().lower() in {"skeleton", "no-op", "noop"}:
            result["reason"] = "vips_probe_failed"
            result["last_error"] = "libvips image processor skeleton is present but libvips is not linked"
            self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
            return self._store_status_cache(cache_key, result)

        result["available"] = True
        result["reason"] = "vips_ready"
        self._debug_log("native_image_processor_vips_status", **self._status_debug_fields(result))
        return self._store_status_cache(cache_key, result)

    def _status_cache_ttl_seconds(self, processor_config: Dict[str, Any]) -> float:
        try:
            return max(0.0, min(3600.0, float(processor_config.get("STATUS_CACHE_SECONDS", 60))))
        except Exception:
            return 60.0

    def _status_cache_key(self, processor_config: Dict[str, Any], path: Path) -> Tuple[Any, ...]:
        return (
            str(path),
            path.is_file(),
            os.access(str(path), os.X_OK),
            self._path_cache_identity(path),
            bool(processor_config.get("ENABLED", False)),
            bool(processor_config.get("PREFERRED", True)),
            bool(processor_config.get("ALLOW_FALLBACK_TO_DEFAULT", True)),
            tuple(self.supported_formats()),
            str(processor_config.get("TIMEOUT_SECONDS") or ""),
            self._status_cache_ttl_seconds(processor_config),
        )

    @staticmethod
    def _path_cache_identity(path: Path) -> Tuple[int, int]:
        try:
            stat = path.stat()
        except OSError:
            return (0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _cached_status(self, cache_key: Tuple[Any, ...], *, allow_stale: bool = False) -> Optional[Dict[str, Any]]:
        with self._status_lock:
            cached = self._status_cache
            if cached is None:
                return None
            cached_key, cached_at, cached_value = cached
            if cached_key != cache_key:
                return None
            ttl = float(cache_key[-1] or 0.0)
            expired = ttl <= 0 or time.monotonic() - cached_at > ttl
            if expired and not allow_stale:
                return None
            result = dict(cached_value)
            result["cache_hit"] = not expired
            result["cache_stale"] = bool(expired)
            return result

    def _store_status_cache(self, cache_key: Tuple[Any, ...], status: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(status)
        result["cache_hit"] = False
        result["cache_stale"] = False
        with self._status_lock:
            self._status_cache = (cache_key, time.monotonic(), dict(result))
        return result

    def _status_pending(self, processor_config: Dict[str, Any], path: Path) -> Dict[str, Any]:
        enabled = bool(processor_config.get("ENABLED", False))
        return {
            "enabled": enabled,
            "preferred": bool(processor_config.get("PREFERRED", True)),
            "path": str(path),
            "present": path.is_file(),
            "executable": os.access(str(path), os.X_OK),
            "available": False,
            "reason": "status_refreshing" if enabled else "vips_disabled",
            "backend": "libvips",
            "formats": {name: False for name in self.supported_formats()},
            "fallback": "default_image_backend" if bool(processor_config.get("ALLOW_FALLBACK_TO_DEFAULT", True)) else "none",
            "cache_hit": False,
            "cache_stale": True,
            "refreshing": True,
        }

    def refresh_status_background(self) -> bool:
        with self._status_lock:
            if self._status_refreshing:
                return False
            self._status_refreshing = True

        def refresh() -> None:
            try:
                self.status(force=True, background=False)
            except Exception as exc:
                self._debug_log("native_image_processor_vips_status_refresh_failed", error_type=type(exc).__name__, error=str(exc))
            finally:
                with self._status_lock:
                    self._status_refreshing = False

        thread = threading.Thread(target=refresh, name="av-imgdata-vips-status-refresh", daemon=True)
        thread.start()
        return True

    @staticmethod
    def _status_debug_fields(status: Dict[str, Any]) -> Dict[str, Any]:
        fields = {
            "enabled": bool(status.get("enabled", False)),
            "available": bool(status.get("available", False)),
            "present": bool(status.get("present", False)),
            "executable": bool(status.get("executable", False)),
            "reason": str(status.get("reason") or ""),
            "backend": str(status.get("backend") or ""),
            "path": str(status.get("path") or ""),
            "version": str(status.get("version") or ""),
            "fallback": str(status.get("fallback") or ""),
        }
        last_error = str(status.get("last_error") or "")
        if last_error:
            fields["last_error"] = last_error[-500:]
        probe = status.get("probe")
        if isinstance(probe, dict):
            error = probe.get("error")
            if isinstance(error, dict):
                fields["probe_error_code"] = str(error.get("code") or "")
                fields["probe_error_message"] = str(error.get("message") or "")[-300:]
        return fields

    @staticmethod
    def _parse_json_line(output: str) -> Optional[Dict[str, Any]]:
        for line in str(output or "").splitlines():
            text = line.strip()
            if not text.startswith("{"):
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _run_simple(self, argv: List[str]) -> Dict[str, Any]:
        try:
            completed = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout_seconds(),
            )
        except Exception as exc:
            output = f"{type(exc).__name__}: {exc}"
            self._debug_log("native_image_processor_vips_run_failed", command=argv[1] if len(argv) > 1 else "", output=output)
            return {"ok": False, "returncode": -1, "output": output}
        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            self._debug_log(
                "native_image_processor_vips_run_failed",
                command=argv[1] if len(argv) > 1 else "",
                returncode=completed.returncode,
                output=output[-500:],
            )
        return {"ok": completed.returncode == 0, "returncode": completed.returncode, "output": output}

    def _processor_env(self) -> Dict[str, str]:
        """Get environment for subprocess with libvips library paths."""
        env = os.environ.copy()
        lib_path = str(self.package_root / "lib")
        if "LD_LIBRARY_PATH" in env:
            env["LD_LIBRARY_PATH"] = f"{lib_path}:" + env["LD_LIBRARY_PATH"]
        else:
            env["LD_LIBRARY_PATH"] = lib_path
        return env

    def process_image(
        self,
        image_path: Path,
        operation: str,
        options: Dict[str, Any],
        output_format: str = "jpeg",
    ) -> Dict[str, Any]:
        """
        Process an image using the native libvips processor.
        
        Args:
            image_path: Path to input image
            operation: Operation name (resize, rotate, convert, auto-orient)
            options: Operation-specific options
            output_format: Output image format (jpeg, png, webp, tiff)
            
        Returns:
            Dictionary with result or error information
        """
        if not self.enabled():
            return {"success": False, "error": "vips_processor_disabled"}
        
        status = self.status()
        if not status.get("available"):
            return {"success": False, "error": status.get("reason", "vips_unavailable")}
        
        image_path = Path(image_path)
        if not image_path.exists():
            return {"success": False, "error": "image_not_found"}
        
        supported_fmts = self.supported_formats()
        if output_format.lower() not in supported_fmts:
            return {"success": False, "error": f"unsupported_format:{output_format}"}
        
        try:
            with tempfile.TemporaryDirectory(prefix="av-imgdata-vips-") as tmpdir:
                workdir = Path(tmpdir)
                input_data = self._job_input(image_path, operation, options, output_format)
                input_path = workdir / "job-input.json"
                output_path = workdir / "processor-result.json"
                
                input_path.write_text(
                    json.dumps(input_data, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                
                result = self._run_processor_command(
                    [str(self.executable_path()), "process"],
                    input_path,
                    output_path,
                    workdir,
                )
                
                return self._parse_processor_result(result, output_path)
        except Exception as exc:
            self._debug_log("vips_process_image_failed", error=str(exc))
            return {"success": False, "error": f"processor_error:{type(exc).__name__}"}

    def resize_image(
        self,
        image_path: Path,
        width: int,
        height: int,
        output_format: str = "jpeg",
        quality: int = 95,
    ) -> Dict[str, Any]:
        """Resize image to specified dimensions."""
        return self.process_image(
            image_path,
            "resize",
            {"width": width, "height": height, "quality": quality},
            output_format,
        )

    def rotate_image(
        self,
        image_path: Path,
        angle: int,
        output_format: str = "jpeg",
    ) -> Dict[str, Any]:
        """Rotate image by specified angle (90, 180, 270)."""
        if angle not in {90, 180, 270}:
            return {"success": False, "error": f"invalid_rotation_angle:{angle}"}
        return self.process_image(
            image_path,
            "rotate",
            {"angle": angle},
            output_format,
        )

    def auto_orient_image(
        self,
        image_path: Path,
        output_format: str = "jpeg",
    ) -> Dict[str, Any]:
        """Auto-orient image based on EXIF orientation."""
        return self.process_image(
            image_path,
            "auto-orient",
            {},
            output_format,
        )

    def convert_image(
        self,
        image_path: Path,
        output_format: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert image to a different format."""
        opts = options or {"quality": 95}
        return self.process_image(image_path, "convert", opts, output_format)

    def batch_process_images(
        self,
        image_paths: List[Path],
        operation: str,
        options: Dict[str, Any],
        output_format: str = "jpeg",
    ) -> List[Dict[str, Any]]:
        """
        Process multiple images with the same operation.
        
        Returns:
            List of result dictionaries, one per input image
        """
        paths = [Path(path) for path in image_paths]
        if not paths:
            return []
        if not self.enabled():
            return [{"path": str(path), "success": False, "error": "vips_processor_disabled"} for path in paths]
        status = self.status()
        if not status.get("available"):
            error = status.get("reason", "vips_unavailable")
            return [{"path": str(path), "success": False, "error": error} for path in paths]
        supported_fmts = self.supported_formats()
        if output_format.lower() not in supported_fmts:
            return [{"path": str(path), "success": False, "error": f"unsupported_format:{output_format}"} for path in paths]

        missing = {str(path) for path in paths if not path.exists()}
        runnable_paths = [path for path in paths if str(path) not in missing]
        results_by_path: Dict[str, Dict[str, Any]] = {
            path: {"path": path, "success": False, "error": "image_not_found"}
            for path in missing
        }
        if runnable_paths:
            try:
                with tempfile.TemporaryDirectory(prefix="av-imgdata-vips-batch-") as tmpdir:
                    workdir = Path(tmpdir)
                    input_data = self._batch_job_input(runnable_paths, operation, options, output_format)
                    input_path = workdir / "job-input.json"
                    output_path = workdir / "processor-result.json"
                    input_path.write_text(
                        json.dumps(input_data, ensure_ascii=False, sort_keys=True),
                        encoding="utf-8",
                    )
                    exec_result = self._run_processor_command(
                        [str(self.executable_path()), "process-batch"],
                        input_path,
                        output_path,
                        workdir,
                    )
                    batch_results = self._parse_batch_processor_result(exec_result, output_path)
                    for item in batch_results:
                        item_path = str(item.get("path") or item.get("image_path") or "")
                        if item_path:
                            results_by_path[item_path] = item
            except Exception as exc:
                self._debug_log("vips_batch_process_images_failed", error=str(exc))
                for path in runnable_paths:
                    results_by_path[str(path)] = {"path": str(path), "success": False, "error": f"processor_error:{type(exc).__name__}"}

        return [
            {"path": str(path), **{key: value for key, value in results_by_path.get(str(path), {"success": False, "error": "missing_batch_result"}).items() if key != "path"}}
            for path in paths
        ]

    @staticmethod
    def _job_input(
        image_path: Path,
        operation: str,
        options: Dict[str, Any],
        output_format: str,
    ) -> Dict[str, Any]:
        """Create job input JSON structure for processor."""
        return {
            "contract_version": "1.0",
            "image_path": str(image_path),
            "operation": operation,
            "output_format": output_format,
            "options": options,
            "timestamp": time.time(),
        }

    @staticmethod
    def _batch_job_input(
        image_paths: List[Path],
        operation: str,
        options: Dict[str, Any],
        output_format: str,
    ) -> Dict[str, Any]:
        """Create batch job input JSON structure for processor."""
        return {
            "contract_version": "1.0",
            "image_paths": [str(path) for path in image_paths],
            "operation": operation,
            "output_format": output_format,
            "options": options,
            "timestamp": time.time(),
        }

    def _run_processor_command(
        self,
        command: List[str],
        input_path: Path,
        output_path: Path,
        workdir: Path,
    ) -> Dict[str, Any]:
        """Execute processor command with input/output files."""
        try:
            argv = command + [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--workdir",
                str(workdir),
            ]
            completed = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout_seconds(),
                env=self._processor_env(),
            )
            return {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "output": (completed.stdout or "").strip(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "returncode": -1,
                "output": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _parse_processor_result(
        exec_result: Dict[str, Any],
        output_path: Path,
    ) -> Dict[str, Any]:
        """Parse processor result from JSON output file."""
        result: Dict[str, Any] = {"success": exec_result.get("ok", False)}
        
        if output_path.exists():
            try:
                parsed = json.loads(output_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    result.update(parsed)
                    image_output_path = parsed.get("output_path")
                    if isinstance(image_output_path, str) and image_output_path:
                        try:
                            image_path = Path(image_output_path)
                            if image_path.is_file():
                                result["image_bytes"] = image_path.read_bytes()
                        except OSError:
                            pass
                    return result
            except Exception:
                pass
        
        if not result["success"]:
            result["error"] = result.get("error", exec_result.get("output", "processor_error"))
        
        return result

    @staticmethod
    def _parse_batch_processor_result(
        exec_result: Dict[str, Any],
        output_path: Path,
    ) -> List[Dict[str, Any]]:
        if output_path.exists():
            try:
                parsed = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                raw_results = parsed.get("results") if isinstance(parsed.get("results"), list) else []
                results: List[Dict[str, Any]] = []
                for item in raw_results:
                    if not isinstance(item, dict):
                        continue
                    result = dict(item)
                    image_output_path = result.get("output_path")
                    if isinstance(image_output_path, str) and image_output_path:
                        try:
                            image_path = Path(image_output_path)
                            if image_path.is_file():
                                result["image_bytes"] = image_path.read_bytes()
                        except OSError:
                            pass
                    results.append(result)
                if results:
                    return results
        error = exec_result.get("output", "processor_error")
        return [{"success": False, "error": error}]

    def get_image_info(self, image_path: Path) -> Dict[str, Any]:
        """Get image information (dimensions, format, metadata)."""
        if not self.enabled():
            return {"success": False, "error": "vips_processor_disabled"}
        
        status = self.status()
        if not status.get("available"):
            return {"success": False, "error": "vips_unavailable"}
        
        image_path = Path(image_path)
        if not image_path.exists():
            return {"success": False, "error": "image_not_found"}
        
        try:
            with tempfile.TemporaryDirectory(prefix="av-imgdata-vips-") as tmpdir:
                workdir = Path(tmpdir)
                input_data = {
                    "contract_version": "1.0",
                    "image_path": str(image_path),
                    "operation": "info",
                    "timestamp": time.time(),
                }
                input_path = workdir / "job-input.json"
                output_path = workdir / "processor-result.json"
                
                input_path.write_text(
                    json.dumps(input_data, ensure_ascii=False),
                    encoding="utf-8",
                )
                
                result = self._run_processor_command(
                    [str(self.executable_path()), "info"],
                    input_path,
                    output_path,
                    workdir,
                )
                
                return self._parse_processor_result(result, output_path)
        except Exception as exc:
            return {"success": False, "error": f"processor_error:{exc}"}


class NativeImageProcessor:
    """Processor interface for native libvips image operations."""

    def __init__(
        self,
        service: NativeImageProcessorVipsService,
        image_path: Path,
        output_format: str = "jpeg",
        quality: int = 95,
    ):
        """
        Initialize processor for an image.
        
        Args:
            service: NativeImageProcessorVipsService instance
            image_path: Path to image to process
            output_format: Output format (jpeg, png, webp, tiff)
            quality: JPEG/WebP quality (1-100)
        """
        self.service = service
        self.image_path = Path(image_path)
        self.output_format = output_format
        self.quality = max(1, min(100, quality))
        self._status_cache: Optional[Dict[str, Any]] = None

    @property
    def is_available(self) -> bool:
        """Check if processor is available."""
        status = self.service.status()
        return status.get("available", False)

    def info(self) -> Dict[str, Any]:
        """Get image information."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        return self.service.get_image_info(self.image_path)

    def resize(self, width: int, height: int) -> Dict[str, Any]:
        """Resize to specific dimensions."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        return self.service.resize_image(
            self.image_path,
            width,
            height,
            self.output_format,
            self.quality,
        )

    def rotate(self, angle: int) -> Dict[str, Any]:
        """Rotate by angle (90, 180, 270)."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        return self.service.rotate_image(self.image_path, angle, self.output_format)

    def auto_orient(self) -> Dict[str, Any]:
        """Auto-orient based on EXIF metadata."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        return self.service.auto_orient_image(self.image_path, self.output_format)

    def convert(self, output_format: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convert to different format."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        opts = options or {"quality": self.quality}
        return self.service.convert_image(self.image_path, output_format, opts)

    def process(
        self,
        operation: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute custom operation."""
        if not self.is_available:
            raise NativeImageProcessorVipsUnavailable("libvips processor not available")
        return self.service.process_image(
            self.image_path,
            operation,
            options,
            self.output_format,
        )
