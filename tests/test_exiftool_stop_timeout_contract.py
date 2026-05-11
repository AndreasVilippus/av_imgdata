import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from handler.exiftool_handler import ExifToolHandler
from imgdata import ImgDataService


def test_subprocess_exiftool_read_has_timeout():
    service = ImgDataService(SessionManager())
    handler = ExifToolHandler(service.config)

    with patch.object(handler, "resolveExecutable", return_value=("exiftool", "")), \
         patch.object(handler, "_persistentEnabled", return_value=False), \
         patch.object(handler, "_persistentTimeoutSeconds", return_value=1), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["exiftool"], timeout=1)) as run_mock:
        result = handler.readMetadataContext("/tmp/stuck.ARW")

    run_mock.assert_called_once()
    assert result["success"] is False
    assert result["error"] == "exiftool_execution_timeout"


def test_persistent_exiftool_process_does_not_pipe_stderr():
    source = Path("src/handler/exiftool_handler.py").read_text(encoding="utf-8")
    persistent_class = source[source.find("class PersistentExifToolProcess"):source.find("class ExifToolHandler")]
    assert "stderr=subprocess.DEVNULL" in persistent_class
    assert "stderr=subprocess.PIPE" not in persistent_class


def test_checks_stop_request_prevents_starting_new_exiftool_context_call():
    service = ImgDataService(SessionManager())

    with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as handle:
        image_path = handle.name
        handle.write(b"not-a-real-heic")

    try:
        service._setChecksProgress(
            "user",
            check_type="name_conflicts",
            source_mode="scan",
            running=True,
            finished=False,
            stop_requested=True,
            save_only=True,
        )
        service._setActiveChecksContext(user_key="user", check_type="name_conflicts", save_only=True)

        config = {
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": False,
                "SIDECAR_EXIFTOOL_FALLBACK_ENABLED": False,
                "SIDECAR_READ_MODE": "direct_only",
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
            },
            "metadata": {"SCHEMAS": {"ACD": False, "MICROSOFT": False, "MWG_REGIONS": False}},
        }

        with patch.object(service.config, "readMergedConfig", return_value=config), \
             patch.object(service.files, "findXmpForImage", return_value=None), \
             patch.object(service.files, "readImageDimensions", return_value={"width": None, "height": None, "unit": "pixel"}), \
             patch.object(service.files, "readJpegExifOrientation", return_value=None), \
             patch.object(service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(service, "_shouldStopChecks", return_value=True), \
             patch.object(service.exiftool_handler, "readMetadataContext", side_effect=AssertionError("stop should prevent new ExifTool context call")) as read_context:
            try:
                service._readImageMetadata(image_path)
            except Exception as exc:
                assert "checks_stop_requested" in str(exc)
            else:
                raise AssertionError("Expected checks_stop_requested")
            read_context.assert_not_called()
    finally:
        Path(image_path).unlink(missing_ok=True)
