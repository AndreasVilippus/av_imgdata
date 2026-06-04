#!/usr/bin/env python3
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))

from handler.file_handler import FileHandler
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from services.config_service import ConfigService


class FileHandlerPhotosComparisonTests(unittest.TestCase):
    def _build_handler(self, *, position_include_photos=True, name_include_photos=True):
        defaults = ConfigService.defaultConfig()
        config = {
            **defaults,
            "analysis": {
                "CHECKS": {
                    **defaults["analysis"]["CHECKS"],
                    "POSITION_DEVIATIONS_INCLUDE_PHOTOS": position_include_photos,
                    "NAME_CONFLICTS_INCLUDE_PHOTOS": name_include_photos,
                },
            },
        }
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        config_path = os.path.join(tempdir.name, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        return FileHandler(ConfigService(config_path))

    @staticmethod
    def _payload_with_face(name, *, x, y):
        return MetadataPayload(
            image_path="/volume1/photo/test.jpg",
            faces=[
                MetadataFace.from_center_box(
                    name=name,
                    x=x,
                    y=y,
                    w=0.2,
                    h=0.2,
                    source="embedded_xmp_exiftool",
                    source_format="MICROSOFT",
                ),
            ],
        )

    @staticmethod
    def _photos_face(name, *, x, y):
        return {
            "name": name,
            "x": x,
            "y": y,
            "w": 0.2,
            "h": 0.2,
            "source": "photos",
            "source_format": "PHOTOS",
        }

    def test_analyze_metadata_can_include_photos_for_position_deviations(self):
        handler = self._build_handler(position_include_photos=True)
        payload = self._payload_with_face("Alice", x=0.2, y=0.2)

        analysis = handler.analyzeMetadata(
            payload,
            comparison_faces=[self._photos_face("Alice", x=0.7, y=0.7)],
            include_position_deviation_comparison_faces=True,
        )

        self.assertEqual(analysis["files_with_face_position_deviations"], 1)

    def test_analyze_metadata_can_include_photos_for_name_conflicts(self):
        handler = self._build_handler(name_include_photos=True)
        payload = self._payload_with_face("Alice", x=0.4, y=0.4)

        analysis = handler.analyzeMetadata(
            payload,
            comparison_faces=[self._photos_face("Bob", x=0.42, y=0.42)],
            include_name_conflict_comparison_faces=True,
        )

        self.assertEqual(analysis["files_with_name_conflicts"], 1)

    def test_oriented_image_dimensions_swap_width_height_for_rotated_exif_orientation(self):
        self.assertEqual(
            FileHandler._orientedImageDimensions({"width": 800, "height": 600, "unit": "pixel"}, 6),
            {"width": 600, "height": 800, "unit": "pixel"},
        )
        self.assertEqual(
            FileHandler._orientedImageDimensions({"width": 800, "height": 600, "unit": "pixel"}, 8),
            {"width": 600, "height": 800, "unit": "pixel"},
        )
        self.assertEqual(
            FileHandler._orientedImageDimensions({"width": 800, "height": 600, "unit": "pixel"}, 3),
            {"width": 800, "height": 600, "unit": "pixel"},
        )

    def test_configured_metadata_schemas_includes_iptc_regions(self):
        defaults = ConfigService.defaultConfig()
        config = {
            **defaults,
            "metadata": {
                "SCHEMAS": {
                    **defaults["metadata"]["SCHEMAS"],
                    "IPTC_EXT_REGIONS": False,
                },
            },
        }
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        config_path = os.path.join(tempdir.name, "config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)

        schemas = FileHandler(ConfigService(config_path)).configuredMetadataSchemas()

        self.assertIn("IPTC_EXT_REGIONS", schemas)
        self.assertFalse(schemas["IPTC_EXT_REGIONS"])


class FileHandlerRawPreviewTests(unittest.TestCase):
    def test_extract_embedded_jpeg_preview_from_arw_tiff_tags(self):
        jpeg = b"\xff\xd8embedded-preview\xff\xd9"
        jpeg_offset = 128
        jpeg_length = len(jpeg)
        data = bytearray(b"\x00" * (jpeg_offset + jpeg_length))
        data[0:8] = b"II" + struct.pack("<HI", 42, 8)
        data[8:10] = struct.pack("<H", 2)
        data[10:22] = struct.pack("<HHI4s", 0x0201, 4, 1, struct.pack("<I", jpeg_offset))
        data[22:34] = struct.pack("<HHI4s", 0x0202, 4, 1, struct.pack("<I", jpeg_length))
        data[34:38] = struct.pack("<I", 0)
        data[jpeg_offset:jpeg_offset + jpeg_length] = jpeg

        with tempfile.NamedTemporaryFile(suffix=".ARW") as handle:
            handle.write(data)
            handle.flush()

            self.assertEqual(FileHandler.extractEmbeddedJpegPreview(handle.name), jpeg)

    def test_extract_embedded_jpeg_preview_ignores_non_raw_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as handle:
            handle.write(b"\xff\xd8embedded-preview\xff\xd9")
            handle.flush()

            self.assertIsNone(FileHandler.extractEmbeddedJpegPreview(handle.name))

    def test_extract_embedded_jpeg_preview_falls_back_to_embedded_segment(self):
        jpeg = b"\xff\xd8fallback-preview\xff\xd9"
        jpeg_offset = 32770
        data = bytearray(b"\x00" * (jpeg_offset + len(jpeg)))
        data[0:8] = b"II" + struct.pack("<HI", 42, 8)
        data[8:10] = struct.pack("<H", 2)
        data[10:22] = struct.pack("<HHI4s", 0x0201, 4, 1, struct.pack("<I", jpeg_offset + 1000))
        data[22:34] = struct.pack("<HHI4s", 0x0202, 4, 1, struct.pack("<I", len(jpeg)))
        data[34:38] = struct.pack("<I", 0)
        data[jpeg_offset:jpeg_offset + len(jpeg)] = jpeg

        with tempfile.NamedTemporaryFile(suffix=".ARW") as handle:
            handle.write(data)
            handle.flush()

            self.assertEqual(FileHandler.extractEmbeddedJpegPreview(handle.name), jpeg)


if __name__ == "__main__":
    unittest.main()
