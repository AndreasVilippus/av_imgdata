import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
import imgdata as imgdata_module
from imgdata import ImgDataService
from services.config_service import ConfigService


class PipPackagesStatusTests(unittest.TestCase):
    def test_default_config_contains_disabled_insightface_optional_package(self):
        insightface = ConfigService.defaultConfig()["pip_packages"]["INSIGHTFACE"]

        self.assertFalse(insightface["ENABLED"])
        self.assertTrue(insightface["INSTALL_ON_START"])
        self.assertEqual(insightface["REQUIREMENTS_FILE"], "requirements-optional-insightface.txt")
        self.assertTrue(insightface["WHEELHOUSE_ENABLED"])
        self.assertEqual(
            insightface["WHEELHOUSE_MANIFEST_URL"],
            "https://github.com/AndreasVilippus/av_imgdata-wheelhouse/releases/download/dsm7-x86_64-python38-2026.04.23/wheelhouse-manifest.json",
        )
        self.assertEqual(insightface["WHEELHOUSE_TARGET"], "dsm7-x86_64-python38")

    def test_insightface_requirements_include_cv2_runtime_dependency(self):
        requirements = Path("src/requirements-optional-insightface.txt").read_text(encoding="utf-8")

        self.assertIn("opencv-python-headless==4.10.0.84", requirements)
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

            def fake_find_spec(module_name):
                return object() if module_name == "onnxruntime" else None

            def fake_import_module(module_name):
                if module_name == "onnxruntime":
                    return object()
                raise ImportError("not installed")

            def fake_version(package_name):
                if package_name == "onnxruntime":
                    return "1.16.3"
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
            self.assertEqual(status["modules"][0]["package"], "insightface")
            self.assertEqual(status["modules"][0]["module"], "insightface.app")
            self.assertFalse(status["modules"][0]["installed"])
            self.assertEqual(status["modules"][1]["package"], "onnxruntime")
            self.assertTrue(status["modules"][1]["installed"])
            self.assertEqual(status["modules"][1]["version"], "1.16.3")
            self.assertEqual(status["modules"][2]["package"], "opencv-python-headless")
            self.assertFalse(status["modules"][2]["installed"])
            self.assertEqual(status["conflicts"], [])

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


if __name__ == "__main__":
    unittest.main()
