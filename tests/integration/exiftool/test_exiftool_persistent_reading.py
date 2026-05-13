#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from handler.exiftool_handler import ExifToolHandler, _ExifToolResult
from imgdata import ImgDataService
from services.config_service import ConfigService


class TestExifToolPersistentReading(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())
        self.exiftool_handler = ExifToolHandler(self.service.config)

    def test_persistent_reading_is_enabled_by_default_and_batch_config_is_removed(self):
        config = ConfigService.defaultConfig()
        files = config["files"]

        self.assertTrue(files["EXIFTOOL_PERSISTENT_ENABLED"])
        self.assertEqual(files["EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS"], 30)
        self.assertNotIn("EXIFTOOL_BATCH_READ_ENABLED", files)
        self.assertNotIn("EXIFTOOL_BATCH_SIZE", files)

    def test_readMetadataContext_uses_persistent_reader_by_default(self):
        payload = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 1920,
            "ImageHeight": 1080,
            "Orientation": 6,
            "XMP": "<xmpmeta><rdf:RDF/></xmpmeta>",
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(0, payload, "")) as persistent_mock, \
             patch("subprocess.run", side_effect=AssertionError("persistent read must not use subprocess.run")):
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=True)

        persistent_mock.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 1920, "height": 1080, "unit": "pixel"})
        self.assertEqual(result["image_orientation"], 6)
        self.assertEqual(result["xmp_content"], "<xmpmeta><rdf:RDF/></xmpmeta>")

    def test_read_helpers_use_persistent_reader_by_default(self):
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", side_effect=[
                 _ExifToolResult(0, "<xmp>embedded</xmp>", ""),
                 _ExifToolResult(0, "<xmp>sidecar</xmp>", ""),
                 _ExifToolResult(0, "400\n300\n", ""),
                 _ExifToolResult(0, "6\n", ""),
             ]) as persistent_mock, \
             patch("subprocess.run", side_effect=AssertionError("persistent read must not use subprocess.run")):
            self.assertEqual(self.exiftool_handler.loadEmbeddedXmp("/tmp/test.jpg"), "<xmp>embedded</xmp>")
            self.assertEqual(self.exiftool_handler.loadXmpFile("/tmp/test.xmp"), "<xmp>sidecar</xmp>")
            self.assertEqual(self.exiftool_handler.readImageDimensions("/tmp/test.jpg"), {"width": 400, "height": 300, "unit": "pixel"})
            self.assertEqual(self.exiftool_handler.readImageOrientation("/tmp/test.jpg"), 6)

        self.assertEqual(persistent_mock.call_count, 4)

    def test_persistent_read_falls_back_to_subprocess_on_process_error(self):
        payload = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 100,
            "ImageHeight": 80,
            "Orientation": 1,
        }])
        subprocess_result = MagicMock(returncode=0, stdout=payload, stderr="")

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", side_effect=OSError("process ended")), \
             patch("subprocess.run", return_value=subprocess_result) as run_mock:
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=False)

        run_mock.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 100, "height": 80, "unit": "pixel"})

    def test_persistent_read_timeout_does_not_retry_same_file_with_subprocess(self):
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", side_effect=TimeoutError("hung")), \
             patch("subprocess.run", side_effect=AssertionError("timeout must not be retried")) as run_mock:
            result = self.exiftool_handler.readMetadataContext("/tmp/stuck.ARW", include_xmp=False)

        run_mock.assert_not_called()
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "exiftool_execution_timeout")

    def test_writeXmpDetailed_keeps_isolated_subprocess_write_path(self):
        subprocess_result = MagicMock(returncode=0, stdout="1 image files updated", stderr="")

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", side_effect=AssertionError("writes must not use persistent reader")), \
             patch("subprocess.run", return_value=subprocess_result) as run_mock:
            result = self.exiftool_handler.writeXmpDetailed("/tmp/test.jpg", "<xmpmeta><rdf:RDF/></xmpmeta>")

        run_mock.assert_called_once()
        self.assertTrue(result["updated"])

    def test_batch_api_is_removed_from_handler_and_scan_service(self):
        self.assertFalse(hasattr(self.exiftool_handler, "readMetadataContextBatch"))
        self.assertFalse(hasattr(self.service, "_populateScanMetadataContextBatch"))

    def test_readImageMetadata_still_accepts_existing_context_cache(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
            handle.write(b"\xff\xd8\xff\xd9")

        try:
            mock_context = {
                "success": True,
                "xmp_content": "<xmpmeta><rdf:RDF/></xmpmeta>",
                "image_dimensions": {"width": 1024, "height": 768, "unit": "pixel"},
                "image_orientation": 6,
                "error": None,
            }
            cache = {path: mock_context}

            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": True,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": True,
                    "EXIFTOOL_PERSISTENT_ENABLED": True,
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), \
                 patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
                 patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", side_effect=AssertionError("context cache should provide XMP")), \
                 patch.object(self.service.exiftool_handler, "readMetadataContext", side_effect=AssertionError("context cache should provide context")), \
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
                metadata = self.service._readImageMetadata(path, metadata_context_cache=cache)

            self.assertEqual(metadata.get("xmp_content"), "<xmpmeta><rdf:RDF/></xmpmeta>")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_exiftool")
            self.assertEqual(metadata.get("image_dimensions"), {"width": 1024, "height": 768, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 6)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
