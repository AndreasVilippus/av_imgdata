#!/usr/bin/env python3
"""Tests für Sidecar XMP Fallback-Logik in ImgDataService."""
import os
import sys
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class TestImgDataServiceSidecarExifToolFallback(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_use_exiftool_for_sidecars_only_as_fallback(self):
        """
        Wenn USE_EXIFTOOL_FOR_SIDECARS=true, wird zuerst direkt gelesen.
        Lediglich bei fehlgeschlagener Direktlese wird ExifTool als Fallback verwendet.
        """
        xmp_path = "/tmp/test_sidecar.xmp"

        with patch.object(self.service.config, "readMergedConfig", return_value={
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": True,
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": False,
                    "MICROSOFT": False,
                    "MWG_REGIONS": False,
                }
            }
        }), patch.object(self.service.files, "findXmpForImage", return_value=xmp_path), patch.object(self.service.files, "loadXmpFromFile", return_value=None) as load_file_mock, patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), patch.object(self.service.exiftool_handler, "loadXmpFile", return_value="<xmp>fallback</xmp>") as load_exiftool_mock, patch.object(self.service.files, "readImageDimensions", return_value={"width": 100, "height": 80, "unit": "pixel"}), patch.object(self.service.files, "readJpegExifOrientation", return_value=1), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg")

        self.assertEqual(metadata.get("xmp_content"), "<xmp>fallback</xmp>")
        self.assertEqual(metadata.get("xmp_source"), "xmp_file")
        load_file_mock.assert_called_once_with(xmp_path)
        load_exiftool_mock.assert_called_once_with(xmp_path)

    def test_use_exiftool_for_sidecars_not_used_when_disabled(self):
        """
        Wenn USE_EXIFTOOL_FOR_SIDECARS=false, wird ExifTool für Sidecars nicht verwendet.
        """
        xmp_path = "/tmp/test_sidecar.xmp"

        with patch.object(self.service.config, "readMergedConfig", return_value={
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": False,
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": False,
                    "MICROSOFT": False,
                    "MWG_REGIONS": False,
                }
            }
        }), patch.object(self.service.files, "findXmpForImage", return_value=xmp_path), patch.object(self.service.files, "loadXmpFromFile", return_value="<xmp>direct</xmp>") as load_file_mock, patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), patch.object(self.service.exiftool_handler, "loadXmpFile", return_value="<xmp>fallback</xmp>") as load_exiftool_mock, patch.object(self.service.files, "readImageDimensions", return_value={"width": 100, "height": 80, "unit": "pixel"}), patch.object(self.service.files, "readJpegExifOrientation", return_value=1), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg")

        self.assertEqual(metadata.get("xmp_content"), "<xmp>direct</xmp>")
        self.assertEqual(metadata.get("xmp_source"), "xmp_file")
        load_file_mock.assert_called_once_with(xmp_path)
        load_exiftool_mock.assert_not_called()

    def test_sidecar_exiftool_fallback_enabled_allows_fallback_even_when_use_exiftool_for_sidecars_disabled(self):
        """
        Wenn SIDECAR_EXIFTOOL_FALLBACK_ENABLED=true, wird ExifTool als Fallback für Sidecars verwendet,
        auch wenn USE_EXIFTOOL_FOR_SIDECARS=false.
        """
        xmp_path = "/tmp/test_sidecar.xmp"

        with patch.object(self.service.config, "readMergedConfig", return_value={
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": False,
                "SIDECAR_EXIFTOOL_FALLBACK_ENABLED": True,
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": False,
                    "MICROSOFT": False,
                    "MWG_REGIONS": False,
                }
            }
        }), patch.object(self.service.files, "findXmpForImage", return_value=xmp_path), patch.object(self.service.files, "loadXmpFromFile", return_value=None) as load_file_mock, patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), patch.object(self.service.exiftool_handler, "loadXmpFile", return_value="<xmp>fallback</xmp>") as load_exiftool_mock, patch.object(self.service.files, "readImageDimensions", return_value={"width": 100, "height": 80, "unit": "pixel"}), patch.object(self.service.files, "readJpegExifOrientation", return_value=1), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg")

        self.assertEqual(metadata.get("xmp_content"), "<xmp>fallback</xmp>")
        self.assertEqual(metadata.get("xmp_source"), "xmp_file")
        load_file_mock.assert_called_once_with(xmp_path)
        load_exiftool_mock.assert_called_once_with(xmp_path)

    def test_sidecar_read_mode_direct_only_never_falls_back(self):
        """
        Wenn SIDECAR_READ_MODE=direct_only, wird ExifTool selbst bei Direktlese-Ausfall nicht genutzt.
        """
        xmp_path = "/tmp/test_sidecar.xmp"

        with patch.object(self.service.config, "readMergedConfig", return_value={
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": True,
                "SIDECAR_READ_MODE": "direct_only",
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": False,
                    "MICROSOFT": False,
                    "MWG_REGIONS": False,
                }
            }
        }), patch.object(self.service.files, "findXmpForImage", return_value=xmp_path), patch.object(self.service.files, "loadXmpFromFile", return_value=None) as load_file_mock, patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), patch.object(self.service.exiftool_handler, "loadXmpFile", return_value="<xmp>fallback</xmp>") as load_exiftool_mock, patch.object(self.service.files, "readImageDimensions", return_value={"width": 100, "height": 80, "unit": "pixel"}), patch.object(self.service.files, "readJpegExifOrientation", return_value=1), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg")

        self.assertIsNone(metadata.get("xmp_content"))
        load_file_mock.assert_called_once_with(xmp_path)
        load_exiftool_mock.assert_not_called()

    def test_sidecar_read_mode_exiftool_only_uses_exiftool(self):
        """
        Wenn SIDECAR_READ_MODE=exiftool_only, wird Sidecar-XMP nur über ExifTool geladen.
        """
        xmp_path = "/tmp/test_sidecar.xmp"

        with patch.object(self.service.config, "readMergedConfig", return_value={
            "files": {
                "USE_EXIFTOOL": True,
                "USE_EXIFTOOL_FOR_SIDECARS": False,
                "SIDECAR_READ_MODE": "exiftool_only",
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": False,
                    "MICROSOFT": False,
                    "MWG_REGIONS": False,
                }
            }
        }), patch.object(self.service.files, "findXmpForImage", return_value=xmp_path), patch.object(self.service.files, "loadXmpFromFile", return_value="<xmp>direct</xmp>") as load_file_mock, patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), patch.object(self.service.exiftool_handler, "loadXmpFile", return_value="<xmp>exiftool</xmp>") as load_exiftool_mock, patch.object(self.service.files, "readImageDimensions", return_value={"width": 100, "height": 80, "unit": "pixel"}), patch.object(self.service.files, "readJpegExifOrientation", return_value=1), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg")

        self.assertEqual(metadata.get("xmp_content"), "<xmp>exiftool</xmp>")
        load_file_mock.assert_not_called()
        load_exiftool_mock.assert_called_once_with(xmp_path)

    def _create_minimal_jpeg_with_xmp(self, path: str, orientation: int = 6, width: int = 800, height: int = 600, xmp_payload: str = "<xmpmeta></xmpmeta>") -> None:
        exif_header = b"Exif\x00\x00"
        tiff_header = b"II*\x00\x08\x00\x00\x00"
        entry_count = struct.pack("<H", 1)
        tag = struct.pack("<H", 0x0112)
        value_type = struct.pack("<H", 3)
        count = struct.pack("<I", 1)
        value = struct.pack("<H", orientation) + b"\x00\x00"
        next_ifd = struct.pack("<I", 0)
        exif_data = exif_header + tiff_header + entry_count + tag + value_type + count + value + next_ifd
        exif_segment = b"\xff\xe1" + struct.pack(">H", len(exif_data) + 2) + exif_data

        xmp_header = b"http://ns.adobe.com/xap/1.0/\x00"
        xmp_data = xmp_header + xmp_payload.encode("utf-8")
        xmp_segment = b"\xff\xe1" + struct.pack(">H", len(xmp_data) + 2) + xmp_data

        sof0_payload = b"\x08" + struct.pack(">H", height) + struct.pack(">H", width) + b"\x03" + b"\x01\x11\x00" + b"\x02\x11\x00" + b"\x03\x11\x00"
        sof0_segment = b"\xff\xc0" + struct.pack(">H", len(sof0_payload) + 2) + sof0_payload

        sos_payload = b"\x01\x01\x00\x00?\x00"
        sos_segment = b"\xff\xda" + struct.pack(">H", len(sos_payload) + 2) + sos_payload

        with open(path, "wb") as handle:
            handle.write(b"\xff\xd8")
            handle.write(exif_segment)
            handle.write(xmp_segment)
            handle.write(sof0_segment)
            handle.write(sos_segment)
            handle.write(b"\x00\xff\xd9")

    def test_read_jpeg_context_parses_dimensions_orientation_and_xmp(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
        try:
            self._create_minimal_jpeg_with_xmp(path, orientation=6, width=800, height=600, xmp_payload="<xmpmeta><rdf:RDF/></xmpmeta>")
            with patch.object(self.service.config, "readMergedConfig", return_value={
                "files": {
                    "USE_EXIFTOOL": False,
                    "USE_EXIFTOOL_FOR_SIDECARS": False,
                    "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                },
                "metadata": {
                    "SCHEMAS": {
                        "ACD": False,
                        "MICROSOFT": False,
                        "MWG_REGIONS": False,
                    }
                }
            }), patch.object(self.service.files, "findXmpForImage", return_value=None), patch.object(self.service.exiftool_handler, "isAvailable", return_value=False), patch.object(self.service.files, "readImageDimensions", side_effect=AssertionError("readImageDimensions should not be called for JPEG context")), patch.object(self.service.files, "readJpegExifOrientation", side_effect=AssertionError("readJpegExifOrientation should not be called for JPEG context")), patch.object(self.service.files, "loadXmpFromImageParsed", side_effect=AssertionError("loadXmpFromImageParsed should not be called when JPEG header XMP is available")), patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
                metadata = self.service._readImageMetadata(path)

            self.assertEqual(metadata.get("image_dimensions"), {"width": 800, "height": 600, "unit": "pixel"})
            self.assertEqual(metadata.get("image_orientation"), 6)
            self.assertEqual(metadata.get("xmp_content"), "<xmpmeta><rdf:RDF/></xmpmeta>")
            self.assertEqual(metadata.get("xmp_source"), "embedded_xmp_parsed")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
