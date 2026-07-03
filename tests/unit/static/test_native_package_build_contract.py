from pathlib import Path


def test_synology_build_uses_onnxruntime_native_face_processor():
    build_script = Path("SynoBuildConf/build").read_text(encoding="utf-8")

    assert "./tools/build-native-face-processor.sh" in build_script
    assert "native ONNXRuntime face processor build failed" in build_script
    assert "./tools/smoke-native-face-processor.sh" in build_script
    assert "native ONNXRuntime face processor smoke checks failed" in build_script
    assert "./tools/functional-native-face-processor.sh" in build_script
    assert "native ONNXRuntime face processor functional checks failed" in build_script
    assert build_script.index("./tools/build-native-face-processor.sh") < build_script.index("./tools/smoke-native-face-processor.sh")
    assert build_script.index("./tools/smoke-native-face-processor.sh") < build_script.index("./tools/functional-native-face-processor.sh")
    assert build_script.index("./tools/functional-native-face-processor.sh") < build_script.index("make clean_python_artifacts")


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


def test_native_face_processor_smoke_script_checks_real_binary_vector_commands():
    smoke_script = Path("tools/smoke-native-face-processor.sh").read_text(encoding="utf-8")

    assert "NATIVE_BINARY" in smoke_script
    assert "onnxruntime-native" in smoke_script
    assert "rank_embeddings" in smoke_script
    assert "face_native_rank_embeddings" in smoke_script
    assert "profile_math" in smoke_script
    assert "face_native_profile_math" in smoke_script
    assert "python3 -m json.tool" in smoke_script
    assert 'p["result"]["ranks"][0]["best_index"] == 0' in smoke_script
    assert 'p["result"]["centroid_embedding"]' in smoke_script


def test_native_face_processor_functional_script_checks_real_inference_commands():
    functional_script = Path("tools/functional-native-face-processor.sh").read_text(encoding="utf-8")

    assert "AV_IMGDATA_NATIVE_FUNCTIONAL_TEST_REQUIRED" in functional_script
    assert "AV_IMGDATA_NATIVE_MODEL_ROOT" in functional_script
    assert "AV_IMGDATA_NATIVE_MODEL_NAME" in functional_script
    assert "AV_IMGDATA_NATIVE_TEST_IMAGE" in functional_script
    assert "det_10g.onnx" in functional_script
    assert "w600k_r50.onnx" in functional_script
    assert '"${NATIVE_BINARY}" probe' in functional_script
    assert '"${NATIVE_BINARY}" embed --input' in functional_script
    assert '"${NATIVE_BINARY}" embed_batch --input' in functional_script
    assert 'payload["type"] == "face_native_embed"' in functional_script
    assert 'payload["type"] == "face_native_embed_batch"' in functional_script
    assert "embedding norm outside expected range" in functional_script


def test_optional_libvips_image_processor_is_feature_flagged():
    build_script = Path("SynoBuildConf/build").read_text(encoding="utf-8")
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")
    build_vips = Path("tools/build-native-image-processor-vips.sh").read_text(encoding="utf-8")
    cmake = Path("processors/native/image_backend_vips/CMakeLists.txt").read_text(encoding="utf-8")
    source = Path("processors/native/image_backend_vips/src/main.cpp").read_text(encoding="utf-8")

    assert 'AV_IMGDATA_WITH_VIPS:-0' in build_script
    assert "./tools/build-native-image-processor-vips.sh" in build_script
    assert 'AV_IMGDATA_WITH_VIPS:-0' in install_script
    assert "av-imgdata-image-processor" in install_script
    assert "vips-image-processor-install" in build_vips
    assert "-DCMAKE_BUILD_TYPE=Release" in build_vips
    assert "AV_IMGDATA_NATIVE_STRIP:-1" in build_vips
    assert "add_executable(av-imgdata-image-processor" in cmake
    assert "INSTALL_RPATH" in cmake
    assert "0.1.0-skeleton image-backend-vips" in source
    assert "libvips_not_linked" in source


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
    assert '"build/native/*/vips-image-processor-build"' in build_package
    assert '"build/native/*/vips-image-processor-install"' in build_package
    assert "build/native/*/deps" not in build_package
    assert '"ui/node_modules"' in build_package
    assert ".av_imgdata-link-sanitize.XXXXXX" in build_package
    assert "sanitize_project_for_toolkit_link" in build_package.split('log "Building Synology package"', 1)[0]


def test_package_info_is_platform_specific_for_native_binary():
    info_script = Path("INFO.sh").read_text(encoding="utf-8")

    assert 'arch="$(pkg_get_platform)"' in info_script
    assert 'arch="noarch"' not in info_script
