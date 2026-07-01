import sys
from types import SimpleNamespace

from services.image_decode_service import ImageDecodeService


class _Config:
    def __init__(self, files):
        self.files = files

    def readMergedConfig(self):
        return {"files": self.files}


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
