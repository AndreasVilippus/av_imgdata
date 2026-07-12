#!/usr/bin/env python3

import json
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
def test_unix_worker_runtime_roles_compile_and_run_shared_tests(tmp_path):
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
            "-DAV_IMGDATA_WORKER_BUILD_TESTS=ON",
            f"-DCMAKE_INSTALL_PREFIX={install_dir}",
        ],
        check=True,
    )
    subprocess.run(["cmake", "--build", str(build_dir), "--parallel", "2"], check=True)
    subprocess.run(["ctest", "--test-dir", str(build_dir), "--output-on-failure"], check=True)
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

    generated_config = tmp_path / "configured" / "worker.json"
    subprocess.run(
        [
            str(install_dir / "bin" / "av-imgdata-worker-configure"),
            "--config",
            str(generated_config),
            "--worker-id",
            "unix-worker-01",
            "--api-url",
            "https://nas.example/worker-api/",
            "--path-base-dir",
            "/mnt/photo",
        ],
        check=True,
    )
    config = json.loads(generated_config.read_text(encoding="utf-8"))
    assert config["schema_version"] == 1
    assert config["worker_id"] == "unix-worker-01"
    assert config["worker_api_base_url"] == "https://nas.example/worker-api"
    assert config["path_base_dir"] == "/mnt/photo"
    assert config["processors"]["face"]["path"] == "../bin/av-imgdata-face-processor"
