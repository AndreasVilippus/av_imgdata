import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from handler.exiftool_handler import ExifToolHandler
from services.config_service import ConfigService


class StubConfigService(ConfigService):
    def __init__(self, configured_path: str, enabled: bool = True, use_manual_path: bool = False, manual_path: str = ""):
        self._configured_path = configured_path
        self._enabled = enabled
        self._use_manual_path = use_manual_path
        self._manual_path = manual_path

    def readMergedConfig(self):
        return {
            "files": {
                "PATHEXIFTOOL": self._configured_path,
                "USE_EXIFTOOL": self._enabled,
                "USE_MANUAL_PATHEXIFTOOL": self._use_manual_path,
                "MANUAL_PATHEXIFTOOL": self._manual_path,
            }
        }


class ExifToolHandlerTests(unittest.TestCase):
    def test_configured_path_prefers_manual_path_when_enabled(self):
        handler = ExifToolHandler(
            StubConfigService(
                "/var/packages/AV_ImgData/target/usr/bin/exiftool",
                use_manual_path=True,
                manual_path="/usr/local/bin/exiftool",
            )
        )

        self.assertEqual(handler.configuredPath(), "/usr/local/bin/exiftool")

    def test_is_available_returns_false_for_broken_executable_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_executable = Path(tmpdir) / "exiftool"
            broken_executable.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
            broken_executable.chmod(0o755)

            handler = ExifToolHandler(StubConfigService(str(broken_executable)))

            self.assertFalse(handler.isAvailable())

    def test_write_xmp_detailed_returns_exiftool_error_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "exiftool"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            target = Path(tmpdir) / "image.jpg"
            target.write_text("dummy", encoding="utf-8")
            handler = ExifToolHandler(StubConfigService(str(executable)))

            class Completed:
                returncode = 1
                stdout = ""
                stderr = "Error: Permission denied"

            with patch("handler.exiftool_handler.subprocess.run", return_value=Completed()):
                result = handler.writeXmpDetailed(str(target), "<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>")

            self.assertFalse(result["updated"])
            self.assertEqual(result["error"], "exiftool_write_failed")
            self.assertEqual(result["returncode"], 1)
            self.assertIn("Permission denied", result["stderr"])


if __name__ == "__main__":
    unittest.main()
