import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from handler.exiftool_handler import ExifToolHandler
from services.config_service import ConfigService


class StubConfigService(ConfigService):
    def __init__(self, configured_path: str, enabled: bool = True):
        self._configured_path = configured_path
        self._enabled = enabled

    def readMergedConfig(self):
        return {
            "files": {
                "PATHEXIFTOOL": self._configured_path,
                "USE_EXIFTOOL": self._enabled,
            }
        }


class ExifToolHandlerTests(unittest.TestCase):
    def test_is_available_returns_false_for_broken_executable_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_executable = Path(tmpdir) / "exiftool"
            broken_executable.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
            broken_executable.chmod(0o755)

            handler = ExifToolHandler(StubConfigService(str(broken_executable)))

            self.assertFalse(handler.isAvailable())


if __name__ == "__main__":
    unittest.main()
