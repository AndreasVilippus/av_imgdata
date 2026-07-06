import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath("src"))

from services.exiftool_service import ExifToolService
from services.config_service import ConfigService


class ExifToolServiceTests(unittest.TestCase):
    def test_configured_path_from_files_config_prefers_manual_path(self):
        configured = ExifToolService._configuredPathFromFilesConfig({
            "PATHEXIFTOOL": "/var/packages/AV_ImgData/target/usr/bin/exiftool",
            "USE_MANUAL_PATHEXIFTOOL": True,
            "MANUAL_PATHEXIFTOOL": "/usr/local/bin/exiftool",
        })

        self.assertEqual(configured, "/usr/local/bin/exiftool")

    def test_install_package_target_executable_copies_binary_and_lib_into_pkgdest_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dest = Path(tmpdir) / "target"
            source_executable = Path(tmpdir) / "Image-ExifTool-13.53" / "exiftool"
            source_lib = source_executable.parent / "lib" / "Image"
            source_executable.parent.mkdir(parents=True, exist_ok=True)
            source_lib.mkdir(parents=True, exist_ok=True)
            source_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (source_lib / "ExifTool.pm").write_text("package Image::ExifTool;\n1;\n", encoding="utf-8")
            source_executable.chmod(0o755)

            with patch.dict(os.environ, {"SYNOPKG_PKGDEST": str(package_dest)}, clear=False):
                ExifToolService._installPackageTargetExecutable(source_executable, source_executable.parent / "lib")
                target_path = ExifToolService._packageTargetExecutablePath()
                target_lib_path = ExifToolService._packageTargetLibPath()

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_text(encoding="utf-8"), source_executable.read_text(encoding="utf-8"))
            self.assertTrue(target_path.stat().st_mode & stat.S_IXUSR)
            self.assertTrue((target_lib_path / "Image" / "ExifTool.pm").exists())

    def test_install_package_target_executable_replaces_existing_target_executable_and_lib(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dest = Path(tmpdir) / "target"
            source_executable = Path(tmpdir) / "Image-ExifTool-13.55" / "exiftool"
            source_lib = source_executable.parent / "lib" / "Image"
            source_executable.parent.mkdir(parents=True, exist_ok=True)
            source_lib.mkdir(parents=True, exist_ok=True)
            source_executable.write_text("#!/bin/sh\necho new\n", encoding="utf-8")
            (source_lib / "ExifTool.pm").write_text("package Image::ExifTool;\nour $VERSION = '13.55';\n1;\n", encoding="utf-8")
            source_executable.chmod(0o755)

            with patch.dict(os.environ, {"SYNOPKG_PKGDEST": str(package_dest)}, clear=False):
                target_path = ExifToolService._packageTargetExecutablePath()
                target_lib_path = ExifToolService._packageTargetLibPath()
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_lib_path.mkdir(parents=True, exist_ok=True)
                target_path.write_text("old", encoding="utf-8")
                (target_lib_path / "stale.txt").write_text("stale", encoding="utf-8")

                ExifToolService._installPackageTargetExecutable(source_executable, source_executable.parent / "lib")

            self.assertEqual(target_path.read_text(encoding="utf-8"), source_executable.read_text(encoding="utf-8"))
            self.assertFalse((target_lib_path / "stale.txt").exists())
            self.assertTrue((target_lib_path / "Image" / "ExifTool.pm").exists())

    def test_remove_installed_keeps_manual_path_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            package_var = Path(tmpdir) / "var"
            package_dest = Path(tmpdir) / "target"
            install_root = package_var / "exiftool"
            install_root.mkdir(parents=True, exist_ok=True)
            (install_root / "dummy.txt").write_text("x", encoding="utf-8")
            target_bin = package_dest / "usr/bin"
            target_bin.mkdir(parents=True, exist_ok=True)
            (target_bin / "exiftool").write_text("x", encoding="utf-8")
            target_lib = target_bin / "lib"
            target_lib.mkdir(parents=True, exist_ok=True)
            (target_lib / "Image.pm").write_text("x", encoding="utf-8")

            config_service = ConfigService(str(config_path))
            config_service.writeConfig({
                "files": {
                    "USE_EXIFTOOL": True,
                    "PATHEXIFTOOL": "/var/packages/AV_ImgData/target/usr/bin/exiftool",
                    "USE_MANUAL_PATHEXIFTOOL": True,
                    "MANUAL_PATHEXIFTOOL": "/usr/local/bin/exiftool",
                }
            })

            service = ExifToolService(config_service)
            with patch.dict(os.environ, {"SYNOPKG_PKGVAR": str(package_var), "SYNOPKG_PKGDEST": str(package_dest)}, clear=False):
                result = service.removeInstalled()

            self.assertTrue(result["success"])
            updated = config_service.readMergedConfig()["files"]
            self.assertTrue(updated["USE_EXIFTOOL"])
            self.assertTrue(updated["USE_MANUAL_PATHEXIFTOOL"])
            self.assertEqual(updated["MANUAL_PATHEXIFTOOL"], "/usr/local/bin/exiftool")
            self.assertEqual(updated["PATHEXIFTOOL"], "/var/packages/AV_ImgData/target/usr/bin/exiftool")

    def test_status_background_returns_pending_without_sync_probe_or_online_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            config_service.writeConfig({
                "files": {
                    "USE_EXIFTOOL": True,
                    "CHECK_EXIFTOOL_UPDATES": True,
                    "PATHEXIFTOOL": "exiftool",
                }
            })
            service = ExifToolService(config_service)
            service.refreshStatusBackground = Mock(return_value=True)

            with patch.object(service, "_detectLocalExifTool", side_effect=AssertionError("local probe must be backgrounded")), \
                    patch.object(service, "_fetchLatestOfficialInfo", side_effect=AssertionError("online check must be backgrounded")), \
                    patch.object(service, "_detectPerl", side_effect=AssertionError("perl probe must be backgrounded")):
                status = service.getStatus(background=True)

            self.assertTrue(status["cache_stale"])
            self.assertTrue(status["refreshing"])
            self.assertEqual(status["configured_path"], "exiftool")
            service.refreshStatusBackground.assert_called_once()

    def test_status_background_uses_cached_status_without_new_probe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_service = ConfigService(str(Path(tmpdir) / "config.json"))
            config_service.writeConfig({
                "files": {
                    "USE_EXIFTOOL": True,
                    "CHECK_EXIFTOOL_UPDATES": False,
                    "PATHEXIFTOOL": "exiftool",
                }
            })
            service = ExifToolService(config_service)

            with patch.object(service, "_detectLocalExifTool", return_value={
                "found": True,
                "configured_path": "exiftool",
                "resolved_path": "/usr/bin/exiftool",
                "found_via": "path_lookup",
                "version": "13.00",
                "kind": "perl_script",
            }), patch.object(service, "_detectPerl", return_value={
                "available": True,
                "path": "/usr/bin/perl",
                "version": "5.36",
            }):
                first = service.getStatus(force=True)

            with patch.object(service, "_detectLocalExifTool", side_effect=AssertionError("cache should avoid local probe")):
                second = service.getStatus(background=True)

            self.assertEqual(first["local"]["version"], "13.00")
            self.assertEqual(second["local"]["version"], "13.00")
            self.assertTrue(second["cache_hit"])


if __name__ == "__main__":
    unittest.main()
