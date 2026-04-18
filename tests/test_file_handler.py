#!/usr/bin/env python3
import json
import os
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


if __name__ == "__main__":
    unittest.main()
