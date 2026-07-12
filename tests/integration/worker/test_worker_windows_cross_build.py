#!/usr/bin/env python3

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
def test_windows_worker_runtime_roles_cross_compile_from_same_sources(tmp_path):
    if shutil.which("cmake") is None or shutil.which("x86_64-w64-mingw32-g++") is None:
        pytest.skip("CMake and MinGW x86_64 are required")

    build_dir = tmp_path / "worker-windows-build"
    install_dir = tmp_path / "worker-windows-install"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(PROJECT_ROOT / "worker"),
            "-B",
            str(build_dir),
            f"-DCMAKE_TOOLCHAIN_FILE={PROJECT_ROOT / 'worker' / 'cmake' / 'toolchains' / 'windows-mingw-x86_64.cmake'}",
            f"-DCMAKE_INSTALL_PREFIX={install_dir}",
        ],
        check=True,
    )
    subprocess.run(["cmake", "--build", str(build_dir), "--parallel", "2"], check=True)
    subprocess.run(["cmake", "--install", str(build_dir)], check=True)

    for binary in (
        "av-imgdata-worker.exe",
        "av-imgdata-worker-api-loop.exe",
        "av-imgdata-worker-configure.exe",
        "av-imgdata-worker-model-sync.exe",
    ):
        assert (install_dir / "bin" / binary).is_file()
    assert (install_dir / "Initialize-AVImgDataWorker.ps1").is_file()
    assert (install_dir / "config" / "worker-config.schema.json").is_file()
