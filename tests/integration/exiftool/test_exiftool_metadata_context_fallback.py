import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _config(*, prefer_context=False):
    return {
        "files": {
            "USE_EXIFTOOL": True,
            "USE_EXIFTOOL_FOR_SIDECARS": False,
            "SIDECAR_EXIFTOOL_FALLBACK_ENABLED": False,
            "SIDECAR_READ_MODE": "direct_only",
            "PREFER_EXIFTOOL_FOR_CONTEXT": prefer_context,
            "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
            "EXIFTOOL_PERSISTENT_ENABLED": True,
        },
        "metadata": {
            "SCHEMAS": {
                "ACD": False,
                "MICROSOFT": False,
                "MWG_REGIONS": False,
            }
        },
    }


def test_heic_metadata_fallback_uses_single_exiftool_context_when_native_values_are_missing():
    service = ImgDataService(SessionManager())

    with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as handle:
        image_path = handle.name
        handle.write(b"not-a-real-heic-but-suffix-is-enough-for-this-contract")

    context = {
        "success": True,
        "xmp_content": "<xmpmeta><rdf:RDF/></xmpmeta>",
        "image_dimensions": {"width": 4032, "height": 3024, "unit": "pixel"},
        "image_orientation": 6,
        "error": None,
    }

    try:
        with patch.object(service.config, "readMergedConfig", return_value=_config(prefer_context=False)),              patch.object(service.files, "findXmpForImage", return_value=None),              patch.object(service.files, "readImageDimensions", return_value={"width": None, "height": None, "unit": "pixel"}) as native_dimensions,              patch.object(service.files, "readJpegExifOrientation", return_value=None) as native_orientation,              patch.object(service.files, "loadXmpFromImageParsed", side_effect=AssertionError("native full scan must stay disabled")),              patch.object(service.exiftool_handler, "isAvailable", return_value=True),              patch.object(service.exiftool_handler, "readMetadataContext", return_value=context) as read_context,              patch.object(service.exiftool_handler, "loadEmbeddedXmp", side_effect=AssertionError("fallback should use bundled context, not a separate XMP call")),              patch.object(service.exiftool_handler, "readImageDimensions", side_effect=AssertionError("fallback should use bundled context, not a separate dimension call")),              patch.object(service.exiftool_handler, "readImageOrientation", side_effect=AssertionError("fallback should use bundled context, not a separate orientation call")),              patch.object(service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = service._readImageMetadata(image_path)

        native_dimensions.assert_called_once()
        native_orientation.assert_called_once()
        read_context.assert_called_once_with(image_path, include_xmp=False)
        assert metadata.get("xmp_content") in (None, "")
        assert metadata["image_dimensions"] == {"width": 4032, "height": 3024, "unit": "pixel"}
        assert metadata["image_orientation"] == 6
    finally:
        Path(image_path).unlink(missing_ok=True)


def test_metadata_context_label_distinguishes_orientation_and_size_from_face_metadata():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")
    german = Path("ui/texts/ger/strings").read_text(encoding="utf-8")
    english = Path("ui/texts/enu/strings").read_text(encoding="utf-8")

    assert "Metadaten (Orientierung, Größe, ...)" in german
    assert "metadata (orientation, size, ...)" in english
    assert "metadata (orientation, size, ...)" in view



def test_metadata_context_is_not_called_when_only_xmp_is_missing_and_native_context_is_complete():
    service = ImgDataService(SessionManager())

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        image_path = handle.name
        handle.write(b"\xff\xd8\xff\xd9")

    try:
        with patch.object(service.config, "readMergedConfig", return_value=_config(prefer_context=False)), \
             patch.object(service.files, "findXmpForImage", return_value=None), \
             patch.object(service.files, "readImageDimensions", return_value={"width": 50, "height": 40, "unit": "pixel"}), \
             patch.object(service.files, "readJpegExifOrientation", return_value=1), \
             patch.object(service.files, "loadXmpFromImageParsed", return_value=None), \
             patch.object(service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(service.exiftool_handler, "readMetadataContext", side_effect=AssertionError("must not call ExifTool context for XMP-only miss")), \
             patch.object(service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = service._readImageMetadata(image_path)

        assert metadata["image_dimensions"] == {"width": 50, "height": 40, "unit": "pixel"}
        assert metadata["image_orientation"] == 1
    finally:
        Path(image_path).unlink(missing_ok=True)


def test_metadata_context_fallback_can_be_disabled_for_scan_face_checks():
    service = ImgDataService(SessionManager())

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
        image_path = handle.name
        handle.write(b"\xff\xd8\xff\xda")

    try:
        with patch.object(service.config, "readMergedConfig", return_value=_config(prefer_context=False)), \
             patch.object(service.files, "findXmpForImage", return_value=None), \
             patch.object(service.files, "readJpegContext", return_value={"width": 100, "height": 80, "unit": "pixel", "orientation": None}), \
             patch.object(service.files, "readImageDimensions", side_effect=AssertionError("JPEG context should provide dimensions")), \
             patch.object(service.files, "readJpegExifOrientation", side_effect=AssertionError("JPEG context should provide orientation result")), \
             patch.object(service.files, "loadXmpFromImageParsed", return_value=None), \
             patch.object(service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(service.exiftool_handler, "readMetadataContext", side_effect=AssertionError("disabled fallback must not call ExifTool")), \
             patch.object(service.exiftool_handler, "readImageOrientation", side_effect=AssertionError("disabled fallback must not call ExifTool orientation")), \
             patch.object(service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = service._readImageMetadata(
                image_path,
                allow_exiftool_context_fallback=False,
            )

        assert metadata["image_dimensions"] == {"width": 100, "height": 80, "unit": "pixel"}
        assert metadata["image_orientation"] is None
    finally:
        Path(image_path).unlink(missing_ok=True)


def test_precomputed_jpeg_context_is_reused_without_second_header_read():
    service = ImgDataService(SessionManager())

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
        image_path = handle.name
        handle.write(b"\xff\xd8\xff\xda")

    try:
        with patch.object(service.config, "readMergedConfig", return_value=_config(prefer_context=False)), \
             patch.object(service.files, "findXmpForImage", return_value=None), \
             patch.object(service.files, "readJpegContext", side_effect=AssertionError("precomputed JPEG context should be reused")), \
             patch.object(service.files, "readImageDimensions", side_effect=AssertionError("JPEG context should provide dimensions")), \
             patch.object(service.files, "readJpegExifOrientation", side_effect=AssertionError("JPEG context should provide orientation")), \
             patch.object(service.exiftool_handler, "isAvailable", return_value=False), \
             patch.object(service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = service._readImageMetadata(
                image_path,
                jpeg_context_override={
                    "width": 120,
                    "height": 90,
                    "unit": "pixel",
                    "orientation": 1,
                    "xmp_content": "<xmpmeta><rdf:RDF/></xmpmeta>",
                    "xmp_source": "embedded_xmp_parsed",
                },
            )

        assert metadata["image_dimensions"] == {"width": 120, "height": 90, "unit": "pixel"}
        assert metadata["image_orientation"] == 1
        assert metadata["xmp_content"] == "<xmpmeta><rdf:RDF/></xmpmeta>"
    finally:
        Path(image_path).unlink(missing_ok=True)


def test_exiftool_sidecar_read_can_be_disabled_for_scan_face_checks():
    service = ImgDataService(SessionManager())

    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = str(Path(tmp_dir) / "photo.jpg")
        xmp_path = str(Path(tmp_dir) / "photo.xmp")
        Path(image_path).write_bytes(b"\xff\xd8\xff\xda")

        config = _config(prefer_context=False)
        config["files"]["USE_EXIFTOOL"] = True
        config["files"]["USE_EXIFTOOL_FOR_SIDECARS"] = True
        config["files"]["SIDECAR_READ_MODE"] = "exiftool_first"

        with patch.object(service.config, "readMergedConfig", return_value=config), \
             patch.object(service.files, "findXmpForImage", return_value=xmp_path), \
             patch.object(service.files, "loadXmpFromFile", return_value="<xmpmeta><rdf:RDF/></xmpmeta>") as direct_read, \
             patch.object(service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(service.exiftool_handler, "loadXmpFile", side_effect=AssertionError("disabled sidecar path must not call ExifTool")), \
             patch.object(service.files, "readJpegContext", return_value={"width": 120, "height": 90, "unit": "pixel", "orientation": 1}), \
             patch.object(service.metadata_parser, "parse", side_effect=lambda **kwargs: kwargs):
            metadata = service._readImageMetadata(
                image_path,
                allow_exiftool_sidecar_read=False,
            )

        direct_read.assert_called_once_with(xmp_path)
        assert metadata["xmp_content"] == "<xmpmeta><rdf:RDF/></xmpmeta>"
