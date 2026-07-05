import time
from pathlib import Path

from services.config_service import ConfigService
from services.native_image_processor_vips_service import NativeImageProcessorVipsService


def _write_vips_skeleton(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "version":
    print("av-imgdata-image-processor 0.1.0-skeleton image-backend-vips")
    raise SystemExit(0)
if cmd == "probe":
    print(json.dumps({
        "contract_version": "1.0",
        "backend": "skeleton",
        "available": False,
        "reason": "vips_probe_failed",
        "formats": {"jpeg": False, "png": False},
        "error": {"code": "libvips_not_linked", "message": "libvips image backend is not linked"},
    }))
    raise SystemExit(1)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_vips_ready(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "version":
    print("av-imgdata-image-processor 0.2.0 libvips 8-test")
    raise SystemExit(0)
if cmd == "probe":
    print(json.dumps({
        "contract_version": "1.0",
        "backend": "libvips",
        "available": True,
        "reason": "vips_ready",
        "formats": {"jpeg": True, "png": True, "webp": False},
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_vips_image_processor_disabled_by_default(tmp_path):
    service = NativeImageProcessorVipsService(ConfigService(str(tmp_path / "config.json")), package_root=tmp_path)

    status = service.status()

    assert status["enabled"] is False
    assert status["available"] is False
    assert status["reason"] == "vips_disabled"
    assert status["fallback"] == "default_image_backend"


def test_vips_image_processor_reports_missing_binary_when_enabled(tmp_path):
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)

    status = service.status()

    assert status["enabled"] is True
    assert status["available"] is False
    assert status["reason"] == "vips_binary_missing"


def test_vips_image_processor_skeleton_is_not_available(tmp_path):
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_skeleton(binary)
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)

    status = service.status()

    assert status["present"] is True
    assert status["executable"] is True
    assert status["available"] is False
    assert status["reason"] == "vips_probe_failed"
    assert status["backend"] == "skeleton"
    assert "not linked" in status["last_error"]


def test_vips_status_logs_skeleton_probe_failure(tmp_path):
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_skeleton(binary)
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    events = []
    service = NativeImageProcessorVipsService(
        config,
        package_root=tmp_path,
        debug_logger=lambda event, **fields: events.append((event, fields)),
    )

    service.status()

    status_events = [fields for event, fields in events if event == "native_image_processor_vips_status"]
    run_failed_events = [fields for event, fields in events if event == "native_image_processor_vips_run_failed"]
    assert status_events
    assert status_events[-1]["reason"] == "vips_probe_failed"
    assert status_events[-1]["backend"] == "skeleton"
    assert status_events[-1]["probe_error_code"] == "libvips_not_linked"
    assert run_failed_events
    assert run_failed_events[-1]["command"] == "probe"


def test_vips_image_processor_ready_probe_reports_formats(tmp_path):
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)

    status = service.status()

    assert status["available"] is True
    assert status["reason"] == "vips_ready"
    assert status["backend"] == "libvips"
    assert status["formats"]["jpeg"] is True
    assert status["formats"]["webp"] is False


def test_vips_image_processor_status_uses_short_cache(monkeypatch, tmp_path):
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({
        "native_processors": {
            "IMAGE_PROCESSOR_VIPS": {
                "ENABLED": True,
                "STATUS_CACHE_SECONDS": 60,
            },
        },
    })
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    calls = []
    original_run_simple = service._run_simple

    def recorded_run_simple(command):
        calls.append(command)
        return original_run_simple(command)

    monkeypatch.setattr(service, "_run_simple", recorded_run_simple)

    first = service.status()
    second = service.status()
    forced = service.status(force=True)

    assert first["available"] is True
    assert first["cache_hit"] is False
    assert second["available"] is True
    assert second["cache_hit"] is True
    assert forced["cache_hit"] is False
    assert len(calls) == 4


def test_vips_image_processor_background_status_returns_stale_cache(monkeypatch, tmp_path):
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({
        "native_processors": {
            "IMAGE_PROCESSOR_VIPS": {
                "ENABLED": True,
                "STATUS_CACHE_SECONDS": 1,
            },
        },
    })
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    first = service.status()
    cache_key, _, cache_value = service._status_cache
    service._status_cache = (cache_key, time.monotonic() - 10, cache_value)
    refresh_calls = []

    monkeypatch.setattr(service, "refresh_status_background", lambda: refresh_calls.append(True) or True)
    monkeypatch.setattr(
        service,
        "_run_simple",
        lambda command: (_ for _ in ()).throw(AssertionError("background status must not probe synchronously")),
    )

    stale = service.status(background=True)

    assert first["available"] is True
    assert stale["available"] is True
    assert stale["cache_hit"] is False
    assert stale["cache_stale"] is True
    assert refresh_calls == [True]


def test_vips_process_image_disabled_returns_error(tmp_path):
    """Test that disabled processor returns error."""
    config = ConfigService(str(tmp_path / "config.json"))
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    # Create dummy image path
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake image data")
    
    result = service.process_image(image_path, "resize", {"width": 100, "height": 100})
    
    assert result["success"] is False
    assert "disabled" in result.get("error", "").lower()


def test_vips_process_image_not_found_returns_error(tmp_path):
    """Test that missing image returns error."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    result = service.process_image(tmp_path / "nonexistent.jpg", "resize", {"width": 100})
    
    assert result["success"] is False
    assert result["error"] == "image_not_found"


def test_vips_parse_processor_result_keeps_temporary_output_bytes(tmp_path):
    output_image = tmp_path / "output.jpeg"
    output_image.write_bytes(b"\xff\xd8vips-jpeg")
    result_json = tmp_path / "processor-result.json"
    result_json.write_text(
        '{"success": true, "output_path": "' + str(output_image) + '", "output_format": "jpeg"}',
        encoding="utf-8",
    )

    result = NativeImageProcessorVipsService._parse_processor_result({"ok": True}, result_json)

    assert result["success"] is True
    assert result["image_bytes"] == b"\xff\xd8vips-jpeg"


def test_vips_resize_image(tmp_path):
    """Test resize operation."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    # Create dummy image
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    result = service.resize_image(image_path, 640, 480, "jpeg", 95)
    
    # Should have success/error keys
    assert "success" in result
    assert isinstance(result, dict)


def test_vips_rotate_image_invalid_angle(tmp_path):
    """Test rotate with invalid angle."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    result = service.rotate_image(image_path, 45)  # Invalid angle
    
    assert result["success"] is False
    assert "invalid_rotation_angle" in result["error"]


def test_vips_auto_orient_image(tmp_path):
    """Test auto-orient operation."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    result = service.auto_orient_image(image_path)
    
    assert isinstance(result, dict)
    assert "success" in result


def test_vips_batch_process_images(tmp_path):
    """Test batch processing."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    # Create multiple dummy images
    images = []
    for i in range(3):
        img_path = tmp_path / f"test{i}.jpg"
        img_path.write_bytes(b"fake jpeg")
        images.append(img_path)
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    results = service.batch_process_images(images, "resize", {"width": 100, "height": 100})
    
    assert len(results) == 3
    assert all("path" in r for r in results)
    assert all("success" in r for r in results)


def test_vips_get_image_info(tmp_path):
    """Test getting image information."""
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    result = service.get_image_info(image_path)
    
    assert isinstance(result, dict)
    assert "success" in result


def test_vips_native_image_processor(tmp_path):
    """Test NativeImageProcessor class."""
    from services.native_image_processor_vips_service import NativeImageProcessor
    
    binary = tmp_path / "bin" / "av-imgdata-image-processor"
    binary.parent.mkdir(parents=True)
    _write_vips_ready(binary)
    
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    config.writeConfig({"native_processors": {"IMAGE_PROCESSOR_VIPS": {"ENABLED": True}}})
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    processor = NativeImageProcessor(service, image_path, "jpeg", 95)
    
    assert processor.is_available is True
    assert processor.quality == 95
    assert processor.output_format == "jpeg"


def test_vips_native_image_processor_unavailable_raises(tmp_path):
    """Test NativeImageProcessor raises when unavailable."""
    from services.native_image_processor_vips_service import (
        NativeImageProcessor,
        NativeImageProcessorVipsUnavailable,
    )
    
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake jpeg")
    
    config = ConfigService(str(tmp_path / "config.json"))
    service = NativeImageProcessorVipsService(config, package_root=tmp_path)
    
    processor = NativeImageProcessor(service, image_path)
    
    # Should raise when trying to use unavailable processor
    try:
        processor.info()
        assert False, "Should have raised NativeImageProcessorVipsUnavailable"
    except NativeImageProcessorVipsUnavailable:
        pass
