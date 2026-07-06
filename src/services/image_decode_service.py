#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.config_service import ConfigService


@dataclass
class ImageDecodeResult:
    success: bool
    image_bytes: bytes = b""
    source: str = ""
    error: str = ""


class ImageDecodeService:
    """Decode image formats that OpenCV cannot read directly via optional tools."""

    def __init__(
        self,
        config_service: Optional[ConfigService] = None,
        *,
        debug_logger: Optional[Callable[..., None]] = None,
        vips_processor: Optional[Any] = None,
    ):
        self._config = config_service or ConfigService()
        self._debug_logger = debug_logger if callable(debug_logger) else None
        self._vips_processor = vips_processor

    def set_debug_logger(self, debug_logger: Optional[Callable[..., None]]) -> None:
        self._debug_logger = debug_logger if callable(debug_logger) else None
        processor = getattr(self, "_vips_processor", None)
        if processor is not None and hasattr(processor, "set_debug_logger"):
            try:
                processor.set_debug_logger(self._debug_logger)
            except Exception:
                pass

    def _debug_log(self, event: str, **fields: Any) -> None:
        logger = self._debug_logger
        if not callable(logger):
            return
        try:
            logger(event, **fields)
        except Exception:
            pass

    def decode_to_jpeg(self, image_path: str) -> ImageDecodeResult:
        path = Path(image_path)
        root_config = self._root_config()
        config = self._files_config(root_config)
        if not bool(config.get("IMAGE_DECODER_ENABLED", True)):
            return ImageDecodeResult(False, error="image_decoder_disabled")
        if not path.is_file():
            return ImageDecodeResult(False, error="image_not_found")
        extension = path.suffix.lower().lstrip(".")
        extensions = self._decoder_extensions(root_config, config)
        if extension not in extensions:
            return ImageDecodeResult(False, error="image_decoder_extension_not_enabled")

        errors: List[str] = []
        decoder_order = self._preferred_decoder_order(root_config, config)
        for decoder in decoder_order:
            if decoder in {"libvips", "vips"}:
                result = self._decode_with_vips(path, root_config, config)
                if result.success:
                    return result
                if result.error:
                    errors.append(f"libvips:{result.error}")
                if not self._vips_fallback_allowed(root_config):
                    return ImageDecodeResult(False, source="libvips", error="; ".join(errors) or "vips_decode_failed")
                continue
            if decoder == "pillow-heif":
                result = self._decode_with_pillow_heif(path, self._max_edge(config))
                if result.success:
                    return result
                if result.error:
                    errors.append(f"{decoder}:{result.error}")
                continue
            result = self._decode_with(decoder, path, config)
            if result.success:
                return result
            if result.error:
                errors.append(f"{decoder}:{result.error}")
        return ImageDecodeResult(False, error="; ".join(errors) or "image_decoder_unavailable")

    def decode_many_to_jpeg(self, image_paths: List[str]) -> Dict[str, ImageDecodeResult]:
        paths = [Path(path) for path in image_paths]
        if not paths:
            return {}
        root_config = self._root_config()
        config = self._files_config(root_config)
        if not bool(config.get("IMAGE_DECODER_ENABLED", True)):
            return {str(path): ImageDecodeResult(False, error="image_decoder_disabled") for path in paths}

        results: Dict[str, ImageDecodeResult] = {}
        pending: List[Path] = []
        extensions = self._decoder_extensions(root_config, config)
        for path in paths:
            if not path.is_file():
                results[str(path)] = ImageDecodeResult(False, error="image_not_found")
                continue
            if path.suffix.lower().lstrip(".") not in extensions:
                results[str(path)] = ImageDecodeResult(False, error="image_decoder_extension_not_enabled")
                continue
            pending.append(path)

        decoder_order = self._preferred_decoder_order(root_config, config)
        if pending and decoder_order and decoder_order[0] in {"libvips", "vips"}:
            vips_results = self._decode_many_with_vips(pending, root_config, config)
            for path in list(pending):
                result = vips_results.get(str(path))
                if result is None:
                    continue
                if result.success:
                    results[str(path)] = result
                    pending.remove(path)
                    continue
                if not self._vips_fallback_allowed(root_config):
                    results[str(path)] = result
                    pending.remove(path)

        for path in pending:
            results[str(path)] = self.decode_to_jpeg(str(path))
        return {str(path): results.get(str(path), ImageDecodeResult(False, error="image_decoder_unavailable")) for path in paths}

    def _preferred_decoder_order(self, root_config: Dict[str, Any], files_config: Dict[str, Any]) -> List[str]:
        order = self._string_list(
            files_config.get("IMAGE_DECODER_ORDER"),
            default=["pillow-heif", "heif-convert", "magick", "ffmpeg", "convert"],
        )
        if self._vips_preferred(root_config) and "libvips" not in order and "vips" not in order:
            return ["libvips", *order]
        return order

    def _decoder_extensions(self, root_config: Dict[str, Any], files_config: Dict[str, Any]) -> List[str]:
        extensions = self._string_list(files_config.get("IMAGE_DECODER_EXTENSIONS"), default=["heic", "heif"])
        if self._vips_preferred(root_config):
            for item in self._vips_supported_formats(root_config):
                if item not in extensions:
                    extensions.append(item)
        return extensions

    @staticmethod
    def _vips_config(root_config: Dict[str, Any]) -> Dict[str, Any]:
        processors = root_config.get("native_processors") if isinstance(root_config.get("native_processors"), dict) else {}
        config = processors.get("IMAGE_PROCESSOR_VIPS") if isinstance(processors.get("IMAGE_PROCESSOR_VIPS"), dict) else {}
        return config

    def _vips_preferred(self, root_config: Dict[str, Any]) -> bool:
        config = self._vips_config(root_config)
        return bool(config.get("ENABLED", False)) and bool(config.get("PREFERRED", True))

    def _vips_supported_formats(self, root_config: Dict[str, Any]) -> List[str]:
        config = self._vips_config(root_config)
        return self._string_list(config.get("SUPPORTED_FORMATS"), default=["jpeg", "jpg", "png", "webp", "tiff"])

    def _vips_fallback_allowed(self, root_config: Dict[str, Any]) -> bool:
        config = self._vips_config(root_config)
        return bool(config.get("ALLOW_FALLBACK_TO_DEFAULT", True))

    def _decode_with_vips(self, image_path: Path, root_config: Dict[str, Any], files_config: Dict[str, Any]) -> ImageDecodeResult:
        processor = self._native_vips_processor(root_config)
        if processor is None:
            return ImageDecodeResult(False, source="libvips", error="vips_processor_unavailable")
        supported, reason = self._vips_input_format_supported(processor, image_path.suffix.lower().lstrip("."))
        if not supported:
            self._debug_log("image_decoder_vips_skipped", image_suffix=image_path.suffix.lower(), reason=reason)
            return ImageDecodeResult(False, source="libvips", error=reason)
        max_edge = self._max_edge(files_config)
        options: Dict[str, Any] = {"quality": 95}
        operation = "auto-orient"
        if max_edge > 0:
            operation = "resize"
            options.update({"width": max_edge, "height": max_edge, "maintain_aspect": True})
        try:
            result = processor.process_image(image_path, operation, options, "jpeg")
        except Exception as exc:
            error = f"vips_decode_failed:{type(exc).__name__}: {exc}"
            self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), error=error)
            return ImageDecodeResult(False, source="libvips", error=error)
        image_bytes = result.get("image_bytes") if isinstance(result.get("image_bytes"), bytes) else b""
        output_path = Path(str(result.get("output_path") or ""))
        if not image_bytes and output_path.is_file():
            try:
                image_bytes = output_path.read_bytes()
            except OSError as exc:
                error = f"vips_output_missing:{exc}"
                self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error=error)
                return ImageDecodeResult(False, source="libvips", error=error)
        if not result.get("success") or not image_bytes:
            error = str(result.get("error") or result.get("message") or "vips_decode_failed")
            self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error=error)
            return ImageDecodeResult(False, source="libvips", error=error)
        if not image_bytes.startswith(b"\xff\xd8"):
            self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error="decoder_output_not_jpeg")
            return ImageDecodeResult(False, source="libvips", error="decoder_output_not_jpeg")
        self._debug_log(
            "image_decoder_vips_used",
            image_suffix=image_path.suffix.lower(),
            operation=operation,
            output_bytes=len(image_bytes),
        )
        return ImageDecodeResult(True, image_bytes=image_bytes, source="libvips")

    def _decode_many_with_vips(self, image_paths: List[Path], root_config: Dict[str, Any], files_config: Dict[str, Any]) -> Dict[str, ImageDecodeResult]:
        processor = self._native_vips_processor(root_config)
        if processor is None:
            return {str(path): ImageDecodeResult(False, source="libvips", error="vips_processor_unavailable") for path in image_paths}

        supported_paths: List[Path] = []
        results: Dict[str, ImageDecodeResult] = {}
        for image_path in image_paths:
            supported, reason = self._vips_input_format_supported(processor, image_path.suffix.lower().lstrip("."))
            if supported:
                supported_paths.append(image_path)
            else:
                self._debug_log("image_decoder_vips_skipped", image_suffix=image_path.suffix.lower(), reason=reason)
                results[str(image_path)] = ImageDecodeResult(False, source="libvips", error=reason)
        if not supported_paths:
            return results

        operation, options = self._vips_decode_operation(files_config)
        batch_process = getattr(processor, "batch_process_images", None)
        if not callable(batch_process):
            for image_path in supported_paths:
                results[str(image_path)] = self._decode_with_vips(image_path, root_config, files_config)
            return results
        try:
            batch_results = batch_process(supported_paths, operation, options, "jpeg")
        except Exception as exc:
            error = f"vips_batch_decode_failed:{type(exc).__name__}: {exc}"
            self._debug_log("image_decoder_vips_batch_failed", error=error, images_count=len(supported_paths))
            return {**results, **{str(path): ImageDecodeResult(False, source="libvips", error=error) for path in supported_paths}}

        by_path = {
            str(item.get("path") or item.get("image_path") or ""): item
            for item in batch_results
            if isinstance(item, dict)
        }
        for image_path in supported_paths:
            item = by_path.get(str(image_path), {})
            image_bytes = item.get("image_bytes") if isinstance(item.get("image_bytes"), bytes) else b""
            output_path = Path(str(item.get("output_path") or ""))
            if not image_bytes and output_path.is_file():
                try:
                    image_bytes = output_path.read_bytes()
                except OSError as exc:
                    error = f"vips_output_missing:{exc}"
                    self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error=error)
                    results[str(image_path)] = ImageDecodeResult(False, source="libvips", error=error)
                    continue
            if not item.get("success") or not image_bytes:
                error = str(item.get("error") or item.get("message") or "vips_decode_failed")
                self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error=error)
                results[str(image_path)] = ImageDecodeResult(False, source="libvips", error=error)
                continue
            if not image_bytes.startswith(b"\xff\xd8"):
                self._debug_log("image_decoder_vips_failed", image_suffix=image_path.suffix.lower(), operation=operation, error="decoder_output_not_jpeg")
                results[str(image_path)] = ImageDecodeResult(False, source="libvips", error="decoder_output_not_jpeg")
                continue
            results[str(image_path)] = ImageDecodeResult(True, image_bytes=image_bytes, source="libvips")
        self._debug_log(
            "image_decoder_vips_batch_used",
            operation=operation,
            images_count=len(supported_paths),
            decoded_count=len([result for result in results.values() if result.success and result.source == "libvips"]),
        )
        return results

    def _vips_decode_operation(self, files_config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        max_edge = self._max_edge(files_config)
        options: Dict[str, Any] = {"quality": 95}
        operation = "auto-orient"
        if max_edge > 0:
            operation = "resize"
            options.update({"width": max_edge, "height": max_edge, "maintain_aspect": True})
        return operation, options

    @staticmethod
    def _vips_format_aliases(extension: str) -> List[str]:
        normalized = str(extension or "").strip().lower().lstrip(".")
        aliases = {
            "jpg": ["jpg", "jpeg"],
            "jpeg": ["jpeg", "jpg"],
            "tif": ["tif", "tiff"],
            "tiff": ["tiff", "tif"],
            "heic": ["heic", "heif"],
            "heif": ["heif", "heic"],
        }
        return aliases.get(normalized, [normalized] if normalized else [])

    def _vips_input_format_supported(self, processor: Any, extension: str) -> Tuple[bool, str]:
        aliases = self._vips_format_aliases(extension)
        if not aliases:
            return False, "vips_input_format_unknown"
        try:
            status = processor.status()
        except Exception as exc:
            return False, f"vips_status_failed:{type(exc).__name__}: {exc}"
        if not isinstance(status, dict) or not status.get("available"):
            reason = str(status.get("reason") or "vips_unavailable") if isinstance(status, dict) else "vips_unavailable"
            return False, reason
        formats = status.get("formats")
        if isinstance(formats, dict):
            if any(bool(formats.get(alias)) for alias in aliases):
                return True, "vips_format_supported"
            return False, f"vips_input_format_unsupported:{aliases[0]}"
        return False, "vips_format_probe_missing"

    def _native_vips_processor(self, root_config: Dict[str, Any]) -> Optional[Any]:
        if not self._vips_preferred(root_config):
            return None
        if self._vips_processor is None:
            try:
                from services.native_image_processor_vips_service import NativeImageProcessorVipsService
                self._vips_processor = NativeImageProcessorVipsService(self._config, debug_logger=self._debug_logger)
            except Exception as exc:
                self._debug_log("image_decoder_vips_failed", error=f"vips_processor_init_failed:{type(exc).__name__}: {exc}")
                return None
        return self._vips_processor

    @staticmethod
    def _decode_with_pillow_heif(image_path: Path, max_edge: int = 4096) -> ImageDecodeResult:
        try:
            from PIL import Image
            from pillow_heif import register_heif_opener
        except ImportError as exc:
            return ImageDecodeResult(False, source="pillow-heif", error=f"decoder_not_installed:{exc}")
        try:
            register_heif_opener()
            with Image.open(image_path) as image:
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                if max_edge > 0:
                    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
                    image.thumbnail((max_edge, max_edge), resampling)
                output = BytesIO()
                image.save(output, format="JPEG", quality=95)
        except Exception as exc:
            return ImageDecodeResult(False, source="pillow-heif", error=f"decoder_failed:{type(exc).__name__}: {exc}")
        image_bytes = output.getvalue()
        if not image_bytes.startswith(b"\xff\xd8"):
            return ImageDecodeResult(False, source="pillow-heif", error="decoder_output_not_jpeg")
        return ImageDecodeResult(True, image_bytes=image_bytes, source="pillow-heif")

    def _decode_with(self, decoder: str, image_path: Path, config: Dict[str, Any]) -> ImageDecodeResult:
        executable = self._decoder_executable(decoder, config)
        if not executable:
            return ImageDecodeResult(False, source=decoder, error="decoder_not_found")
        timeout = self._timeout(config)
        with tempfile.TemporaryDirectory(prefix="av_imgdata_decode_") as tmpdir:
            output_path = Path(tmpdir) / "decoded.jpg"
            command = self._decoder_command(decoder, executable, image_path, output_path)
            if not command:
                return ImageDecodeResult(False, source=decoder, error="decoder_not_supported")
            try:
                completed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return ImageDecodeResult(False, source=decoder, error="decoder_timeout")
            except OSError as exc:
                return ImageDecodeResult(False, source=decoder, error=f"decoder_failed:{exc}")
            if completed.returncode != 0:
                stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
                return ImageDecodeResult(False, source=decoder, error=stderr or f"decoder_returncode_{completed.returncode}")
            try:
                image_bytes = output_path.read_bytes()
            except OSError as exc:
                return ImageDecodeResult(False, source=decoder, error=f"decoder_output_missing:{exc}")
            if not image_bytes.startswith(b"\xff\xd8"):
                return ImageDecodeResult(False, source=decoder, error="decoder_output_not_jpeg")
            return ImageDecodeResult(True, image_bytes=image_bytes, source=decoder)

    @staticmethod
    def _decoder_command(decoder: str, executable: str, image_path: Path, output_path: Path) -> List[str]:
        source = str(image_path)
        target = str(output_path)
        if decoder == "heif-convert":
            return [executable, "-q", "95", source, target]
        if decoder in {"magick", "convert"}:
            return [executable, source, "-auto-orient", "-quality", "95", target]
        if decoder == "ffmpeg":
            return [executable, "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-frames:v", "1", target]
        return []

    def _decoder_executable(self, decoder: str, config: Dict[str, Any]) -> str:
        key = {
            "heif-convert": "PATH_HEIF_CONVERT",
            "magick": "PATH_IMAGEMAGICK",
            "ffmpeg": "PATH_FFMPEG",
            "convert": "PATH_CONVERT",
        }.get(decoder)
        configured = str(config.get(key or "") or decoder).strip()
        if not configured:
            configured = decoder
        if os.sep in configured:
            return configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else ""
        return shutil.which(configured) or ""

    def _root_config(self) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
        return config if isinstance(config, dict) else {}

    @staticmethod
    def _files_config(config: Dict[str, Any]) -> Dict[str, Any]:
        return config.get("files", {}) if isinstance(config.get("files"), dict) else {}

    @staticmethod
    def _timeout(files_config: Dict[str, Any]) -> int:
        try:
            timeout = int(files_config.get("IMAGE_DECODER_TIMEOUT_SECONDS") or 30)
        except (TypeError, ValueError):
            timeout = 30
        return max(1, min(300, timeout))

    @staticmethod
    def _max_edge(files_config: Dict[str, Any]) -> int:
        try:
            max_edge = int(files_config.get("IMAGE_DECODER_MAX_EDGE", 4096))
        except (TypeError, ValueError):
            max_edge = 4096
        return max(0, min(20000, max_edge))

    @staticmethod
    def _string_list(value: Any, *, default: List[str]) -> List[str]:
        source = value if isinstance(value, list) else default
        normalized: List[str] = []
        for item in source:
            text = str(item or "").strip().lower().lstrip(".")
            if text and text not in normalized:
                normalized.append(text)
        return normalized or list(default)
