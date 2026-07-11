from pathlib import Path

from services.face_model_path_service import FaceModelPathService
from services.worker_provisioning_service import ResolvedFaceModelStoreService


class DummyConfigService:
    def __init__(self, model_root: str = "", model_name: str = "buffalo_l"):
        self.model_root = model_root
        self.model_name = model_name

    def readMergedConfig(self):
        return {
            "native_processors": {
                "FACE_PROCESSOR": {
                    "MODEL_ROOT": self.model_root,
                    "MODEL_NAME": self.model_name,
                }
            }
        }

    def readConfig(self):
        return self.readMergedConfig()


def test_shared_resolver_uses_package_runtime_model_root(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOME", raising=False)
    package_var = tmp_path / "var"
    paths = FaceModelPathService(DummyConfigService(), package_var=package_var)

    assert paths.model_root() == (package_var / "insightface_models").resolve()
    assert paths.model_store() == (package_var / "insightface_models" / "models").resolve()
    assert paths.model_dir() == (package_var / "insightface_models" / "models" / "buffalo_l").resolve()


def test_worker_store_delegates_to_shared_resolver(tmp_path: Path):
    package_var = tmp_path / "var"
    store = ResolvedFaceModelStoreService(DummyConfigService(), package_var=package_var)

    assert store.model_root() == (package_var / "insightface_models" / "models").resolve()
    assert store.model_dir("buffalo_l") == (
        package_var / "insightface_models" / "models" / "buffalo_l"
    ).resolve()


def test_shared_resolver_uses_configured_insightface_root_and_name(tmp_path: Path):
    configured_root = tmp_path / "configured-insightface-root"
    paths = FaceModelPathService(
        DummyConfigService(str(configured_root), "antelopev2"),
        package_var=tmp_path / "var",
    )

    assert paths.model_root() == configured_root.resolve()
    assert paths.model_store() == (configured_root / "models").resolve()
    assert paths.model_name() == "antelopev2"
    assert paths.model_dir() == (configured_root / "models" / "antelopev2").resolve()
