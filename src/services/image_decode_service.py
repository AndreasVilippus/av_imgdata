#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.config_service import ConfigService


@dataclass
class ImageDecodeResult:
    success: bool
    image_bytes: bytes = b""
    source: str = ""
    error: str = ""


class ImageDecodeService:
    """Decode image formats that OpenCV cannot read directly via optional tools."""

    def __init__(self, config_service: Optional[ConfigService] = None):
        self._config = config_service or ConfigService()

    def decode_to_jpeg(self, image_path: str) -> ImageDecodeResult:
        path = Path(image_path)
        config = self._files_config()
        if not bool(config.get("IMAGE_DECODER_ENABLED", True)):
            return ImageDecodeResult(False, error="image_decoder_disabled")
        if not path.is_file():
            return ImageDecodeResult(False, error="image_not_found")
        extension = path.suffix.lower().lstrip(".")
        extensions = self._string_list(config.get("IMAGE_DECODER_EXTENSIONS"), default=["heic", "heif"])
        if extension not in extensions:
            return ImageDecodeResult(False, error="image_decoder_extension_not_enabled")

        errors: List[str] = []
        for decoder in self._string_list(config.get("IMAGE_DECODER_ORDER"), default=["pillow-heif", "heif-convert", "magick", "ffmpeg", "convert"]):
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

    def _files_config(self) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
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
