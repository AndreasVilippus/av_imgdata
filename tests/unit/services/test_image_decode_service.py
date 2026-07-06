import sys
from types import SimpleNamespace

from services.image_decode_service import ImageDecodeService


class _Config:
    def __init__(self, files, native_processors=None):
        self.files = files
        self.native_processors = native_processors or {}

    def readMergedConfig(self):
        return {"files": self.files, "native_processors": self.native_processors}


def test_decoder_ignores_extensions_outside_config(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    service = ImageDecodeService(_Config({"IMAGE_DECODER_EXTENSIONS": ["heic"], "IMAGE_DECODER_ENABLED": True}))

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is False
    assert result.error == "image_decoder_extension_not_enabled"


def test_pillow_heif_decoder_returns_jpeg_bytes(monkeypatch, tmp_path):
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    registered = []

    class _Image:
        mode = "RGB"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def thumbnail(self, size, resampling=None):
            self.thumbnail_size = size
            self.thumbnail_resampling = resampling

        def save(self, output, **_kwargs):
            output.write(b"\xff\xd8jpeg")

    fake_image_module = SimpleNamespace(open=lambda _path: _Image())
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=fake_image_module))
    monkeypatch.setitem(sys.modules, "pillow_heif", SimpleNamespace(register_heif_opener=lambda: registered.append(True)))
    service = ImageDecodeService(_Config({
        "IMAGE_DECODER_ENABLED": True,
        "IMAGE_DECODER_EXTENSIONS": ["heic", "heif"],
        "IMAGE_DECODER_ORDER": ["pillow-heif"],
    }))

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is True
    assert result.source == "pillow-heif"
    assert result.image_bytes == b"\xff\xd8jpeg"
    assert registered == [True]


def test_vips_preferred_decoder_runs_before_configured_fallback(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    calls = []

    class _VipsProcessor:
        def status(self):
            return {"available": True, "formats": {"jpeg": True}}

        def process_image(self, path, operation, options, output_format):
            calls.append((path, operation, options, output_format))
            return {"success": True, "image_bytes": b"\xff\xd8vips-jpeg"}

    service = ImageDecodeService(
        _Config(
            {
                "IMAGE_DECODER_ENABLED": True,
                "IMAGE_DECODER_EXTENSIONS": ["heic"],
                "IMAGE_DECODER_ORDER": ["pillow-heif"],
                "IMAGE_DECODER_MAX_EDGE": 1024,
            },
            native_processors={
                "IMAGE_PROCESSOR_VIPS": {
                    "ENABLED": True,
                    "PREFERRED": True,
                    "ALLOW_FALLBACK_TO_DEFAULT": True,
                },
            },
        ),
        vips_processor=_VipsProcessor(),
    )

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is True
    assert result.source == "libvips"
    assert result.image_bytes == b"\xff\xd8vips-jpeg"
    assert calls == [(image_path, "resize", {"quality": 95, "width": 1024, "height": 1024, "maintain_aspect": True}, "jpeg")]


def test_vips_preferred_decoder_batches_multiple_images(tmp_path):
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    image_a.write_bytes(b"jpeg-a")
    image_b.write_bytes(b"jpeg-b")
    calls = []

    class _VipsProcessor:
        def status(self):
            return {"available": True, "formats": {"jpeg": True, "jpg": True}}

        def batch_process_images(self, paths, operation, options, output_format):
            calls.append((list(paths), operation, options, output_format))
            return [
                {"path": str(path), "success": True, "image_bytes": b"\xff\xd8batch-" + path.name.encode("ascii")}
                for path in paths
            ]

        def process_image(self, *_args, **_kwargs):
            raise AssertionError("decode_many_to_jpeg must use the libvips batch command")

    service = ImageDecodeService(
        _Config(
            {
                "IMAGE_DECODER_ENABLED": True,
                "IMAGE_DECODER_EXTENSIONS": ["heic"],
                "IMAGE_DECODER_ORDER": ["pillow-heif"],
                "IMAGE_DECODER_MAX_EDGE": 1024,
            },
            native_processors={
                "IMAGE_PROCESSOR_VIPS": {
                    "ENABLED": True,
                    "PREFERRED": True,
                    "ALLOW_FALLBACK_TO_DEFAULT": True,
                },
            },
        ),
        vips_processor=_VipsProcessor(),
    )

    results = service.decode_many_to_jpeg([str(image_a), str(image_b)])

    assert results[str(image_a)].success is True
    assert results[str(image_a)].source == "libvips"
    assert results[str(image_a)].image_bytes == b"\xff\xd8batch-a.jpg"
    assert results[str(image_b)].success is True
    assert calls == [([image_a, image_b], "resize", {"quality": 95, "width": 1024, "height": 1024, "maintain_aspect": True}, "jpeg")]


def test_vips_preferred_decoder_skips_heic_when_probe_reports_no_heif(monkeypatch, tmp_path):
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    registered = []

    class _VipsProcessor:
        def status(self):
            return {"available": True, "formats": {"jpeg": True, "heic": False, "heif": False}}

        def process_image(self, *_args, **_kwargs):
            raise AssertionError("HEIC must not be sent to libvips when probe reports no HEIF loader")

    class _Image:
        mode = "RGB"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def thumbnail(self, *_args, **_kwargs):
            pass

        def save(self, output, **_kwargs):
            output.write(b"\xff\xd8pillow-heif")

    fake_image_module = SimpleNamespace(open=lambda _path: _Image())
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=fake_image_module))
    monkeypatch.setitem(sys.modules, "pillow_heif", SimpleNamespace(register_heif_opener=lambda: registered.append(True)))
    service = ImageDecodeService(
        _Config(
            {
                "IMAGE_DECODER_ENABLED": True,
                "IMAGE_DECODER_EXTENSIONS": ["heic"],
                "IMAGE_DECODER_ORDER": ["pillow-heif"],
            },
            native_processors={
                "IMAGE_PROCESSOR_VIPS": {
                    "ENABLED": True,
                    "PREFERRED": True,
                    "ALLOW_FALLBACK_TO_DEFAULT": True,
                },
            },
        ),
        vips_processor=_VipsProcessor(),
    )

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is True
    assert result.source == "pillow-heif"
    assert result.image_bytes == b"\xff\xd8pillow-heif"
    assert registered == [True]


def test_vips_preferred_decoder_blocks_fallback_when_configured(tmp_path):
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")

    class _VipsProcessor:
        def status(self):
            return {"available": True, "formats": {"heic": True, "heif": True}}

        def process_image(self, *_args, **_kwargs):
            return {"success": False, "error": "vips_failed"}

    service = ImageDecodeService(
        _Config(
            {
                "IMAGE_DECODER_ENABLED": True,
                "IMAGE_DECODER_EXTENSIONS": ["heic"],
                "IMAGE_DECODER_ORDER": ["pillow-heif"],
            },
            native_processors={
                "IMAGE_PROCESSOR_VIPS": {
                    "ENABLED": True,
                    "PREFERRED": True,
                    "ALLOW_FALLBACK_TO_DEFAULT": False,
                },
            },
        ),
        vips_processor=_VipsProcessor(),
    )

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is False
    assert result.source == "libvips"
    assert result.error == "libvips:vips_failed"


def test_pillow_heif_decoder_limits_image_edge(monkeypatch, tmp_path):
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    images = []

    class _Image:
        mode = "RGB"

        def __enter__(self):
            images.append(self)
            return self

        def __exit__(self, *_args):
            return False

        def thumbnail(self, size, resampling=None):
            self.thumbnail_size = size
            self.thumbnail_resampling = resampling

        def save(self, output, **_kwargs):
            output.write(b"\xff\xd8jpeg")

    fake_image_module = SimpleNamespace(open=lambda _path: _Image(), Resampling=SimpleNamespace(LANCZOS="lanczos"))
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=fake_image_module))
    monkeypatch.setitem(sys.modules, "pillow_heif", SimpleNamespace(register_heif_opener=lambda: None))
    service = ImageDecodeService(_Config({
        "IMAGE_DECODER_ENABLED": True,
        "IMAGE_DECODER_EXTENSIONS": ["heic"],
        "IMAGE_DECODER_ORDER": ["pillow-heif"],
        "IMAGE_DECODER_MAX_EDGE": 2048,
    }))

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is True
    assert images[0].thumbnail_size == (2048, 2048)


def test_external_decoder_uses_configured_binary(monkeypatch, tmp_path):
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    executable = tmp_path / "heif-convert"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        output_path = command[-1]
        with open(output_path, "wb") as handle:
            handle.write(b"\xff\xd8jpeg")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("services.image_decode_service.subprocess.run", fake_run)
    service = ImageDecodeService(_Config({
        "IMAGE_DECODER_ENABLED": True,
        "IMAGE_DECODER_EXTENSIONS": ["heic"],
        "IMAGE_DECODER_ORDER": ["heif-convert"],
        "PATH_HEIF_CONVERT": str(executable),
    }))

    result = service.decode_to_jpeg(str(image_path))

    assert result.success is True
    assert result.source == "heif-convert"
    assert commands[0][:3] == [str(executable), "-q", "95"]
