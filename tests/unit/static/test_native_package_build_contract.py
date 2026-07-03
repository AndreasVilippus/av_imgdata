from pathlib import Path


def test_synology_build_uses_onnxruntime_native_face_processor():
    build_script = Path("SynoBuildConf/build").read_text(encoding="utf-8")

    assert "./tools/build-native-face-processor.sh" in build_script
    assert "native ONNXRuntime face processor build failed" in build_script


def test_native_face_processor_build_uses_runtime_heif_loader():
    build_script = Path("tools/build-native-face-processor.sh").read_text(encoding="utf-8")
    cmake = Path("processors/native/face_processor/CMakeLists.txt").read_text(encoding="utf-8")
    source = Path("processors/native/face_processor/src/main.cpp").read_text(encoding="utf-8")

    assert "resolve_heif_root" in build_script
    assert "libheif headers not found" in build_script
    assert "copy_library_family \"${HEIF_ROOT}\" \"libheif.so*\"" not in build_script
    assert "libheif/heif.h" in cmake
    assert "HEIF_LIBRARY" not in cmake
    assert "AV_FACE_PROCESSOR_WITH_HEIF" in cmake
    assert "dlopen" in source
    assert "heif_have_decoder_for_format" in source


def test_native_face_processor_release_build_strips_binary_by_default():
    build_script = Path("tools/build-native-face-processor.sh").read_text(encoding="utf-8")

    assert "-DCMAKE_BUILD_TYPE=Release" in build_script
    assert "strip_native_binary" in build_script
    assert "AV_IMGDATA_NATIVE_STRIP:-1" in build_script
    assert "--strip-unneeded" in build_script
    assert "native binary remains unstripped" in build_script


def test_synology_install_requires_native_face_processor_libraries():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "onnxruntime-native" in install_script
    assert "libonnxruntime.so" in install_script
    assert "libjpeg.so" in install_script
    assert "libheif.so" not in install_script
    assert 'cp -av "$NATIVE_INSTALL/lib/."' not in install_script
    assert "find \"$NATIVE_INSTALL/lib\" -maxdepth 1" in install_script


def test_package_wrapper_moves_local_artifacts_before_toolkit_link():
    build_package = Path("tools/build-package.sh").read_text(encoding="utf-8")

    assert "sanitize_project_for_toolkit_link" in build_package
    assert "restore_local_build_artifacts" in build_package
    assert '".test-venv"' in build_package
    assert '"build"' not in build_package
    assert "SANITIZE_NATIVE_BUILD_PATTERNS" in build_package
    assert '"build/native/*/face_processor-build"' in build_package
    assert '"build/native/*/face_processor-install"' in build_package
    assert "build/native/*/deps" not in build_package
    assert '"ui/node_modules"' in build_package
    assert ".av_imgdata-link-sanitize.XXXXXX" in build_package
    assert "sanitize_project_for_toolkit_link" in build_package.split('log "Building Synology package"', 1)[0]


def test_package_info_is_platform_specific_for_native_binary():
    info_script = Path("INFO.sh").read_text(encoding="utf-8")

    assert 'arch="$(pkg_get_platform)"' in info_script
    assert 'arch="noarch"' not in info_script
