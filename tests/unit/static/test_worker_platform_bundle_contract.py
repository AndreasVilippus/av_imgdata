#!/usr/bin/env python3

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_worker_cmake_builds_same_runtime_roles_for_both_platform_targets():
    cmake = (PROJECT_ROOT / "worker" / "CMakeLists.txt").read_text(encoding="utf-8")

    for target in (
        "av-imgdata-worker",
        "av-imgdata-worker-api-loop",
        "av-imgdata-worker-configure",
        "av-imgdata-worker-model-sync",
    ):
        assert f"add_executable({target}" in cmake
        assert target in cmake.split("set(AV_IMGDATA_WORKER_TARGETS", 1)[1]
    assert "protocol/worker-protocol.json" in cmake
    assert "config/worker-config.schema.json" in cmake
    assert "packaging/windows/Initialize-AVImgDataWorker.ps1" in cmake
    assert "packaging/unix/initialize-av-imgdata-worker.sh" in cmake


def test_windows_initializer_delegates_config_and_model_sync():
    script = (PROJECT_ROOT / "worker" / "packaging" / "windows" / "Initialize-AVImgDataWorker.ps1").read_text(encoding="utf-8")

    assert "av-imgdata-worker-configure.exe" in script
    assert "av-imgdata-worker-model-sync.exe" in script
    assert "Get-FileHash" not in script
    assert "Invoke-WebRequest" not in script
    assert "$config.processors.face" not in script
    assert "manifest.files" not in script


def test_unix_initializer_delegates_config_and_model_sync():
    script = (PROJECT_ROOT / "worker" / "packaging" / "unix" / "initialize-av-imgdata-worker.sh").read_text(encoding="utf-8")

    assert "av-imgdata-worker-configure" in script
    assert "av-imgdata-worker-model-sync" in script
    assert "sha256sum" not in script
    assert "manifest.json" not in script
    assert "chmod 600" in script


def test_worker_example_config_matches_schema_contract():
    config = json.loads((PROJECT_ROOT / "worker" / "config" / "worker-config.example.json").read_text(encoding="utf-8"))
    schema = json.loads((PROJECT_ROOT / "worker" / "config" / "worker-config.schema.json").read_text(encoding="utf-8"))

    assert config["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert set(schema["required"]).issubset(config)
    assert config["input_modes"] == ["shared_path"]
    assert config["processors"]["face"]["model_root"] == "../.models/face"
    assert "dsm_base_url" not in config


def test_config_writer_owns_platform_specific_executable_names():
    source = (PROJECT_ROOT / "worker" / "src" / "configure.cpp").read_text(encoding="utf-8")

    assert "av-imgdata-face-processor.exe" in source
    assert "av-imgdata-face-processor\"" in source
    assert "kConfigSchemaVersion" in source
    assert "input_modes_json()" in source


def test_model_sync_owns_manifest_hash_and_atomic_install_logic():
    source = (PROJECT_ROOT / "worker" / "src" / "model_sync.cpp").read_text(encoding="utf-8")

    assert '"sha256"' in source
    assert "file_sha256" in source
    assert "manifest.json.download" in source
    assert "std::filesystem::rename" in source
    assert "X-Worker-Id" in source
