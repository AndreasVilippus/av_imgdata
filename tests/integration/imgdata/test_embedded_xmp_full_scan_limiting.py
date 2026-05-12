#!/usr/bin/env python3
"""Tests für AP5: Full-File-XMP-Scan begrenzen."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class TestEmbeddedXmpFullScanLimiting(unittest.TestCase):
    """Tests für AP5: Embedded XMP Full-Scan begrenzen."""

    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_embedded_xmp_full_scan_disabled_by_default(self):
        """
        Test: EMBEDDED_XMP_FULL_SCAN_ENABLED ist standardmäßig False.
        Bei Nicht-JPEG-Dateien wird kein Full-Scan durchgeführt.
        """
        with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as handle:
            path = handle.name
            # Schreibe eine große Datei mit XMP am Ende
            handle.write(b"x" * 100000)  # 100KB Dummy-Daten
            handle.write(b'<xmpmeta xmlns="adobe:ns:meta/"><rdf:RDF/></xmpmeta>')
        
        try:
            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": False,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                    # EMBEDDED_XMP_FULL_SCAN_ENABLED ist standardmäßig False
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), patch.object(self.service.exiftool_handler, "isAvailable", return_value=False), patch.object(self.service.files, "loadXmpFromImageParsed", side_effect=AssertionError("loadXmpFromImageParsed should not be called when disabled")) as load_parsed_mock, patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                metadata = self.service._readImageMetadata(path)

            # XMP sollte nicht gefunden werden (da Full-Scan disabled)
            self.assertEqual(metadata.get("xmp_content"), None)
            self.assertEqual(metadata.get("xmp_source"), "")
        finally:
            os.unlink(path)

    def test_embedded_xmp_full_scan_enabled_with_max_bytes(self):
        """
        Test: Wenn EMBEDDED_XMP_FULL_SCAN_ENABLED=True,
        wird loadXmpFromImageParsed mit max_bytes aufgerufen.
        """
        with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as handle:
            path = handle.name
            # Schreibe eine Datei mit XMP innerhalb der Grenze
            handle.write(b"x" * 50000)  # 50KB Dummy-Daten
            handle.write(b'<xmpmeta xmlns="adobe:ns:meta/"><rdf:RDF/></xmpmeta>')
        
        try:
            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": False,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                    "EMBEDDED_XMP_FULL_SCAN_ENABLED": True,
                    "EMBEDDED_XMP_FULL_SCAN_MAX_BYTES": 100000,
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), patch.object(self.service.exiftool_handler, "isAvailable", return_value=False), patch.object(self.service.files, "loadXmpFromImageParsed", return_value='<xmpmeta xmlns="adobe:ns:meta/"><rdf:RDF/></xmpmeta>') as load_parsed_mock, patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                metadata = self.service._readImageMetadata(path)

            # loadXmpFromImageParsed sollte mit max_bytes aufgerufen werden
            load_parsed_mock.assert_called_once_with(path, max_bytes=100000)
            self.assertEqual(metadata.get("xmp_content"), '<xmpmeta xmlns="adobe:ns:meta/"><rdf:RDF/></xmpmeta>')
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_parsed")
        finally:
            os.unlink(path)

    def test_embedded_xmp_full_scan_xmp_beyond_max_bytes_not_found(self):
        """
        Test: Wenn XMP nach max_bytes liegt, wird es nicht gefunden.
        """
        with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as handle:
            path = handle.name
            # Schreibe eine Datei mit XMP NACH der Grenze
            handle.write(b"x" * 150000)  # 150KB Dummy-Daten (über max_bytes=100000)
            handle.write(b'<xmpmeta xmlns="adobe:ns:meta/"><rdf:RDF/></xmpmeta>')
        
        try:
            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": False,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                    "EMBEDDED_XMP_FULL_SCAN_ENABLED": True,
                    "EMBEDDED_XMP_FULL_SCAN_MAX_BYTES": 100000,
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), patch.object(self.service.exiftool_handler, "isAvailable", return_value=False), patch.object(self.service.files, "loadXmpFromImageParsed", return_value=None) as load_parsed_mock, patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                metadata = self.service._readImageMetadata(path)

            # loadXmpFromImageParsed sollte mit max_bytes aufgerufen werden
            load_parsed_mock.assert_called_once_with(path, max_bytes=100000)
            # XMP sollte nicht gefunden werden (da außerhalb max_bytes)
            self.assertEqual(metadata.get("xmp_content"), None)
            self.assertEqual(metadata.get("xmp_source"), "")
        finally:
            os.unlink(path)

    def test_embedded_xmp_full_scan_jpeg_uses_header_scan_instead(self):
        """
        Test: Bei JPEG-Dateien wird der Full-Scan nicht verwendet,
        da readJpegContext() bevorzugt wird.
        """
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
            # Schreibe eine JPEG-Datei mit XMP im Header
            handle.write(b"\xff\xd8")  # JPEG SOI
            # APP1 XMP Segment
            xmp_data = b"http://ns.adobe.com/xap/1.0/\x00<xmpmeta><rdf:RDF/></xmpmeta>"
            handle.write(b"\xff\xe1" + (len(xmp_data) + 2).to_bytes(2, 'big') + xmp_data)
            handle.write(b"\xff\xd9")  # JPEG EOI
        
        try:
            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": False,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                    "EMBEDDED_XMP_FULL_SCAN_ENABLED": True,  # Sollte für JPEG ignoriert werden
                    "EMBEDDED_XMP_FULL_SCAN_MAX_BYTES": 100000,
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), patch.object(self.service.exiftool_handler, "isAvailable", return_value=False), patch.object(self.service.files, "loadXmpFromImageParsed", side_effect=AssertionError("loadXmpFromImageParsed should not be called for JPEG")) as load_parsed_mock, patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                metadata = self.service._readImageMetadata(path)

            # XMP sollte aus JPEG-Header kommen, nicht aus Full-Scan
            self.assertIn("<xmpmeta>", metadata.get("xmp_content") or "")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_parsed")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()