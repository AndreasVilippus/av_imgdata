#!/usr/bin/env python3

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
def test_unix_worker_runtime_roles_compile_from_one_cmake_project(tmp_path):
    if shutil.which("cmake") is None or shutil.which("c++") is None:
        pytest.skip("CMake and a C++ compiler are required")

    build_dir = tmp_path / "worker-build"
    install_dir = tmp_path / "worker-install"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(PROJECT_ROOT / "worker"),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={install_dir}",
        ],
        check=True,
    )
    subprocess.run(["cmake", "--build", str(build_dir), "--parallel", "2"], check=True)
    subprocess.run(["cmake", "--install", str(build_dir)], check=True)

    for binary in (
        "av-imgdata-worker",
        "av-imgdata-worker-api-loop",
        "av-imgdata-worker-configure",
        "av-imgdata-worker-model-sync",
    ):
        assert (install_dir / "bin" / binary).is_file()
    assert (install_dir / "config" / "worker-config.schema.json").is_file()
    assert (install_dir / "share" / "worker_protocol" / "worker-protocol.json").is_file()
    assert (install_dir / "initialize-av-imgdata-worker.sh").is_file()
