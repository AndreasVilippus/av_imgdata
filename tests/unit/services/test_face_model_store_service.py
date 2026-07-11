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


def test_status_reports_missing_models_from_canonical_package_store(tmp_path: Path):
    store = FaceModelStoreService(package_var=tmp_path, clock=_clock)

    status = store.status("buffalo_l")

    expected_root = (tmp_path / "insightface_models").resolve()
    expected_store = (expected_root / "models").resolve()
    assert status["model_pack"] == "buffalo_l"
    assert status["models_present"] is False
    assert status["license_ack_present"] is False
    assert status["ready"] is False
    assert status["distributed_with_package"] is False
    assert status["root_source"] == "package_var"
    assert status["insightface_root"] == str(expected_root)
    assert status["root"] == str(expected_store)
    assert status["fallback_root"] == str(expected_store)
    assert status["model_dir"] == str(expected_store / "buffalo_l")


def test_status_uses_configured_insightface_root_and_models_child(tmp_path: Path):
    configured_root = tmp_path / "configured-insightface"
    package_var = tmp_path / "var"
    config = DummyConfigService()
    config.config = {
        "native_processors": {
            "FACE_PROCESSOR": {
                "MODEL_ROOT": str(configured_root),
                "MODEL_NAME": "buffalo_l",
            }
        }
    }
    store = FaceModelStoreService(config, package_var=package_var, clock=_clock)

    status = store.status("buffalo_l")

    expected_store = (configured_root / "models").resolve()
    expected_fallback = (package_var / "insightface_models" / "models").resolve()
    assert status["insightface_root"] == str(configured_root.resolve())
    assert status["root"] == str(expected_store)
    assert status["root_source"] == "config"
    assert status["fallback_root"] == str(expected_fallback)
    assert status["files"]["det_10g.onnx"]["path"] == str(
        expected_store / "buffalo_l" / "det_10g.onnx"
    )


def test_acknowledge_usage_persists_insightface_root_not_models_child(tmp_path: Path):
    config = DummyConfigService()
    store = FaceModelStoreService(config, package_var=tmp_path, clock=_clock)

    ack = store.acknowledge_usage(model_pack="buffalo_l", accepted_by="tester", package_version="1.2.3")

    expected_root = (tmp_path / "insightface_models").resolve()
    expected_store = (expected_root / "models").resolve()
    ack_path = expected_store / "buffalo_l" / "LICENSE_ACK.json"
    assert ack_path.is_file()
    saved = json.loads(ack_path.read_text(encoding="utf-8"))
    assert saved["accepted_by"] == "tester"
    assert saved["accepted_at"] == "2026-07-07T20:00:00Z"
    assert saved["model_root"] == str(expected_root)
    assert saved["model_store"] == str(expected_store)
    assert ack["package_version"] == "1.2.3"
    face_config = config.config["native_processors"]["FACE_PROCESSOR"]
    assert face_config["INSIGHTFACE_LICENSE_ACKNOWLEDGED"] is True
    assert face_config["MODEL_NAME"] == "buffalo_l"
    assert face_config["MODEL_ROOT"] == str(expected_root)
    assert not face_config["MODEL_ROOT"].endswith("/models")


def test_acknowledge_usage_preserves_existing_configured_root(tmp_path: Path):
    configured_root = (tmp_path / "configured").resolve()
    config = DummyConfigService()
    config.config = {
        "native_processors": {
            "FACE_PROCESSOR": {
                "MODEL_ROOT": str(configured_root),
                "MODEL_NAME": "antelopev2",
            }
        }
    }
    store = FaceModelStoreService(config, package_var=tmp_path / "var", clock=_clock)

    store.acknowledge_usage(model_pack="antelopev2")

    face_config = config.config["native_processors"]["FACE_PROCESSOR"]
    assert face_config["MODEL_ROOT"] == str(configured_root)
    assert face_config["MODEL_NAME"] == "antelopev2"
    assert (configured_root / "models" / "antelopev2" / "LICENSE_ACK.json").is_file()


def test_import_model_files_copies_required_files_and_manifest(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "det_10g.onnx").write_bytes(b"detector")
    (source / "w600k_r50.onnx").write_bytes(b"recognizer")
    store = FaceModelStoreService(package_var=tmp_path / "var", clock=_clock)

    result = store.import_model_files(source, model_pack="buffalo_l", source="manual-test")

    model_root = (tmp_path / "var" / "insightface_models").resolve()
    model_store = model_root / "models"
    model_dir = model_store / "buffalo_l"
    assert (model_dir / "det_10g.onnx").read_bytes() == b"detector"
    assert (model_dir / "w600k_r50.onnx").read_bytes() == b"recognizer"
    assert (model_dir / "manifest.json").is_file()
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "manual-test"
    assert manifest["model_root"] == str(model_root)
    assert manifest["model_store"] == str(model_store)
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
