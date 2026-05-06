#!/usr/bin/env python3
"""Tests für AP6: ExifTool-Reads pro Datei bündeln."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from handler.exiftool_handler import ExifToolHandler
from imgdata import ImgDataService


class TestExifToolContextBundling(unittest.TestCase):
    """Tests für AP6: ExifTool-Reads pro Datei bündeln."""

    def setUp(self):
        self.service = ImgDataService(SessionManager())
        self.exiftool_handler = ExifToolHandler(self.service.config)

    def test_readMetadataContext_success_with_xmp(self):
        """
        Test: readMetadataContext gibt vollständigen Kontext zurück.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 1920,
            "ImageHeight": 1080,
            "Orientation": 6,
            "XMP": "<xmpmeta><rdf:RDF/></xmpmeta>"
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 1920, "height": 1080, "unit": "pixel"})
        self.assertEqual(result["image_orientation"], 6)
        self.assertEqual(result["xmp_content"], "<xmpmeta><rdf:RDF/></xmpmeta>")
        self.assertIsNone(result["error"])

    def test_readMetadataContext_success_without_xmp(self):
        """
        Test: readMetadataContext ohne XMP funktioniert.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{
            "SourceFile": "/tmp/test.jpg",
            "ImageWidth": 800,
            "ImageHeight": 600,
            "Orientation": 1
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": 800, "height": 600, "unit": "pixel"})
        self.assertEqual(result["image_orientation"], 1)
        self.assertIsNone(result["xmp_content"])
        self.assertIsNone(result["error"])

    def test_readMetadataContext_exiftool_not_available(self):
        """
        Test: readMetadataContext bei nicht verfügbarem ExifTool.
        """
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("", "not found")):
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "exiftool_not_available")
        self.assertIsNone(result["xmp_content"])
        self.assertEqual(result["image_dimensions"], {"width": None, "height": None, "unit": "pixel"})
        self.assertIsNone(result["image_orientation"])

    def test_readMetadataContext_exiftool_execution_error(self):
        """
        Test: readMetadataContext bei ExifTool-Ausführungsfehler.
        """
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", side_effect=FileNotFoundError("exiftool not found")):
            
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertIn("exiftool_execution_failed", result["error"])

    def test_readMetadataContext_invalid_json(self):
        """
        Test: readMetadataContext bei ungültiger JSON-Ausgabe.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg")

        self.assertFalse(result["success"])
        self.assertIn("json_parse_error", result["error"])

    def test_readMetadataContext_missing_keys(self):
        """
        Test: readMetadataContext behandelt fehlende Keys korrekt.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{
            "SourceFile": "/tmp/test.jpg"
            # Keine ImageWidth, ImageHeight, Orientation, XMP
        }])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContext("/tmp/test.jpg", include_xmp=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["image_dimensions"], {"width": None, "height": None, "unit": "pixel"})
        self.assertIsNone(result["image_orientation"])
        self.assertIsNone(result["xmp_content"])

    def test_readImageMetadata_uses_bundled_exiftool_context(self):
        """
        Test: _readImageMetadata verwendet gebündelten ExifTool-Kontext.
        """
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
            # Schreibe minimale JPEG-Datei
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
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                
                metadata = self.service._readImageMetadata(path)

            # Sollte readMetadataContext einmal aufgerufen haben
            self.assertEqual(metadata.get("xmp_content"), "<xmpmeta><rdf:RDF/></xmpmeta>")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_exiftool")
            self.assertEqual(metadata.get("image_dimensions"), {"width": 1024, "height": 768, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 6)
        finally:
            os.unlink(path)

    def test_readImageMetadata_fallback_when_context_fails(self):
        """
        Test: _readImageMetadata fällt zurück bei fehlgeschlagenem Kontext.
        """
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
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                
                metadata = self.service._readImageMetadata(path)

            # Sollte auf individuelle Methoden zurückgefallen sein
            self.assertEqual(metadata.get("image_dimensions"), {"width": 800, "height": 600, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()