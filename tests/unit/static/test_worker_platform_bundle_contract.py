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


def test_all_worker_binary_roles_use_shared_protocol_and_runtime():
    for filename in ("main.cpp", "api_loop.cpp", "configure.cpp", "model_sync.cpp"):
        source = (PROJECT_ROOT / "worker" / "src" / filename).read_text(encoding="utf-8")
        assert '#include "av_imgdata/worker_protocol.h"' in source
        assert '#include "av_imgdata/worker_runtime.h"' in source
        assert "0.1.0-phase-d" not in source
        assert "0.1.0-phase-h1" not in source

    main_source = (PROJECT_ROOT / "worker" / "src" / "main.cpp").read_text(encoding="utf-8")
    api_source = (PROJECT_ROOT / "worker" / "src" / "api_loop.cpp").read_text(encoding="utf-8")
    for duplicated_definition in (
        "std::string shell_quote(",
        "std::string json_escape(",
        "std::string arg_value(",
        "CommandResult run_command(",
    ):
        assert duplicated_definition not in main_source
        assert duplicated_definition not in api_source


def test_windows_initializer_delegates_config_and_model_sync_from_both_locations():
    script = (PROJECT_ROOT / "worker" / "packaging" / "windows" / "Initialize-AVImgDataWorker.ps1").read_text(encoding="utf-8")

    assert "av-imgdata-worker-configure.exe" in script
    assert "av-imgdata-worker-model-sync.exe" in script
    assert 'Join-Path $RootCandidate "bin"' in script
    assert 'Join-Path $PSScriptRoot "..\\.."' in script
    assert "Get-FileHash" not in script
    assert "Invoke-WebRequest" not in script
    assert "$config.processors.face" not in script
    assert "manifest.files" not in script


def test_unix_initializer_delegates_config_and_model_sync_from_both_locations():
    script = (PROJECT_ROOT / "worker" / "packaging" / "unix" / "initialize-av-imgdata-worker.sh").read_text(encoding="utf-8")

    assert "av-imgdata-worker-configure" in script
    assert "av-imgdata-worker-model-sync" in script
    assert 'if [ -d "$SCRIPT_DIR/bin" ]' in script
    assert '"$SCRIPT_DIR/../.."' in script
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
    assert config["processors"]["image_vips"]["enabled"] is True
    assert config["processors"]["image_vips"]["path"] == "../bin/av-imgdata-image-processor"
    assert "dsm_base_url" not in config


def test_config_writer_owns_platform_specific_executable_names():
    source = (PROJECT_ROOT / "worker" / "src" / "configure.cpp").read_text(encoding="utf-8")

    assert "av-imgdata-face-processor.exe" in source
    assert "av-imgdata-face-processor\"" in source
    assert '\\"image_vips\\": {\\"enabled\\": true' in source
    assert "kConfigSchemaVersion" in source
    assert "input_modes_json()" in source


def test_worker_bundle_builds_and_integrates_vips_image_processor_by_default_with_opt_out():
    cmake = (PROJECT_ROOT / "worker" / "CMakeLists.txt").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "tools" / "build-worker.sh").read_text(encoding="utf-8")
    windows_script = (PROJECT_ROOT / "tools" / "build-native-image-processor-vips-windows.sh").read_text(encoding="utf-8")
    linux_chroot_script = (PROJECT_ROOT / "tools" / "build-native-image-processor-vips-linux-chroot.sh").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "worker" / "README.md").read_text(encoding="utf-8")

    assert 'AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR "Bundle av-imgdata-image-processor with the worker artifact" ON' in cmake
    assert 'AV_IMGDATA_BUNDLE_WORKER_VIPS="${AV_IMGDATA_BUNDLE_WORKER_VIPS:-${AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR:-1}}"' in script
    assert 'AV_IMGDATA_BUILD_WORKER_VIPS="${AV_IMGDATA_BUILD_WORKER_VIPS:-1}"' in script
    assert 'AV_IMGDATA_REQUIRE_WORKER_VIPS="${AV_IMGDATA_REQUIRE_WORKER_VIPS:-1}"' in script
    assert "bundle_vips_processor" in script
    assert "require_worker_vips_build_tools" in script
    assert 'AV_IMGDATA_LINUX_CHROOT="${AV_IMGDATA_LINUX_CHROOT:-1}"' in script
    assert "build-native-image-processor-vips-linux-chroot.sh" in script
    assert "AV_IMGDATA_LINUX_CHROOT=0" in readme
    assert "build/chroot/linux-x86_64" in linux_chroot_script
    assert "debootstrap" in linux_chroot_script
    assert "chroot --userspec" in linux_chroot_script
    assert "mount --bind" in linux_chroot_script
    assert "meson" in readme
    assert "pkg-config" in readme
    assert "build-native-image-processor-vips.sh" in script
    assert "build-native-image-processor-vips-windows.sh" in script
    vips_bundle_block = script.split("bundle_vips_processor()", 1)[1].split("write_worker_model_readme()", 1)[0]
    assert vips_bundle_block.index('if [ "${copied}" = "0" ] && [ "${AV_IMGDATA_BUILD_WORKER_VIPS}" != "0" ]; then') < vips_bundle_block.index("local binary_candidates=(")
    assert "Skipping libvips image processor integration because AV_IMGDATA_BUNDLE_WORKER_VIPS=0." in script
    assert "Skipping libvips image processor rebuild because AV_IMGDATA_BUILD_WORKER_VIPS=0." in script
    assert "worker probe will report image_vips_binary_exists=false" in script
    assert "required libvips image processor binary not found" in script
    assert "worker build directory is not writable" in script
    assert "worker dist directory is not writable" in script
    assert "generated worker path cannot be removed" in script
    assert "build-win64-mxe" in windows_script
    assert "AV_IMGDATA_WINDOWS_VIPS_REPO_TAG" in windows_script
    assert "Keeping bundled runtime DLL already provided by dependency root" in windows_script
    assert "Keeping bundled runtime DLL already provided by processor bundle" in script
    assert 'MXE_TMPDIR="${AV_IMGDATA_WINDOWS_VIPS_TMPDIR:-${BUILD_ROOT}/mxe-tmp}"' in windows_script
    assert 'MXE_PODMAN_RUNTIME_DIR="${AV_IMGDATA_WINDOWS_VIPS_PODMAN_RUNTIME_DIR:-}"' in windows_script
    assert 'MXE_PODMAN_HOME="${AV_IMGDATA_WINDOWS_VIPS_PODMAN_HOME:-}"' in windows_script
    assert 'MXE_CONTAINER_USER_ARGS="${AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS:--u $(id -u):$(id -g)}"' in windows_script
    assert 'MXE_BUILD_ARGS="${AV_IMGDATA_WINDOWS_VIPS_BUILD_ARGS:---tmpdir ${MXE_TMPDIR} avimgdata --with-jpeg-turbo --without-llvm}"' in windows_script
    assert 'export HOME="${MXE_PODMAN_HOME}"' in windows_script
    assert 'export XDG_DATA_HOME="${MXE_PODMAN_HOME}/.local/share"' in windows_script
    assert 'export XDG_RUNTIME_DIR="${MXE_PODMAN_RUNTIME_DIR}"' in windows_script
    assert "write_avimgdata_mxe_profile" in windows_script
    assert "patch_build_win64_mxe_runner" in windows_script
    assert 'AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS' in windows_script
    assert "vips-avimgdata" in windows_script
    assert "glib expat libjpeg-turbo" in windows_script
    assert '"expat": "$(expat_VERSION)"' in windows_script
    assert "libheif libde265" in windows_script
    assert "-DWITH_LIBDE265=1" in windows_script
    assert "-DWITH_X265=0" in windows_script
    assert "x265" not in windows_script.split("cat >\"${profile}\"", 1)[1].split("PROFILE_EOF", 1)[0]
    assert "worker/native_deps/windows-x86_64/vips" in windows_script
    assert "ensure_vips_root" in windows_script
    assert "find_built_vips_zip" in windows_script
    assert "extract_built_vips_zip" in windows_script
    assert "normalize_vips_pkgconfig_prefix" in windows_script
    assert 'sed -i "s|^prefix=.*|prefix=${VIPS_ROOT}|" "${pc_file}"' in windows_script
    assert 'ensure_vips_root\nselect_pkg_config\nrm -rf "${BUILD_DIR}"' in windows_script
    assert "vips-dev-w64-*.zip" in windows_script
    assert '"${MXE_BUILD_ROOT}"/build/vips-dev-*' in windows_script
    assert '"${MXE_BUILD_ROOT}"/build/mxe/usr/x86_64-w64-mingw32.shared.win32.avimgdata' in windows_script
    assert "build-win64-mxe packaging failed, but a usable Windows libvips root was produced; continuing." in windows_script
    assert "lib/pkgconfig/vips.pc" in windows_script
    assert "av-imgdata-image-processor.exe" in windows_script


def test_worker_probe_reports_vips_without_requiring_it_for_readiness():
    source = (PROJECT_ROOT / "worker" / "src" / "main.cpp").read_text(encoding="utf-8")

    assert "image_vips_binary_exists" in source
    assert "image_vips_probe_ok" in source
    assert "ready_for_face_jobs" in source
    ready_block = source.split("bool ready_for_face_jobs", 1)[1].split("int print_usage", 1)[0]
    assert "image_vips" not in ready_block


def test_worker_vips_build_preflight_checks_host_pkg_config_dependencies():
    build_script = (PROJECT_ROOT / "tools" / "build-worker.sh").read_text(encoding="utf-8")

    assert "pkg-config --exists" in build_script
    assert "glib-2.0 gio-2.0 gobject-2.0 expat" in build_script
    assert "libglib2.0-dev libexpat1-dev" in build_script


def test_model_sync_owns_manifest_hash_and_atomic_install_logic():
    source = (PROJECT_ROOT / "worker" / "src" / "model_sync.cpp").read_text(encoding="utf-8")

    assert '"sha256"' in source
    assert "file_sha256" in source
    assert "manifest.json.download" in source
    assert "std::filesystem::rename" in source
    assert "X-Worker-Id" in source
