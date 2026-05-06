#!/usr/bin/env python3
"""Tests für AP7: ExifTool-Batch-Read für Scanläufe vorbereiten."""
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


class TestExifToolBatchReading(unittest.TestCase):
    """Tests für AP7: ExifTool-Batch-Read für Scanläufe vorbereiten."""

    def setUp(self):
        self.service = ImgDataService(SessionManager())
        self.exiftool_handler = ExifToolHandler(self.service.config)

    def test_readMetadataContextBatch_empty_list(self):
        """
        Test: readMetadataContextBatch mit leerer Liste.
        """
        result = self.exiftool_handler.readMetadataContextBatch([])
        self.assertEqual(result, {})

    def test_readMetadataContextBatch_exiftool_not_available(self):
        """
        Test: readMetadataContextBatch bei nicht verfügbarem ExifTool.
        """
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("", "not found")):
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg", "/tmp/test2.jpg"])

        self.assertEqual(len(result), 2)
        for path in ["/tmp/test1.jpg", "/tmp/test2.jpg"]:
            self.assertIn(path, result)
            self.assertFalse(result[path]["success"])
            self.assertEqual(result[path]["error"], "exiftool_not_available")

    def test_readMetadataContextBatch_success_with_xmp(self):
        """
        Test: readMetadataContextBatch erfolgreich mit XMP.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {
                "SourceFile": "/tmp/test1.jpg",
                "ImageWidth": 1920,
                "ImageHeight": 1080,
                "Orientation": 6,
                "XMP": "<xmpmeta><rdf:RDF/></xmpmeta>"
            },
            {
                "SourceFile": "/tmp/test2.jpg",
                "ImageWidth": 800,
                "ImageHeight": 600,
                "Orientation": 1,
                "XMP": "<xmpmeta><rdf:RDF>2</xmpmeta>"
            }
        ])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg", "/tmp/test2.jpg"], include_xmp=True)

        self.assertEqual(len(result), 2)
        
        # Test erste Datei
        ctx1 = result["/tmp/test1.jpg"]
        self.assertTrue(ctx1["success"])
        self.assertEqual(ctx1["image_dimensions"], {"width": 1920, "height": 1080, "unit": "pixel"})
        self.assertEqual(ctx1["image_orientation"], 6)
        self.assertEqual(ctx1["xmp_content"], "<xmpmeta><rdf:RDF/></xmpmeta>")
        
        # Test zweite Datei
        ctx2 = result["/tmp/test2.jpg"]
        self.assertTrue(ctx2["success"])
        self.assertEqual(ctx2["image_dimensions"], {"width": 800, "height": 600, "unit": "pixel"})
        self.assertEqual(ctx2["image_orientation"], 1)
        self.assertEqual(ctx2["xmp_content"], "<xmpmeta><rdf:RDF>2</xmpmeta>")

    def test_readMetadataContextBatch_success_without_xmp(self):
        """
        Test: readMetadataContextBatch erfolgreich ohne XMP.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {
                "SourceFile": "/tmp/test1.jpg",
                "ImageWidth": 1920,
                "ImageHeight": 1080,
                "Orientation": 6
            }
        ])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg"], include_xmp=False)

        self.assertEqual(len(result), 1)
        ctx = result["/tmp/test1.jpg"]
        self.assertTrue(ctx["success"])
        self.assertEqual(ctx["image_dimensions"], {"width": 1920, "height": 1080, "unit": "pixel"})
        self.assertEqual(ctx["image_orientation"], 6)
        self.assertIsNone(ctx["xmp_content"])

    def test_readMetadataContextBatch_partial_success(self):
        """
        Test: readMetadataContextBatch mit teilweisem Erfolg.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {
                "SourceFile": "/tmp/test1.jpg",
                "ImageWidth": 1920,
                "ImageHeight": 1080,
                "Orientation": 6
            }
            # test2.jpg fehlt in Ausgabe
        ])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg", "/tmp/test2.jpg"])

        self.assertEqual(len(result), 2)
        
        # test1.jpg erfolgreich
        ctx1 = result["/tmp/test1.jpg"]
        self.assertTrue(ctx1["success"])
        
        # test2.jpg fehlgeschlagen
        ctx2 = result["/tmp/test2.jpg"]
        self.assertFalse(ctx2["success"])
        self.assertEqual(ctx2["error"], "file_not_in_batch_output")

    def test_readMetadataContextBatch_execution_error(self):
        """
        Test: readMetadataContextBatch bei Ausführungsfehler.
        """
        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", side_effect=FileNotFoundError("exiftool not found")):
            
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg", "/tmp/test2.jpg"])

        self.assertEqual(len(result), 2)
        for path in ["/tmp/test1.jpg", "/tmp/test2.jpg"]:
            self.assertIn(path, result)
            self.assertFalse(result[path]["success"])
            self.assertIn("exiftool_execution_failed", result[path]["error"])

    def test_readMetadataContextBatch_invalid_json(self):
        """
        Test: readMetadataContextBatch bei ungültiger JSON-Ausgabe.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", return_value=mock_result):
            
            result = self.exiftool_handler.readMetadataContextBatch(["/tmp/test1.jpg"])

        self.assertEqual(len(result), 1)
        ctx = result["/tmp/test1.jpg"]
        self.assertFalse(ctx["success"])
        self.assertIn("json_parse_error", ctx["error"])

    def test_readMetadataContextBatch_batches(self):
        """
        Test: readMetadataContextBatch verarbeitet in Batches.
        """
        # Erstelle 5 Dateien, Batch-Size 2
        paths = [f"/tmp/test{i}.jpg" for i in range(5)]
        
        # Mock für ersten Batch (test0.jpg, test1.jpg)
        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = json.dumps([
            {"SourceFile": "/tmp/test0.jpg", "ImageWidth": 100, "ImageHeight": 100},
            {"SourceFile": "/tmp/test1.jpg", "ImageWidth": 200, "ImageHeight": 200}
        ])
        
        # Mock für zweiten Batch (test2.jpg, test3.jpg)
        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = json.dumps([
            {"SourceFile": "/tmp/test2.jpg", "ImageWidth": 300, "ImageHeight": 300},
            {"SourceFile": "/tmp/test3.jpg", "ImageWidth": 400, "ImageHeight": 400}
        ])
        
        # Mock für dritten Batch (test4.jpg)
        mock_result3 = MagicMock()
        mock_result3.returncode = 0
        mock_result3.stdout = json.dumps([
            {"SourceFile": "/tmp/test4.jpg", "ImageWidth": 500, "ImageHeight": 500}
        ])

        with patch.object(self.exiftool_handler, "resolveExecutable", return_value=("exiftool", "")), \
             patch("subprocess.run", side_effect=[mock_result1, mock_result2, mock_result3]):
            
            result = self.exiftool_handler.readMetadataContextBatch(paths, batch_size=2)

        self.assertEqual(len(result), 5)
        for i, path in enumerate(paths):
            self.assertIn(path, result)
            self.assertTrue(result[path]["success"])
            expected_width = (i + 1) * 100
            self.assertEqual(result[path]["image_dimensions"]["width"], expected_width)

    def test_readImageMetadata_uses_batch_cache(self):
        """
        Test: _readImageMetadata verwendet Batch-Cache.
        """
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
                    "EXIFTOOL_BATCH_READ_ENABLED": False,  # Deaktiviert, aber Cache wird verwendet
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
                 patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                
                metadata = self.service._readImageMetadata(path, metadata_context_cache=cache)

            # Sollte Cache verwenden, nicht readMetadataContext aufrufen
            self.assertEqual(metadata.get("xmp_content"), "<xmpmeta><rdf:RDF/></xmpmeta>")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_exiftool")
            self.assertEqual(metadata.get("image_dimensions"), {"width": 1024, "height": 768, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 6)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()