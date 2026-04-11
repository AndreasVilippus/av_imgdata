import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from services.exiftool_service import ExifToolService


class ExifToolServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
