#!/usr/bin/env python3
"""Tests für ExifTool-Kontext-Lesezugriffe über persistenten Reader."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from handler.exiftool_handler import ExifToolHandler, _ExifToolResult
from imgdata import ImgDataService


class TestExifToolContextBundling(unittest.TestCase):
    """Tests für den gebündelten Metadaten-Kontext pro Datei."""

    def setUp(self):
        self.service = ImgDataService(SessionManager())
        self.exiftool_handler = ExifToolHandler(self.service.config)

    def test_readMetadataContext_success_with_xmp(self):
        output = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 1920,
            "ImageHeight": 1080,
            "Orientation": 6,
            "XMP": "<xmpmeta><rdf:RDF/></xmpmeta>"
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(0, output, "")):

            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 1920, "height": 1080, "unit": "pixel"})
        self.assertEqual(result["image_orientation"], 6)
        self.assertEqual(result["xmp_content"], "<xmpmeta><rdf:RDF/></xmpmeta>")
        self.assertIsNone(result["error"])

    def test_readMetadataContext_success_without_xmp(self):
        output = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 800,
            "ImageHeight": 600,
            "Orientation": 1
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(0, output, "")):

            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 800, "height": 600, "unit": "pixel"})
        self.assertEqual(result["image_orientation"], 1)
        self.assertIsNone(result["xmp_content"])
        self.assertIsNone(result["error"])

    def test_readMetadataContext_exiftool_not_available(self):
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("", "not found")):
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "exiftool_not_available")
        self.assertIsNone(result["xmp_content"])
        self.assertEqual(result["image_dimensions"], {"width": None, "height": None, "unit": "pixel"})
        self.assertIsNone(result["image_orientation"])

    def test_readMetadataContext_exiftool_execution_error(self):
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(126, "", "exiftool_execution_failed: exiftool not found")):

            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertIn("exiftool_execution_failed", result["error"])

    def test_readMetadataContext_invalid_json(self):
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(0, "invalid json", "")):

            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertIn("json_parse_error", result["error"])

    def test_readMetadataContext_missing_keys(self):
        output = json.dumps([{
            "SourceFile": "/tmp/test.jpg"
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch.object(self.exiftool_handler, "_runPersistentExifTool", return_value=_ExifToolResult(0, output, "")):

            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": None, "height": None, "unit": "pixel"})
        self.assertIsNone(result["image_orientation"])
        self.assertIsNone(result["xmp_content"])

    def test_readImageMetadata_uses_bundled_exiftool_context(self):
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

            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": True,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": True,
                    "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
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
                 patch.object(self.service.exiftool_handler, "readMetadataContext", return_value=mock_context), \
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):

                metadata = self.service._readImageMetadata(path)

            self.assertEqual(metadata.get("xmp_content"), "<xmpmeta><rdf:RDF/></xmpmeta>")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_exiftool")
            self.assertEqual(metadata.get("image_dimensions"), {"width": 1024, "height": 768, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 6)
        finally:
            os.unlink(path)

    def test_readImageMetadata_fallback_when_context_fails(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
            handle.write(b"\xff\xd8\xff\xd9")

        try:
            mock_context = {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": "some_error",
            }

            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": True,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": True,
                    "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
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
                 patch.object(self.service.exiftool_handler, "readMetadataContext", return_value=mock_context), \
                 patch.object(self.service.exiftool_handler, "readImageDimensions", return_value={"width": 800, "height": 600, "unit": "pixel"}), \
                 patch.object(self.service.exiftool_handler, "readImageOrientation", return_value=1), \
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):

                metadata = self.service._readImageMetadata(path)

            self.assertEqual(metadata.get("image_dimensions"), {"width": 800, "height": 600, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
