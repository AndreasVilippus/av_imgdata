import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from handler.exiftool_handler import ExifToolHandler, PersistentExifToolProcess
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

    def test_write_xmp_detailed_ignores_minor_makernotes_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "exiftool"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            target = Path(tmpdir) / "image.jpg"
            target.write_text("dummy", encoding="utf-8")
            handler = ExifToolHandler(StubConfigService(str(executable)))

            class Completed:
                returncode = 0
                stdout = "    1 image files updated"
                stderr = "Warning: Bad MakerNotes offset for CameraInfo2"

            with patch("handler.exiftool_handler.subprocess.run", return_value=Completed()) as run_mock:
                result = handler.writeXmpDetailed(str(target), "<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>")

            command = run_mock.call_args[0][0]
            self.assertIn("-m", command)
            self.assertTrue(result["updated"])
            self.assertIn("Bad MakerNotes offset", result["stderr"])

    def test_extract_embedded_jpeg_preview_reads_binary_preview_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "exiftool"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            target = Path(tmpdir) / "image.heic"
            target.write_bytes(b"heic")
            handler = ExifToolHandler(StubConfigService(str(executable)))

            class Completed:
                returncode = 0
                stdout = b"\xff\xd8jpeg-preview\xff\xd9"
                stderr = b""

            with patch("handler.exiftool_handler.subprocess.run", return_value=Completed()) as run_mock:
                preview = handler.extractEmbeddedJpegPreview(str(target))

            self.assertEqual(preview, b"\xff\xd8jpeg-preview\xff\xd9")
            command = run_mock.call_args[0][0]
            self.assertIn("-b", command)
            self.assertIn("-PreviewImage", command)

    def test_extract_embedded_jpeg_preview_ignores_non_jpeg_binary_tag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "exiftool"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            target = Path(tmpdir) / "image.heic"
            target.write_bytes(b"heic")
            handler = ExifToolHandler(StubConfigService(str(executable)))

            class Completed:
                returncode = 0
                stdout = b"not-jpeg"
                stderr = b""

            with patch("handler.exiftool_handler.subprocess.run", return_value=Completed()):
                preview = handler.extractEmbeddedJpegPreview(str(target))

            self.assertIsNone(preview)

    def test_persistent_reader_handles_multiline_output_without_text_buffer_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "fake_exiftool.py"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "for line in sys.stdin:\n"
                "    if line.strip() == '-execute':\n"
                "        sys.stdout.write('[{\\n')\n"
                "        sys.stdout.write('  \"ImageWidth\": 4272,\\n')\n"
                "        sys.stdout.write('  \"ImageHeight\": 2848,\\n')\n"
                "        sys.stdout.write('  \"Orientation\": 1\\n')\n"
                "        sys.stdout.write('}]\\n')\n"
                "        sys.stdout.write('{ready}\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif line.strip() == 'False':\n"
                "        break\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            reader = PersistentExifToolProcess(str(executable), timeout_seconds=1)

            try:
                result = reader.run(["-j", "-n", "-ImageWidth", "/tmp/photo.jpg"])
            finally:
                reader.close()

            self.assertEqual(result.returncode, 0)
            self.assertIn('"ImageWidth": 4272', result.stdout)
            self.assertIn('"ImageHeight": 2848', result.stdout)
            self.assertIn('"Orientation": 1', result.stdout)

    def test_persistent_reader_handles_ready_marker_after_binary_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "fake_exiftool.py"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "for line in sys.stdin:\n"
                "    if line.strip() == '-execute':\n"
                "        sys.stdout.write('<x:xmpmeta></x:xmpmeta>')\n"
                "        sys.stdout.write('{ready}\\n')\n"
                "        sys.stdout.flush()\n"
                "    elif line.strip() == 'False':\n"
                "        break\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            reader = PersistentExifToolProcess(str(executable), timeout_seconds=1)

            try:
                result = reader.run(["-b", "-XMP", "/tmp/photo.jpg"])
            finally:
                reader.close()

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "<x:xmpmeta></x:xmpmeta>")


if __name__ == "__main__":
    unittest.main()
