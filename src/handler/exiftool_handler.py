#!/usr/bin/env python3
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.config_service import ConfigService


class ExifToolHandler:
    def __init__(self, config_service: ConfigService):
        self._config = config_service

    def isEnabled(self) -> bool:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return bool(files_config.get("USE_EXIFTOOL", False))

    def configuredPath(self) -> str:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return str(files_config.get("PATHEXIFTOOL", "exiftool") or "exiftool").strip() or "exiftool"

    def resolveExecutable(self) -> Tuple[str, str]:
        candidate = self.configuredPath()
        explicit = Path(candidate)
        if explicit.is_absolute():
            return (str(explicit), "configured_path") if explicit.exists() else ("", "")

        found = shutil.which(candidate)
        if found:
            return found, "path_lookup"

        common_paths = [
            "/usr/bin/exiftool",
            "/usr/local/bin/exiftool",
            "/opt/bin/exiftool",
            "/var/packages/ExifTool/target/bin/exiftool",
        ]
        for path in common_paths:
            if Path(path).exists():
                return path, "common_path"
        return "", ""

    def isAvailable(self) -> bool:
        executable_path, _ = self.resolveExecutable()
        return bool(executable_path)

    def loadEmbeddedXmp(self, image_path: str) -> Optional[str]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-b", "-XMP", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None

        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def loadXmpFile(self, xmp_path: str) -> Optional[str]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-b", "-XMP", xmp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None

        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def readImageDimensions(self, image_path: str) -> Dict[str, Any]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return {"width": None, "height": None, "unit": "pixel"}

        try:
            result = subprocess.run(
                [executable_path, "-s3", "-ImageWidth", "-ImageHeight", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return {"width": None, "height": None, "unit": "pixel"}

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return {"width": None, "height": None, "unit": "pixel"}

        try:
            width = int(float(lines[0]))
            height = int(float(lines[1]))
        except (TypeError, ValueError):
            return {"width": None, "height": None, "unit": "pixel"}

        return {"width": width, "height": height, "unit": "pixel"}

    def readImageOrientation(self, image_path: str) -> Optional[int]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-s3", "-n", "-Orientation", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None

        value = result.stdout.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
