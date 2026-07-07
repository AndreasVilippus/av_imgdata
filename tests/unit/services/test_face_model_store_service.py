import json
from datetime import datetime, timezone
from pathlib import Path

from services.face_model_store_service import FaceModelStoreError, FaceModelStoreService


class DummyConfigService:
    def __init__(self):
        self.config = {}

    def readConfig(self):
        return dict(self.config)

    def readMergedConfig(self):
        return dict(self.config)

    def writeConfig(self, config):
        self.config = config
        return True


def _clock():
    return datetime(2026, 7, 7, 20, 0, 0, tzinfo=timezone.utc)


def test_status_reports_missing_models_and_ack(tmp_path: Path):
    store = FaceModelStoreService(package_var=tmp_path, clock=_clock)

    status = store.status("buffalo_l")

    assert status["model_pack"] == "buffalo_l"
    assert status["models_present"] is False
    assert status["license_ack_present"] is False
    assert status["ready"] is False
    assert status["distributed_with_package"] is False
    assert status["root_source"] == "package_var"


def test_status_uses_configured_model_root(tmp_path: Path):
    configured_root = tmp_path / "configured-models"
    config = DummyConfigService()
    config.config = {
        "native_processors": {
            "FACE_PROCESSOR": {
                "MODEL_ROOT": str(configured_root),
                "MODEL_NAME": "buffalo_l",
            }
        }
    }
    store = FaceModelStoreService(config, package_var=tmp_path / "var", clock=_clock)

    status = store.status("buffalo_l")

    assert status["root"] == str(configured_root.resolve())
    assert status["root_source"] == "config"
    assert status["fallback_root"] == str(tmp_path / "var" / "models" / "face")
    assert status["files"]["det_10g.onnx"]["path"] == str(configured_root.resolve() / "buffalo_l" / "det_10g.onnx")


def test_acknowledge_usage_writes_ack_and_legacy_config_flag(tmp_path: Path):
    config = DummyConfigService()
    store = FaceModelStoreService(config, package_var=tmp_path, clock=_clock)

    ack = store.acknowledge_usage(model_pack="buffalo_l", accepted_by="tester", package_version="1.2.3")

    ack_path = tmp_path / "models" / "face" / "buffalo_l" / "LICENSE_ACK.json"
    assert ack_path.is_file()
    saved = json.loads(ack_path.read_text(encoding="utf-8"))
    assert saved["accepted_by"] == "tester"
    assert saved["accepted_at"] == "2026-07-07T20:00:00Z"
    assert ack["package_version"] == "1.2.3"
    assert config.config["native_processors"]["FACE_PROCESSOR"]["INSIGHTFACE_LICENSE_ACKNOWLEDGED"] is True
    assert config.config["native_processors"]["FACE_PROCESSOR"]["MODEL_NAME"] == "buffalo_l"


def test_import_model_files_copies_required_files_and_manifest(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "det_10g.onnx").write_bytes(b"detector")
    (source / "w600k_r50.onnx").write_bytes(b"recognizer")
    store = FaceModelStoreService(package_var=tmp_path / "var", clock=_clock)

    result = store.import_model_files(source, model_pack="buffalo_l", source="manual-test")

    model_dir = tmp_path / "var" / "models" / "face" / "buffalo_l"
    assert (model_dir / "det_10g.onnx").read_bytes() == b"detector"
    assert (model_dir / "w600k_r50.onnx").read_bytes() == b"recognizer"
    assert (model_dir / "manifest.json").is_file()
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "manual-test"
    assert {item["name"] for item in manifest["files"]} == {"det_10g.onnx", "w600k_r50.onnx"}
    assert result["models_present"] is True
    assert result["ready"] is False


def test_import_model_files_rejects_missing_required_file(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "det_10g.onnx").write_bytes(b"detector")
    store = FaceModelStoreService(package_var=tmp_path / "var", clock=_clock)

    try:
        store.import_model_files(source)
    except FaceModelStoreError as exc:
        assert str(exc) == "required_model_file_missing:w600k_r50.onnx"
    else:
        raise AssertionError("missing model file was not rejected")
