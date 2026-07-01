import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
import imgdata as imgdata_module
from imgdata import ImgDataService
from services.config_service import ConfigService


class PipPackagesStatusTests(unittest.TestCase):
    @staticmethod
    def _urlopen_factory(manifest, wheel_payloads):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.payload

        def fake_urlopen(url, timeout=0):
            if str(url).endswith("wheelhouse-manifest.json"):
                return FakeResponse(json.dumps(manifest).encode("utf-8"))
            filename = str(url).rsplit("/", 1)[-1]
            return FakeResponse(wheel_payloads[filename])

        return fake_urlopen

    def test_default_config_contains_disabled_insightface_optional_package(self):
        insightface = ConfigService.defaultConfig()["pip_packages"]["INSIGHTFACE"]

        self.assertFalse(insightface["ENABLED"])
        self.assertFalse(insightface["INSTALL_ON_START"])
        self.assertEqual(insightface["REQUIREMENTS_FILE"], "requirements-optional-insightface.txt")
        self.assertTrue(insightface["WHEELHOUSE_ENABLED"])
        self.assertEqual(
            insightface["WHEELHOUSE_MANIFEST_URL"],
            "https://github.com/AndreasVilippus/av_imgdata-wheelhouse/releases/download/dsm7-x86_64-python38-2026.06.22/wheelhouse-manifest.json",
        )
        self.assertEqual(insightface["WHEELHOUSE_TARGET"], "dsm7-x86_64-python38")

    def test_insightface_requirements_include_cv2_runtime_dependency(self):
        requirements = Path("src/requirements-optional-insightface.txt").read_text(encoding="utf-8")

        self.assertIn("opencv-python-headless==4.10.0.84", requirements)
        self.assertIn("Pillow==10.4.0", requirements)
        self.assertIn("pillow-heif==0.18.0", requirements)
        self.assertIn("onnxruntime==1.16.3", requirements)
        self.assertIn("urllib3<2", requirements)

    def test_pip_packages_status_reports_config_modules_and_last_install_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            status_path = Path(tmpdir) / "pip_packages_status.json"
            config_service = ConfigService(str(config_path))
            config_service.writeConfig({
                "pip_packages": {
                    "INSIGHTFACE": {
                        "ENABLED": True,
                        "INSTALL_ON_START": True,
                        "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                        "WHEELHOUSE_ENABLED": True,
                        "WHEELHOUSE_MANIFEST_URL": "https://example.invalid/releases/download/dsm7-x86_64-python38/wheelhouse-manifest.json",
                        "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                    },
                },
            })
            status_path.write_text(
                '{"packages":{"INSIGHTFACE":{"status":"failed","success":false,"message":"No matching distribution found"}}}',
                encoding="utf-8",
            )
            service = ImgDataService(SessionManager())
            service.config = config_service
            service.face_recognition.profiles = lambda: {"profiles": [{"person_id": 1}, {"person_id": 2}]}

            def fake_find_spec(module_name):
                return object() if module_name in {"onnxruntime", "PIL.Image"} else None

            def fake_import_module(module_name):
                if module_name in {"onnxruntime", "PIL.Image"}:
                    return object()
                raise ImportError("not installed")

            def fake_version(package_name):
                if package_name == "onnxruntime":
                    return "1.16.3"
                if package_name == "Pillow":
                    return "10.4.0"
                raise Exception("not installed")

            with patch.object(imgdata_module.importlib.util, "find_spec", side_effect=fake_find_spec), patch.object(imgdata_module.importlib, "import_module", side_effect=fake_import_module), patch.object(imgdata_module.importlib_metadata, "version", side_effect=fake_version):
                status = service.pipPackagesStatus()["packages"]["INSIGHTFACE"]

            self.assertTrue(status["enabled"])
            self.assertTrue(status["install_on_start"])
            self.assertTrue(status["wheelhouse_enabled"])
            self.assertEqual(status["wheelhouse_manifest_url"], "https://example.invalid/releases/download/dsm7-x86_64-python38/wheelhouse-manifest.json")
            self.assertEqual(status["wheelhouse_target"], "dsm7-x86_64-python38")
            self.assertFalse(status["installed"])
            self.assertEqual(status["install_status"]["status"], "failed")
            self.assertIn("model_status", status)
            self.assertEqual(status["modules"][0]["package"], "insightface")
            self.assertEqual(status["modules"][0]["module"], "insightface.app")
            self.assertFalse(status["modules"][0]["installed"])
            self.assertEqual(status["modules"][1]["package"], "onnxruntime")
            self.assertTrue(status["modules"][1]["installed"])
            self.assertEqual(status["modules"][1]["version"], "1.16.3")
            self.assertEqual(status["modules"][2]["package"], "opencv-python-headless")
            self.assertFalse(status["modules"][2]["installed"])
            self.assertEqual(status["modules"][3]["package"], "Pillow")
            self.assertTrue(status["modules"][3]["installed"])
            self.assertEqual(status["modules"][3]["version"], "10.4.0")
            self.assertEqual(status["modules"][4]["package"], "pillow-heif")
            self.assertFalse(status["modules"][4]["installed"])
            self.assertEqual(status["conflicts"], [])
            self.assertEqual(status["status_blocks"], [{
                "key": "generated_face_profiles",
                "label_key": "status:pip_generated_face_profiles",
                "fallback_label": "Generated person profiles",
                "value": 2,
            }])

    def test_pip_packages_status_requires_successful_module_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            service = ImgDataService(SessionManager())
            service.config = config_service

            def fake_find_spec(module_name):
                return object()

            def fake_import_module(module_name):
                if module_name == "cv2":
                    raise ImportError("libfoo.so missing")
                return object()

            def fake_version(package_name):
                return {
                    "insightface": "0.2.1",
                    "onnxruntime": "1.16.3",
                    "opencv-python-headless": "4.10.0.84",
                    "Pillow": "10.4.0",
                    "pillow-heif": "0.18.0",
                    "opencv-python": "4.13.0.92",
                }[package_name]

            with patch.object(imgdata_module.importlib.util, "find_spec", side_effect=fake_find_spec), patch.object(imgdata_module.importlib, "import_module", side_effect=fake_import_module), patch.object(imgdata_module.importlib_metadata, "version", side_effect=fake_version):
                status = service.pipPackagesStatus()["packages"]["INSIGHTFACE"]

            self.assertFalse(status["installed"])
            cv2_status = status["modules"][2]
            self.assertEqual(cv2_status["module"], "cv2")
            self.assertFalse(cv2_status["installed"])
            self.assertEqual(cv2_status["version"], "4.10.0.84")
            self.assertIn("libfoo.so missing", cv2_status["import_error"])
            self.assertEqual(status["conflicts"], [{"package": "opencv-python", "version": "4.13.0.92"}])

    def test_pip_packages_status_handles_nested_module_lookup_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            service = ImgDataService(SessionManager())
            service.config = config_service

            def fake_find_spec(module_name):
                if module_name == "insightface.app":
                    raise ModuleNotFoundError("No module named 'insightface'")
                return object()

            def fake_import_module(module_name):
                return object()

            def fake_version(package_name):
                return "1.0.0"

            with patch.object(imgdata_module.importlib.util, "find_spec", side_effect=fake_find_spec), patch.object(imgdata_module.importlib, "import_module", side_effect=fake_import_module), patch.object(imgdata_module.importlib_metadata, "version", side_effect=fake_version):
                status = service.pipPackagesStatus()["packages"]["INSIGHTFACE"]

            self.assertFalse(status["installed"])
            self.assertEqual(status["modules"][0]["module"], "insightface.app")
            self.assertFalse(status["modules"][0]["installed"])
            self.assertEqual(status["modules"][0]["version"], "1.0.0")
            self.assertIn("No module named 'insightface'", status["modules"][0]["import_error"])

    def test_pip_wheelhouse_packages_lists_manifest_packages_with_installed_versions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            config_service.writeConfig({
                "pip_packages": {
                    "INSIGHTFACE": {
                        "WHEELHOUSE_MANIFEST_URL": "https://example.invalid/wheelhouse-manifest.json",
                        "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                        "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                    },
                },
            })
            service = ImgDataService(SessionManager())
            service.config = config_service
            manifest = {
                "target": "dsm7-x86_64-python38",
                "requirements_file": "requirements-runtime-insightface.txt",
                "packages": [
                    {"name": "onnxruntime", "file": "onnxruntime.whl", "sha256": "a", "size": 10},
                    {"name": "insightface", "file": "insightface.whl", "sha256": "b", "size": 20},
                ],
            }

            def fake_version(package_name):
                if package_name == "insightface":
                    return "0.7.3"
                raise Exception("not installed")

            with patch.object(imgdata_module.urllib.request, "urlopen", side_effect=self._urlopen_factory(manifest, {})), patch.object(imgdata_module.importlib_metadata, "version", side_effect=fake_version):
                result = service.pipWheelhousePackages()

            self.assertEqual([item["name"] for item in result["packages"]], ["insightface", "onnxruntime"])
            self.assertTrue(result["packages"][0]["installed"])
            self.assertEqual(result["packages"][0]["installed_version"], "0.7.3")
            self.assertFalse(result["packages"][1]["installed"])

    def test_pip_wheelhouse_reinstall_downloads_fresh_assets_and_force_reinstalls_selected_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            config_service.writeConfig({
                "pip_packages": {
                    "INSIGHTFACE": {
                        "WHEELHOUSE_MANIFEST_URL": "https://example.invalid/wheelhouse-manifest.json",
                        "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                        "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                    },
                },
            })
            service = ImgDataService(SessionManager())
            service.config = config_service
            wheel_payloads = {
                "insightface.whl": b"fresh insightface wheel",
                "onnxruntime.whl": b"fresh onnxruntime wheel",
            }
            manifest = {
                "target": "dsm7-x86_64-python38",
                "requirements_file": "requirements-runtime-insightface.txt",
                "packages": [
                    {
                        "name": "insightface",
                        "file": "insightface.whl",
                        "sha256": hashlib.sha256(wheel_payloads["insightface.whl"]).hexdigest(),
                        "size": len(wheel_payloads["insightface.whl"]),
                    },
                    {
                        "name": "onnxruntime",
                        "file": "onnxruntime.whl",
                        "sha256": hashlib.sha256(wheel_payloads["onnxruntime.whl"]).hexdigest(),
                        "size": len(wheel_payloads["onnxruntime.whl"]),
                    },
                ],
            }
            pip_calls = []
            download_calls = []

            def fake_run(command, **kwargs):
                pip_calls.append((command, kwargs))
                return SimpleNamespace(returncode=0, stdout="installed")

            fake_urlopen = self._urlopen_factory(manifest, wheel_payloads)

            def tracking_urlopen(url, timeout=0):
                download_calls.append(str(url))
                return fake_urlopen(url, timeout=timeout)

            with patch.object(imgdata_module.urllib.request, "urlopen", side_effect=tracking_urlopen), patch.object(imgdata_module.subprocess, "run", side_effect=fake_run):
                result = service.installPipWheelhousePackage(package_name="insightface", reinstall=True)

            self.assertTrue(result["success"])
            self.assertEqual(result["package_name"], "insightface")
            self.assertEqual(download_calls, [
                "https://example.invalid/wheelhouse-manifest.json",
                "https://example.invalid/insightface.whl",
                "https://example.invalid/onnxruntime.whl",
            ])
            command = pip_calls[0][0]
            self.assertIn("--force-reinstall", command)
            self.assertIn("--no-index", command)
            self.assertIn("--find-links", command)
            self.assertEqual(command[-1], "insightface")
            status = json.loads((Path(tmpdir) / "pip_packages_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["packages"]["INSIGHTFACE"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
