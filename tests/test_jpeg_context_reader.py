#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from handler.file_handler import FileHandler


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def sof_segment(width: int, height: int, marker: int = 0xC0) -> bytes:
    return jpeg_segment(
        marker,
        b"\x08"
        + int(height).to_bytes(2, "big")
        + int(width).to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00",
    )


def exif_orientation_segment(orientation: int) -> bytes:
    tiff = (
        b"MM"
        + (42).to_bytes(2, "big")
        + (8).to_bytes(4, "big")
        + (1).to_bytes(2, "big")
        + (0x0112).to_bytes(2, "big")
        + (3).to_bytes(2, "big")
        + (1).to_bytes(4, "big")
        + int(orientation).to_bytes(2, "big")
        + b"\x00\x00"
        + (0).to_bytes(4, "big")
    )
    return jpeg_segment(0xE1, b"Exif\x00\x00" + tiff)


def xmp_segment(xmp: str) -> bytes:
    return jpeg_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + xmp.encode("utf-8"))


class JpegContextReaderTests(unittest.TestCase):
    def _write_jpeg(self, payload: bytes) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / "image.jpg"
        path.write_bytes(payload)
        return path

    def test_reads_dimensions_orientation_and_xmp(self):
        path = self._write_jpeg(
            b"\xff\xd8"
            + exif_orientation_segment(6)
            + xmp_segment("<x:xmpmeta>ok</x:xmpmeta>")
            + sof_segment(1024, 768)
            + b"\xff\xda\x00\x02"
        )

        context = FileHandler.readJpegContext(str(path))

        self.assertEqual(context["width"], 1024)
        self.assertEqual(context["height"], 768)
        self.assertEqual(context["orientation"], 6)
        self.assertEqual(context["xmp_content"], "<x:xmpmeta>ok</x:xmpmeta>")
        self.assertEqual(context["xmp_source"], "embedded_xmp_parsed")

    def test_reads_orientation_when_xmp_is_not_requested(self):
        path = self._write_jpeg(
            b"\xff\xd8"
            + exif_orientation_segment(8)
            + sof_segment(640, 480)
            + b"\xff\xda\x00\x02"
        )

        context = FileHandler.readJpegContext(str(path), include_xmp=False)

        self.assertEqual(context["width"], 640)
        self.assertEqual(context["height"], 480)
        self.assertEqual(context["orientation"], 8)
        self.assertIsNone(context["xmp_content"])

    def test_progressive_jpeg_dimensions_are_supported(self):
        path = self._write_jpeg(b"\xff\xd8" + sof_segment(300, 200, marker=0xC2) + b"\xff\xda\x00\x02")

        context = FileHandler.readJpegContext(str(path), include_xmp=False)

        self.assertEqual(context["width"], 300)
        self.assertEqual(context["height"], 200)

    def test_corrupt_jpeg_returns_empty_context(self):
        path = self._write_jpeg(b"not-a-jpeg")

        context = FileHandler.readJpegContext(str(path))

        self.assertIsNone(context["width"])
        self.assertIsNone(context["height"])
        self.assertIsNone(context["orientation"])
        self.assertIsNone(context["xmp_content"])

    def test_respects_max_scan_bytes(self):
        path = self._write_jpeg(b"\xff\xd8" + (b"\x00" * 256) + sof_segment(300, 200))

        context = FileHandler.readJpegContext(str(path), include_xmp=False, max_scan_bytes=16)

        self.assertIsNone(context["width"])
        self.assertLessEqual(context["scanned_bytes"], 16)


if __name__ == "__main__":
    unittest.main()
