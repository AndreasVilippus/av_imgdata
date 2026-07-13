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
    assert "LoadLibraryA" in source
    assert "GetProcAddress" in source
    assert "heif_have_decoder_for_format" in source
    assert 'candidates.push_back("libheif.dll")' in source
    assert 'candidates.push_back("libheif.so.1")' in source


def test_native_face_processor_cmake_does_not_mix_host_headers_into_cross_builds():
    cmake = Path("processors/native/face_processor/CMakeLists.txt").read_text(encoding="utf-8")
    windows_build = Path("tools/build-native-face-processor-windows.sh").read_text(encoding="utf-8")

    assert 'PATHS "${JPEG_ROOT}/include" "${JPEG_ROOT}/usr/include"\n    NO_DEFAULT_PATH' in cmake
    assert 'PATHS "${JPEG_ROOT}/lib" "${JPEG_ROOT}/lib64" "${JPEG_ROOT}/usr/lib" "${JPEG_ROOT}/usr/lib64"\n    NO_DEFAULT_PATH' in cmake
    assert 'PATHS "${HEIF_ROOT}/include" "${HEIF_ROOT}/usr/include" "${JPEG_ROOT}/include" "${JPEG_ROOT}/usr/include"\n    NO_DEFAULT_PATH' in cmake
    assert "^JPEG_INCLUDE_DIR:PATH=/usr/include$" in windows_build
    assert "-UJPEG_INCLUDE_DIR" in windows_build
    assert "-UJPEG_LIBRARY" in windows_build
    assert "-UHEIF_INCLUDE_DIR" in windows_build
    assert "Windows face processor build directory is not writable" in windows_build
    assert "AV_IMGDATA_FACE_PROCESSOR_WINDOWS_BUILD_ROOT" in windows_build
    assert "AV_IMGDATA_FACE_PROCESSOR_WINDOWS_DIST_DIR" in windows_build
    assert '"${DEPS_ROOT}/vips"' in windows_build
    assert 'copy_matching_files "${HEIF_ROOT}/bin" "${DIST_DIR}/bin"' in windows_build
    assert '"libheif*.dll"' in windows_build
    assert '"libde265*.dll"' in windows_build
    assert '"libaom*.dll"' in windows_build
    assert '"libsharpyuv*.dll"' in windows_build
    assert "cp -L" in windows_build
    assert "cp -aL" not in windows_build


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


def test_optional_libvips_image_processor_is_packaged_by_default_with_opt_out():
    build_script = Path("SynoBuildConf/build").read_text(encoding="utf-8")
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")
    build_vips = Path("tools/build-native-image-processor-vips.sh").read_text(encoding="utf-8")
    cmake = Path("processors/native/image_backend_vips/CMakeLists.txt").read_text(encoding="utf-8")
    source = Path("processors/native/image_backend_vips/src/main.cpp").read_text(encoding="utf-8")

    assert 'AV_IMGDATA_WITH_VIPS:-1' in build_script
    assert "./tools/build-native-image-processor-vips.sh" in build_script
    assert 'AV_IMGDATA_WITH_VIPS:-1' in install_script
    assert "av-imgdata-image-processor" in install_script
    assert "libvips.so" in install_script
    assert "cleanup_native_build_artifacts" in install_script
    assert "INSTALL_SUCCEEDED=0" in install_script
    assert "Preserving native build artifacts after failed install for diagnostics." in install_script
    assert '"$native_root/face_processor-build"' not in install_script
    assert '"$native_root/face_processor-install"' not in install_script
    assert '"$native_root/deps/source-cache"' in install_script
    assert '"$native_root/libde265-build"' in install_script
    assert '"$native_root/libde265-source"' in install_script
    assert '"$native_root/libheif-build"' in install_script
    assert '"$native_root/libheif-source"' in install_script
    assert '"$native_root/libvips-source"' in install_script
    assert '"$native_root/vips-image-processor-install"' not in install_script
    assert '"$native_root/deps"' not in install_script
    assert "vips-image-processor-install" in build_vips
    assert "LIBDE265_VERSION" in build_vips
    assert "b92beb6b53c346db9a8fae968d686ab706240099cdd5aff87777362d668b0de7" in build_vips
    assert "LIBHEIF_VERSION" in build_vips
    assert "e1ac2abb354fdc8ccdca71363ebad7503ad731c84022cf460837f0839e171718" in build_vips
    assert "LIBVIPS_VERSION" in build_vips
    assert "d114d7c132ec5b45f116d654e17bb4af84561e3041183cd4bfd79abfb85cf724" in build_vips
    assert "curl -fkL" in build_vips
    assert "sha256sum -c" in build_vips
    assert "build_heif_stack" in build_vips
    assert "require_libvips_host_dependencies" in build_vips
    assert "require_pkg_config_package glib-2.0 libglib2.0-dev" in build_vips
    assert "require_pkg_config_package gio-2.0 libglib2.0-dev" in build_vips
    assert "require_pkg_config_package gobject-2.0 libglib2.0-dev" in build_vips
    assert "require_pkg_config_package expat libexpat1-dev" in build_vips
    assert "--disable-x265" in build_vips
    assert "--disable-aom" in build_vips
    assert "--disable-rav1e" in build_vips
    assert "--disable-gdk-pixbuf" in build_vips
    assert "--disable-examples" in build_vips
    assert "-Wno-error=maybe-uninitialized" in build_vips
    assert 'LDFLAGS="-L${VIPS_PREFIX}/lib"' in build_vips
    assert 'LDFLAGS="-L${VIPS_PREFIX}/lib${synology_lib_dir' not in build_vips
    assert "builtin_h265_decoder=yes" in build_vips
    assert "builtin_h265_encoder=yes" in build_vips
    assert "x265/GPL must stay out of this package" in build_vips
    assert "install_heif_stack_license_files" in build_vips
    assert "share/licenses/AV_ImgData/heif-stack" in build_vips
    assert "sources/${LIBDE265_TARBALL}" in build_vips
    assert "sources/${LIBHEIF_TARBALL}" in build_vips
    assert "install_libvips_license_files" in build_vips
    assert "share/licenses/AV_ImgData/libvips" in build_vips
    assert "sources/${LIBVIPS_TARBALL}" in build_vips
    assert "vips-${LIBVIPS_VERSION}-av-imgdata.patch" in build_vips
    assert "install_runtime_dependency_notice" in build_vips
    assert "share/licenses/AV_ImgData/runtime-dependencies" in build_vips
    assert "packaged-libraries.txt" in build_vips
    assert "$VIPS_INSTALL/share/licenses" in install_script
    assert "patch_libvips_source" in build_vips
    assert "has_header_symbol('tiff.h', 'COMPRESSION_WEBP'" in build_vips
    assert "AV_ImgData package build skips upstream libvips tools" in build_vips
    assert "AV_ImgData package build skips upstream libvips tests" in build_vips
    assert "AV_ImgData package build skips upstream libvips fuzzers" in build_vips
    assert "libvips meson tool/test/fuzz subdirs were not disabled" in build_vips
    assert "vipsmarshal_h = custom_target" in build_vips
    assert "glib-genmarshal --prefix=vips --header" in build_vips
    assert "glib-genmarshal --prefix=vips --body" in build_vips
    assert "The Synology Toolkit GLib is older than libvips 8.16.1 expects" in build_vips
    assert "g_utf8_make_valid" in build_vips
    assert "g_strdup(vips_value_get_save_string" in build_vips
    assert "#if 0 \\&\\& GLIB_CHECK_VERSION(2, 62, 0)" in build_vips
    assert "--pragma-once" not in build_vips
    assert "--include-header" not in build_vips
    assert "resolve_synology_toolchain_sysroot" in build_vips
    assert "ToolChainSysRoot" in build_vips
    assert "jpeglib.h" in build_vips
    assert "-Dc_args=-I${synology_sysroot}/usr/include" in build_vips
    assert "-Dc_link_args=-L${synology_sysroot}/usr/lib" in build_vips
    assert "-Dcpp_args=-I${synology_sysroot}/usr/include" not in build_vips
    assert "-Dcpp_link_args=-L${synology_sysroot}/usr/lib" not in build_vips
    assert "patch_libvips_ninja_link_args" in build_vips
    assert "resolve_synology_library_file" in build_vips
    assert "/^build .*: (c|cpp)_LINKER/" in build_vips
    assert 'token ~ /^-Wl,--sysroot=/' in build_vips
    assert "-DCMAKE_EXE_LINKER_FLAGS=-Wl,--sysroot=${NATIVE_PROCESSOR_SYSROOT}" not in build_vips
    assert 'token == "-ljpeg"' in build_vips
    assert 'token == "-lpng16"' in build_vips
    assert 'token == "-lwebpdemux"' in build_vips
    assert 'token == "-llcms2"' in build_vips
    assert 'token == "-lglib-2.0"' not in build_vips
    assert 'token == "-lgio-2.0"' not in build_vips
    assert 'token == "-lgobject-2.0"' not in build_vips
    assert 'libdir "/libglib-2\\\\.0\\\\.so"' in build_vips
    assert 'libdir "/libgio-2\\\\.0\\\\.so"' in build_vips
    assert 'libdir "/libgobject-2\\\\.0\\\\.so"' in build_vips
    assert 'token == "-L" libdir' in build_vips
    assert "LINK_ARGS = -L" not in build_vips
    assert "meson setup" in build_vips
    assert "-Dheif=enabled" in build_vips
    assert "-Dheif=disabled" not in build_vips
    assert "-Draw=enabled" not in build_vips
    assert "require_tool strings" in build_vips
    assert "copy_libvips_runtime_dependencies" in build_vips
    assert '"libheif.so*"' in build_vips
    assert '"libde265.so*"' in build_vips
    assert '"libmount.so*"' in build_vips
    assert '"libblkid.so*"' in build_vips
    assert '"libuuid.so*"' in build_vips
    assert "-DCMAKE_BUILD_TYPE=Release" in build_vips
    assert "AV_IMGDATA_NATIVE_STRIP:-1" in build_vips
    assert "libvips image processor is only the skeleton binary" in build_vips
    assert "libvips_not_linked" in build_vips
    assert "strings \"${NATIVE_BINARY}\"" in build_vips
    assert "runtime probe skipped: Toolkit build runtime is older than packaged Synology sysroot libraries" in build_vips
    assert "GLIBC_[0-9.]+" in build_vips
    assert "add_executable(av-imgdata-image-processor" in cmake
    assert "pkg_check_modules(VIPS REQUIRED vips)" in cmake
    assert "find_library(VIPS_SHARED_LIBRARY" in cmake
    assert "VIPS_DIRECT_RUNTIME_LIBS" in cmake
    assert 'VIPS_LIB MATCHES "^(glib-2.0|gobject-2.0|gio-2.0)$"' in cmake
    assert "find_library(VIPS_DIRECT_${VIPS_LIB_VAR}_LIBRARY" in cmake
    assert "libvips direct runtime library not found" in cmake
    assert "target_link_libraries(av-imgdata-image-processor PRIVATE ${VIPS_SHARED_LIBRARY} ${VIPS_DIRECT_RUNTIME_LIBS})" in cmake
    assert "target_link_libraries(av-imgdata-image-processor PRIVATE ${VIPS_LIBRARIES})" not in cmake
    assert "-Wl,--allow-shlib-undefined" in cmake
    assert "INSTALL_RPATH" in cmake
    assert "backend" in source
    assert "libvips" in source
    assert "vips_ready" in source
    assert "vips_image_new_from_file" in source
    assert "0.1.0-skeleton image-backend-vips" not in source
    assert "libvips_not_linked" not in source


def test_synology_install_requires_native_face_processor_libraries():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "ensure_native_face_processor" in install_script
    assert "Native face processor missing; building before package staging." in install_script
    assert "./tools/build-native-face-processor.sh" in install_script
    assert "./tools/smoke-native-face-processor.sh" in install_script
    assert "./tools/functional-native-face-processor.sh" in install_script
    assert "ensure_native_face_processor || return 1" in install_script
    assert "create_install || return 1" in install_script
    assert "./INFO.sh > INFO" in install_script
    assert "onnxruntime-native" in install_script
    assert "libonnxruntime.so" in install_script
    assert "libjpeg.so" in install_script
    assert "libheif.so" not in install_script
    assert 'cp -av "$NATIVE_INSTALL/lib/."' not in install_script
    assert "find \"$NATIVE_INSTALL/lib\" -maxdepth 1" in install_script
    assert "$NATIVE_INSTALL/share/licenses" in install_script


def test_synology_install_can_build_missing_vips_processor_before_staging():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "ensure_vips_image_processor" in install_script
    assert "Optional libvips image processor missing; building before package staging." in install_script
    assert "./tools/build-native-image-processor-vips.sh" in install_script
    assert install_script.index("ensure_vips_image_processor") < install_script.index("VIPS_INSTALL=\"$(native_install_root vips-image-processor-install)\"")


def test_ui_makefile_uses_unquoted_dist_targets_and_utf8_snpm():
    makefile = Path("ui/Makefile").read_text(encoding="utf-8")

    assert "JS_DIR=dist" in makefile
    assert "JS_NAMESPACE=SYNO.SDS.App.AV_ImgData" in makefile
    assert "BUNDLE_JS=dist/av-img-data.bundle.js" in makefile
    assert "BUNDLE_CSS=dist/style/av-img-data.bundle.css" in makefile
    assert 'JS_DIR="dist"' not in makefile
    assert 'BUNDLE_JS="dist/av-img-data.bundle.js"' not in makefile
    assert "PYTHONIOENCODING=utf-8 /usr/local/tool/snpm install" in makefile
    assert "PYTHONIOENCODING=utf-8 /usr/local/tool/snpm run build" in makefile
    assert "install: $(BUNDLE_JS) style.css $(SUBDIR)" in makefile
    assert '$(MAKE) -f Makefile.js.inc JSCompress JS_NAMESPACE=\\"$(JS_NAMESPACE)\\" JS_DIR=$(JS_DIR)' in makefile
    assert '$(MAKE) -f Makefile.js.inc install_JSCompress JS_NAMESPACE=\\"$(JS_NAMESPACE)\\" JS_DIR=$(JS_DIR)' in makefile
    assert "install: $(BUNDLE_JS) style.css $(SUBDIR) JSCompress install_JSCompress" not in makefile


def test_native_face_processor_packages_third_party_license_notices():
    build_script = Path("tools/build-native-face-processor.sh").read_text(encoding="utf-8")
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "AV_IMGDATA_NATIVE_DEPS_TARGET:-linux-x86_64" in build_script
    assert '"${PROJECT_DIR}/worker/native_deps/${deps_target}/onnxruntime"' in build_script
    assert '"${PROJECT_DIR}/worker/native_deps/${deps_target}"/onnxruntime-linux-x64-*' in build_script
    assert "resolve_synology_toolchain_compilers" in build_script
    assert "/usr/local/x86_64-pc-linux-gnu/bin/x86_64-pc-linux-gnu-g++" in build_script
    assert "/usr/local/*/bin/*-g++" in build_script
    assert 'export CXX="${cxx_candidate}"' in build_script
    assert 'export CC="${gcc_candidate}"' in build_script
    assert "install_native_face_processor_license_files" in build_script
    assert "share/licenses/AV_ImgData/native-face-processor" in build_script
    assert "onnxruntime.LICENSE" in build_script
    assert "onnxruntime.ThirdPartyNotices.txt" in build_script
    assert "libjpeg-turbo.LICENSE" in build_script
    assert "$NATIVE_INSTALL/share/licenses" in install_script
    assert "$VIPS_INSTALL/share/licenses" in install_script


def test_package_wrapper_moves_local_artifacts_before_toolkit_link():
    build_package = Path("tools/build-package.sh").read_text(encoding="utf-8")

    assert "sanitize_project_for_toolkit_link" in build_package
    assert "restore_local_build_artifacts" in build_package
    assert '".test-venv"' in build_package
    assert '"build"' not in build_package
    assert '"build/chroot/*"' in build_package
    assert "SANITIZE_NATIVE_BUILD_PATTERNS" in build_package
    assert "cleanup_existing_toolkit_link_target" in build_package
    assert 'target="${WORKSPACE_ROOT}/build_env/ds.${platform}-${version}/source/${PACKAGE_NAME}"' in build_package
    assert '[[ -e "${target}" ]] || return 0' in build_package
    assert "Existing Toolkit link target cannot be removed" in build_package
    assert '"build/native/*/face_processor-build"' in build_package
    assert '"build/native/*/face_processor-install"' not in build_package
    assert '"build/native/*/libde265-build"' in build_package
    assert '"build/native/*/libde265-source"' in build_package
    assert '"build/native/*/libheif-build"' in build_package
    assert '"build/native/*/libheif-source"' in build_package
    assert '"build/native/*/libvips-build"' in build_package
    assert '"build/native/*/libvips-source"' in build_package
    assert '"build/native/*/vips-image-processor-build"' in build_package
    assert '"build/native/*/vips-image-processor-install"' not in build_package
    assert "build/native/*/deps" not in build_package
    assert '"ui/node_modules"' in build_package
    assert 'mktemp -d "${PACKAGE_ROOT}/../.av_imgdata-link-sanitize.XXXXXX"' in build_package
    assert "sanitize_project_for_toolkit_link" in build_package.split('log "Building Synology package"', 1)[0]


def test_package_info_is_platform_specific_for_native_binary():
    info_script = Path("INFO.sh").read_text(encoding="utf-8")

    assert 'arch="$(pkg_get_platform)"' in info_script
    assert 'arch="noarch"' not in info_script
