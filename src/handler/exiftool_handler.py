#!/usr/bin/env python3
import subprocess
import tempfile
from typing import Any, Dict, Optional, Tuple

from services.config_service import ConfigService
from services.exiftool_service import ExifToolService


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
        return ExifToolService._resolveExecutable(self.configuredPath())

    def isAvailable(self) -> bool:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return False
        return bool(ExifToolService._readExifToolVersion(executable_path))

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
        if result.returncode != 0:
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
        if result.returncode != 0:
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
        if result.returncode != 0:
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
        if result.returncode != 0:
            return None

        value = result.stdout.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def writeXmp(self, target_path: str, xmp_content: str) -> bool:
        executable_path, _ = self.resolveExecutable()
        if not executable_path or not target_path or not xmp_content:
            return False

        packet_content = str(xmp_content or "").strip()
        if not packet_content:
            return False
        if "<?xpacket" not in packet_content:
            packet_content = (
                "<?xpacket begin='\ufeff' id='W5M0MpCehiHzreSzNTczkc9d'?>\n"
                f"{packet_content}\n"
                "<?xpacket end='w'?>\n"
            )

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".xmp", encoding="utf-8", delete=False) as handle:
                handle.write(packet_content)
                temp_path = handle.name
            result = subprocess.run(
                [executable_path, "-overwrite_original", f"-XMP<={temp_path}", target_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return False
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return False

        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        combined_output = f"{stdout}\n{stderr}".lower()
        if "0 image files updated" in combined_output or "0 image files created" in combined_output:
            return False
        if "1 image files updated" in combined_output or "1 image files created" in combined_output:
            return True
        if "1 image files unchanged" in combined_output:
            return True
        return True
