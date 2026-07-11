from pathlib import Path

from services.worker_provisioning_service import UiConfiguredFaceModelStoreService


class DummyConfigService:
    def __init__(self, model_root: str = ""):
        self.model_root = model_root

    def readMergedConfig(self):
        return {
            "native_processors": {
                "FACE_PROCESSOR": {
                    "MODEL_ROOT": self.model_root,
                    "MODEL_NAME": "buffalo_l",
                }
            }
        }

    def readConfig(self):
        return self.readMergedConfig()


def test_worker_distribution_uses_package_var_default_insightface_store(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOME", raising=False)
    package_var = tmp_path / "var"
    store = UiConfiguredFaceModelStoreService(DummyConfigService(), package_var=package_var)

    assert store.model_root() == (package_var / ".insightface" / "models").resolve()
    assert store.model_dir("buffalo_l") == (package_var / ".insightface" / "models" / "buffalo_l").resolve()


def test_worker_distribution_uses_ui_configured_insightface_store(tmp_path: Path):
    configured_root = tmp_path / "configured-insightface-root"
    store = UiConfiguredFaceModelStoreService(
        DummyConfigService(str(configured_root)),
        package_var=tmp_path / "var",
    )

    assert store.model_root() == (configured_root / "models").resolve()
    assert store.model_dir("buffalo_l") == (configured_root / "models" / "buffalo_l").resolve()
