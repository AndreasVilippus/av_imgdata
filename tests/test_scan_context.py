#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService, ScanContext


def scan_config():
    return {
        "files": {
            "USE_EXIFTOOL": False,
            "USE_EXIFTOOL_FOR_SIDECARS": False,
            "SIDECAR_READ_MODE": "direct_only",
            "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
            "PREFER_EXIFTOOL_FOR_CONTEXT": False,
        },
        "metadata": {
            "SCHEMAS": {
                "ACD": False,
                "MICROSOFT": False,
                "MWG_REGIONS": False,
            }
        },
    }


class ScanContextTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_scan_context_initializes_per_scan_caches(self):
        context = ScanContext(scan_config())

        self.assertIsInstance(context.config, dict)
        self.assertIsNotNone(context.sidecar_cache)
        self.assertIsNotNone(context.photos_lookup_cache)
        self.assertEqual(context.metadata_context_cache, {})
        self.assertEqual(context.name_mapping_index, {})
        self.assertIsNone(context.io_metrics)

    def test_scan_context_initializes_io_metrics_when_enabled(self):
        config = scan_config()
        config["debug"] = {"IO_METRICS_ENABLED": True}

        context = ScanContext(config)

        self.assertIsNotNone(context.io_metrics)
        self.assertEqual(context.io_metrics.snapshot()["file_reads"], 0)
        context.io_metrics.file_reads += 1
        context.io_metrics.increment_cache_hit("metadata_context")
        self.assertEqual(context.io_metrics.snapshot()["file_reads"], 1)
        self.assertEqual(context.io_metrics.snapshot()["cache_hits"]["metadata_context"], 1)

    def test_readImageMetadata_uses_scan_context_config_and_sidecar_cache(self):
        context = ScanContext(scan_config())

        with patch.object(self.service.config, "readMergedConfig", side_effect=AssertionError("scan context config expected")), \
             patch.object(self.service.files, "findXmpForImage", return_value=None) as find_xmp_mock, \
             patch.object(self.service.files, "readJpegContext", return_value={"width": 100, "height": 80, "unit": "pixel", "orientation": 1}), \
             patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs) as parse_mock:
            metadata = self.service._readImageMetadata("/tmp/photo.jpg", scan_context=context)

        self.assertIs(find_xmp_mock.call_args.kwargs["lookup_cache"], context.sidecar_cache)
        self.assertFalse(parse_mock.call_args.kwargs["use_acd"])
        self.assertFalse(parse_mock.call_args.kwargs["use_microsoft"])
        self.assertFalse(parse_mock.call_args.kwargs["use_mwg_regions"])
        self.assertEqual(metadata["image_dimensions"], {"width": 100, "height": 80, "unit": "pixel"})

    def test_readImageMetadata_records_io_metrics_when_enabled(self):
        config = scan_config()
        config["debug"] = {"IO_METRICS_ENABLED": True}
        context = ScanContext(config)

        with patch.object(self.service.files, "findXmpForImage", return_value=None), \
             patch.object(self.service.files, "readJpegContext", return_value={"width": 100, "height": 80, "unit": "pixel", "orientation": 1}), \
             patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            self.service._readImageMetadata("/tmp/photo.jpg", scan_context=context)

        self.assertEqual(context.io_metrics.snapshot()["file_reads"], 1)

    def test_readImageMetadata_handles_non_jpeg_with_exiftool_available(self):
        config = scan_config()
        config["files"]["USE_EXIFTOOL"] = True
        context = ScanContext(config)

        with patch.object(self.service.files, "findXmpForImage", return_value=None), \
             patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", return_value=None), \
             patch.object(self.service.files, "readImageDimensions", return_value={"width": 50, "height": 40, "unit": "pixel"}), \
             patch.object(self.service.files, "readJpegExifOrientation", return_value=None), \
             patch.object(self.service.exiftool_handler, "readImageOrientation", return_value=6), \
             patch.object(self.service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = self.service._readImageMetadata("/tmp/photo.png", scan_context=context)

        self.assertEqual(metadata["image_dimensions"], {"width": 50, "height": 40, "unit": "pixel"})
        self.assertEqual(metadata["image_orientation"], 6)

    def test_loadPhotoFacesForImage_forwards_photos_lookup_cache(self):
        context = ScanContext(scan_config())

        with patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 42}) as find_mock, \
             patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]):
            faces = self.service._loadPhotoFacesForImage(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                shared_folder="/volume1/photo",
                image_path="/volume1/photo/trip/image.jpg",
                photos_lookup_cache=context.photos_lookup_cache,
            )

        self.assertEqual(faces, [])
        self.assertIs(find_mock.call_args.kwargs["lookup_cache"], context.photos_lookup_cache)


if __name__ == "__main__":
    unittest.main()
