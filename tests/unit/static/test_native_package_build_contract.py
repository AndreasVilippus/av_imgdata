from pathlib import Path
import re


def test_synology_package_targets_dsm_74_toolchain():
    info = Path("INFO.sh").read_text(encoding="utf-8")
    depends = Path("SynoBuildConf/depends").read_text(encoding="utf-8")
    build_package = Path("tools/build-package.sh").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert 'os_min_ver="7.4-00000"' in info
    assert 'all="7.4.0"' in depends
    assert "DEFAULT_ARGS=(-v 7.4 -p geminilake -c)" in build_package
    assert "pkgcreate_option_value -v 7.4" in build_package
    assert "DSM `7.4` or newer" in readme
    assert "-v 7.3" not in build_package
    assert 'all="7.3.0"' not in depends
    assert 'os_min_ver="7.3-00000"' not in info


def test_root_makefile_does_not_use_synology_module_generator_for_ui_install():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "GenerateModuleFiles.php" not in makefile
    assert "Makefile.js.inc" not in makefile
    assert "JSCompress" not in makefile
    assert "shrinksafe.php" not in makefile
    assert "GenerateModuleFiles.php $@ $@" not in makefile


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


def test_synology_install_propagates_native_build_failures_to_script_exit():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "create_install\n\tcreate_spk" in install_script
    assert "create_install || return 1" not in install_script
    assert "create_spk || return 1" not in install_script
    assert "main \"$@\"\nexit $?" in install_script


def test_synology_native_face_processor_build_auto_fetches_linux_deps():
    build_script = Path("tools/build-native-face-processor.sh").read_text(encoding="utf-8")

    assert "auto_fetch_native_deps" in build_script
    assert "AV_IMGDATA_NATIVE_FETCH_DEPS:-1" in build_script
    assert "AV_IMGDATA_NATIVE_DEPS_TARGET:-linux-x86_64" in build_script
    assert "tools/fetch-worker-native-deps.sh" in build_script
    assert "--target \"${deps_target}\" --no-update-check" in build_script
    resolve_block = "auto_fetch_native_deps\nresolve_onnxruntime_root\nresolve_jpeg_root"
    assert resolve_block in build_script


def test_native_dependency_fetches_use_available_ca_bundle_for_curl():
    native_fetch = Path("tools/fetch-worker-native-deps.sh").read_text(encoding="utf-8")
    windows_fetch = Path("tools/fetch-worker-windows-deps.sh").read_text(encoding="utf-8")

    for script in (native_fetch, windows_fetch):
        assert "curl_with_ca" in script
        assert "/etc/ssl/cert.pem" in script
        assert "/etc/ssl/certs/ca-certificates.crt" in script
        assert 'curl --cacert "${ca_cert}" "$@"' in script
        assert 'curl "$@"' in script
        assert '"${ca_args[@]}"' not in script

    assert "curl_with_ca -L -f --retry 3 --retry-delay 2" in native_fetch
    assert "curl_with_ca -fsSL" in native_fetch
    assert "curl_with_ca -L --fail --retry 3" in windows_fetch


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


def test_native_face_processor_uses_windows_wide_paths_for_image_files():
    source = Path("processors/native/face_processor/src/main.cpp").read_text(encoding="utf-8")

    assert "windows_path_from_text" in source
    assert "MultiByteToWideChar(CP_UTF8" in source
    assert "GetFileAttributesW(wide.c_str())" in source
    decode_jpeg = source.split("bool decode_jpeg", 1)[1].split("jpeg_decompress_struct", 1)[0]
    assert "_wfopen(wide_path.c_str(), L\"rb\")" in decode_jpeg
    assert "fopen(path.c_str(), \"rb\")" in decode_jpeg
    assert "#ifdef _WIN32" in decode_jpeg


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
    assert "is_glibc_runtime_mismatch" in smoke_script
    assert "GLIBC_[0-9.]+" in smoke_script
    assert "smoke checks skipped: Toolkit build runtime is older than packaged Synology sysroot libraries" in smoke_script
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
    assert 'if [ ! -f "$package_tgz_dir/ui/config" ]; then' in install_script
    assert "ui/config missing in package staging dir" in install_script
    assert "Check ui/Makefile config target and DSM GenerateJSDepend integration." in install_script
    assert 'make packageinstall DESTDIR="$package_tgz_dir" PKG_DIR="$PKG_DIR" || return 1' in install_script
    assert "cleanup_native_build_artifacts" in install_script
    assert "INSTALL_SUCCEEDED=0" in install_script
    assert 'if [ "${NOSTRIP:-}" = "NOSTRIP" ]; then' in install_script
    assert 'export AV_IMGDATA_NATIVE_STRIP="${AV_IMGDATA_NATIVE_STRIP:-0}"' in install_script
    assert "Debug package requested; rebuilding native face processor without stripping." in install_script
    assert "assert_no_duplicate_package_sonames" in install_script
    assert "copy_runtime_library_family" in install_script
    assert "readelf is required to verify packaged runtime library SONAMEs." in install_script
    assert "duplicate package runtime library SONAMEs" in install_script
    assert 'copy_runtime_library_family "$NATIVE_INSTALL/lib" "$package_tgz_dir/lib" \'libonnxruntime.so*\' \'libjpeg.so*\'' in install_script
    assert 'copy_runtime_library_family "$VIPS_INSTALL/lib" "$package_tgz_dir/lib" \'*.so*\'' in install_script
    assert 'find "$VIPS_INSTALL/lib" -maxdepth 1 \\( -type f -o -type l \\) -name \'*.so*\' -exec cp -av' not in install_script
    assert "Preserving native build artifacts after failed install for diagnostics." in install_script
    assert '"$native_root/face_processor-build"' in install_script
    assert '"$native_root/face_processor-install"' in install_script
    assert '"$native_root/deps/source-cache"' in install_script
    assert '"$native_root/libde265-build"' in install_script
    assert '"$native_root/libde265-source"' in install_script
    assert '"$native_root/libheif-build"' in install_script
    assert '"$native_root/libheif-source"' in install_script
    assert '"$native_root/libvips-source"' in install_script
    assert '"$native_root/vips-image-processor-install"' not in install_script
    assert '"$native_root/deps"' not in install_script
    assert "vips-image-processor-install" in build_vips
    assert "BUILD_FINGERPRINT_FILE" in build_vips
    assert "build_fingerprint()" in build_vips
    assert "--print-fingerprint" in build_vips
    assert "fingerprint_contract=av-imgdata-image-processor-vips-v1" in build_vips
    assert "native_strip=%s" in build_vips
    assert "processors/native/image_backend_vips/src/main.cpp" in build_vips
    assert "processors/native/image_backend_vips/CMakeLists.txt" in build_vips
    assert "tools/build-native-image-processor-vips.sh" in build_vips
    assert 'build_fingerprint > "${BUILD_FINGERPRINT_FILE}"' in build_vips
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
    assert "select_pkg_config_tool" in build_vips
    assert "configure_synology_pkg_config_if_available" in build_vips
    assert "PKG_CONFIG_TOOL" in build_vips
    assert 'for env_file in /env64.mak /env.mak; do' in build_vips
    assert "host_value=" in build_vips
    assert '"${HOST}-pkg-config"' in build_vips
    assert '"/usr/bin/${HOST}-pkg-config"' in build_vips
    assert "for candidate in /usr/bin/*-pkg-config; do" in build_vips
    assert "pkg-config-origin is missing" in build_vips
    assert "PKG_CONFIG_LIBDIR" in build_vips
    assert 'grep -Fq "${synology_sysroot}/usr" "${glib_pc}"' in build_vips
    assert "unset PKG_CONFIG_SYSROOT_DIR" in build_vips
    assert "Using Synology pkg-config metadata with absolute sysroot paths" in build_vips
    assert 'export PKG_CONFIG="${PKG_CONFIG_TOOL}"' in build_vips
    assert 'if ! "${PKG_CONFIG_TOOL}" --exists "${package}"; then' in build_vips
    assert "require_tool pkg-config" not in build_vips
    assert "pkg-config --exists" not in build_vips
    assert "require_tool readelf" in build_vips
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
    assert "sources/${LIBDE265_TARBALL}" not in build_vips
    assert "sources/${LIBHEIF_TARBALL}" not in build_vips
    assert "Source tarballs are intentionally not embedded in the runtime package" in build_vips
    assert "install_libvips_license_files" in build_vips
    assert "share/licenses/AV_ImgData/libvips" in build_vips
    assert "sources/${LIBVIPS_TARBALL}" not in build_vips
    assert "vips-${LIBVIPS_VERSION}-av-imgdata.patch" in build_vips
    assert "install_runtime_dependency_notice" in build_vips
    assert "share/licenses/AV_ImgData/runtime-dependencies" in build_vips
    assert "packaged-libraries.txt" in build_vips
    assert "verify-third-party-licenses.py --root \"$package_tgz_dir\" --write" in install_script
    assert "$VIPS_INSTALL/share/licenses" in install_script
    assert "patch_libvips_source" in build_vips
    assert "vips_foreign_load_heif_get_cicp" not in build_vips
    assert "heifload: setting CICP from nclx" not in build_vips
    assert "CICP image, skipping colourspace conversion" not in build_vips
    assert "CICP image, skipping colour management" not in build_vips
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
    assert "copy_library_family" not in build_vips
    assert "shared_library_link_name" not in build_vips
    assert 'source_soname%.*}.so' not in build_vips
    assert 'for dir in /usr/local/*/*/sys-root/usr/lib' not in build_vips
    assert 'multiarch_dir="/usr/lib/$(gcc -dumpmachine' not in build_vips
    assert "for dir in /usr/lib/*-linux-gnu /lib/*-linux-gnu" not in build_vips
    assert "strip_runtime_libraries" in build_vips
    assert "assert_no_duplicate_runtime_sonames" in build_vips
    assert "duplicate runtime library SONAMEs staged" in build_vips
    assert "BUILD_HOST_LD_LIBRARY_PATH" in build_vips
    assert "restore_build_host_library_path" in build_vips
    assert 'LD_LIBRARY_PATH="${VIPS_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"\nexport PKG_CONFIG_SYSROOT_DIR' not in build_vips
    assert "runtime_probe_library_path" in build_vips
    assert 'probe_path="${probe_path}:${synology_sysroot}/usr/lib"' in build_vips
    assert 'LD_LIBRARY_PATH="$(runtime_probe_library_path)" "${NATIVE_BINARY}" probe' in build_vips
    assert not re.search(r'build_env/ds\.\$\{platform_lower\}-[0-9.]+/env(64)?\.mak', build_vips)
    assert '[ -d "${env_root}/${value#/}" ]' in build_vips
    assert "configure_synology_toolchain_compilers_if_available" in build_vips
    assert "ToolChainPrefix" in build_vips
    assert 'candidates+=("${prefix_value}g++")' in build_vips
    assert 'candidates+=("/usr/local/${host_value}/bin/${host_value}-g++")' in build_vips
    assert "for candidate in /usr/local/*/bin/*-g++; do" in build_vips
    assert 'export CC="${gcc_candidate}"' in build_vips
    assert 'export CXX="${cxx_candidate}"' in build_vips
    assert "Using Synology toolchain compiler for libvips stack:" in build_vips
    assert "--disable-libfuzzer" in build_vips
    assert "configure_synology_host_toolchain_if_available" not in build_vips
    assert 'export CC="${toolchain_bin}/${host}-gcc"' not in build_vips
    assert 'export CXX="${toolchain_bin}/${host}-g++"' not in build_vips
    assert 'pkg_config_overlay="${BUILD_ROOT}/pkgconfig-overlay"' in build_vips
    assert 'cp -a --no-preserve=ownership "${synology_sysroot}/usr/lib/pkgconfig/"*.pc "${pkg_config_overlay}/"' in build_vips
    assert "glib_genmarshal=$(command -v glib-genmarshal" in build_vips
    assert "glib_mkenums=$(command -v glib-mkenums" in build_vips
    assert 'meson_pkg_config_path="${meson_pkg_config_path}:${pkg_config_overlay}"' in build_vips
    assert 'PKG_CONFIG_SYSROOT_DIR= PKG_CONFIG_PATH="${meson_pkg_config_path}" meson "${meson_args[@]}"' in build_vips
    assert "--strip-unneeded" in build_vips
    assert "readelf -d" in build_vips
    assert "-name 'libheif.so*'" in build_vips
    assert "-name 'libde265.so*'" in build_vips
    assert '"libmount.so*"' not in build_vips
    assert '"libblkid.so*"' not in build_vips
    assert '"libuuid.so*"' not in build_vips
    assert '"libglib-2.0.so*"' not in build_vips
    assert '"libgio-2.0.so*"' not in build_vips
    assert '"libjpeg.so*"' not in build_vips
    assert '"libpng16.so*"' not in build_vips
    assert '"libtiff.so*"' not in build_vips
    assert '"libwebp.so*"' not in build_vips
    assert '"liblcms2.so*"' not in build_vips
    assert '"libz.so*"' not in build_vips
    assert "prune_non_runtime_install_artifacts" in build_vips
    assert '"${VIPS_PREFIX}/include"' in build_vips
    assert '"${VIPS_PREFIX}/lib/cmake"' in build_vips
    assert '"${VIPS_PREFIX}/lib/pkgconfig"' in build_vips
    assert '"${VIPS_PREFIX}/share/locale"' in build_vips
    assert '"${VIPS_PREFIX}/share/man"' in build_vips
    assert '"${VIPS_PREFIX}/share/mime"' in build_vips
    assert '"${VIPS_PREFIX}/share/thumbnailers"' in build_vips
    assert "packaged libheif runtime library missing" in build_vips
    assert "packaged libde265 runtime library missing" in build_vips
    assert "-DCMAKE_BUILD_TYPE=Release" in build_vips
    assert "AV_IMGDATA_NATIVE_STRIP:-1" in build_vips
    assert "libvips image processor is only the skeleton binary" in build_vips
    assert "libvips_not_linked" in build_vips
    assert "strings \"${NATIVE_BINARY}\"" in build_vips
    assert "is_toolkit_runtime_probe_unavailable" in build_vips
    assert "runtime probe skipped: Toolkit build runtime cannot execute packaged Synology-targeted libraries" in build_vips
    assert "GLIBC_[0-9.]+" in build_vips
    assert "libsyno[^[:space:]]*\\.so" in build_vips
    assert "add_executable(av-imgdata-image-processor" in cmake
    assert "pkg_check_modules(VIPS REQUIRED vips)" in cmake
    assert "find_library(VIPS_SHARED_LIBRARY" in cmake
    assert "VIPS_DIRECT_RUNTIME_LIBS" in cmake
    assert 'VIPS_LIB MATCHES "^(glib-2.0|gobject-2.0|gio-2.0)$"' in cmake
    assert "find_library(VIPS_DIRECT_${VIPS_LIB_VAR}_LIBRARY" not in cmake
    assert "list(APPEND VIPS_DIRECT_RUNTIME_LIBS ${VIPS_LIB})" in cmake
    vips_library_lookup = cmake.split("find_library(VIPS_SHARED_LIBRARY", 1)[1].split("if(NOT VIPS_SHARED_LIBRARY)", 1)[0]
    assert "PATHS ${VIPS_LIBRARY_DIRS}" in vips_library_lookup
    assert "NO_DEFAULT_PATH" in vips_library_lookup
    assert "libvips direct runtime library not found" not in cmake
    assert "link_directories(${VIPS_LIBRARY_DIRS})" in cmake
    assert "target_link_libraries(av-imgdata-image-processor PRIVATE ${VIPS_SHARED_LIBRARY} ${VIPS_DIRECT_RUNTIME_LIBS})" in cmake
    assert "target_link_libraries(av-imgdata-image-processor PRIVATE ${VIPS_LIBRARIES})" not in cmake
    assert "-Wl,--allow-shlib-undefined" in cmake
    assert "INSTALL_RPATH" in cmake
    assert "backend" in source
    assert "libvips" in source
    assert "vips_ready" in source
    assert "vips_image_new_from_file" in source
    assert 'job.options["colorspace"] = colorspace.empty() ? "srgb" : colorspace' in source
    assert "vips_colourspace(image, &normalized, VIPS_INTERPRETATION_sRGB" in source
    assert "vips_image_get_typeof(image, VIPS_META_ICC_NAME)" in source
    normalizer = source.split("VipsImage* normalize_srgb_for_jpeg", 1)[1].split("\n}\n\nint process_job", 1)[0]
    assert 'vips_image_get_typeof(image, "cicp-transfer-characteristics")' not in normalizer
    assert "CICP image, skipping colourspace conversion" not in source
    assert "CICP image, skipping colour management" not in source
    assert "vips_copy(image, &normalized" not in normalizer
    assert 'vips_icc_transform(image, &normalized, "srgb"' in source
    assert '"embedded", TRUE' in source
    assert '"depth", 8' in source
    assert "vips_image_remove(normalized, VIPS_META_ICC_NAME)" not in source
    assert "0.1.0-skeleton image-backend-vips" not in source
    assert "libvips_not_linked" not in source


def test_native_vips_job_json_parser_does_not_read_later_fields_as_current_value():
    source = Path("processors/native/image_backend_vips/src/main.cpp").read_text(encoding="utf-8")

    string_parser = source.split("std::string json_string_value", 1)[1].split("\n}\n\nstd::string json_object_body", 1)[0]
    int_parser = source.split("int json_int_value", 1)[1].split("\n}\n\nbool json_bool_value", 1)[0]

    assert "body[value_start] != '\"'" in string_parser
    assert 'body.find(\'"\', colon + 1)' not in string_parser
    assert "body[value_start] == '\"'" in int_parser
    assert "std::isdigit(static_cast<unsigned char>(body[value_start]))" in int_parser
    assert 'body.find_first_of("-0123456789", colon + 1)' not in int_parser


def test_synology_install_requires_native_face_processor_libraries():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "ensure_native_face_processor" in install_script
    assert "Native face processor missing; building before package staging." in install_script
    assert "./tools/build-native-face-processor.sh" in install_script
    assert "./tools/smoke-native-face-processor.sh" in install_script
    assert "./tools/functional-native-face-processor.sh" in install_script
    assert "ensure_native_face_processor || return 1" in install_script
    assert "create_install\n\tcreate_spk" in install_script
    assert "./INFO.sh > INFO" in install_script
    assert "native face processor missing" in install_script
    assert "onnxruntime-native" in install_script
    assert "libonnxruntime.so" in install_script
    assert "libjpeg.so" in install_script
    assert "libheif.so" not in install_script
    assert 'cp -av --no-preserve=ownership "$NATIVE_INSTALL/bin/av-imgdata-face-processor" "$package_tgz_dir/bin/"' in install_script
    assert 'cp -av "$NATIVE_INSTALL/lib/."' not in install_script
    assert "find \"$NATIVE_INSTALL/lib\" -maxdepth 1" in install_script
    assert "$NATIVE_INSTALL/share/licenses" in install_script
    assert "Windows external worker face processor missing" in install_script
    assert "Windows external worker checksum manifest missing" in install_script
    assert "Run tools/build-worker.sh --target $target --clean before packaging." in install_script
    assert "external worker face processor missing or not executable" in install_script
    assert 'AV_IMGDATA_PACKAGE_EXTERNAL_WORKERS:-1' in install_script
    assert "Skipping external worker archive packaging because AV_IMGDATA_PACKAGE_EXTERNAL_WORKERS=0." in install_script
    assert 'rm -f "/image/packages/$(pkg_get_spk_family_name)"' in install_script
    assert 'rm -f "/image/packages/${package_name}-"*"-${package_version}"*.spk' not in install_script


def test_synology_install_can_build_missing_vips_processor_before_staging():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert "ensure_vips_image_processor" in install_script
    assert "Optional libvips image processor missing; building before package staging." in install_script
    assert "Existing libvips image processor is stale or unversioned; rebuilding before package staging." in install_script
    assert "av-imgdata-image-processor.build-fingerprint" in install_script
    assert "./tools/build-native-image-processor-vips.sh --print-fingerprint" in install_script
    assert 'current_fingerprint="$(cat "$fingerprint_file" 2>/dev/null || true)"' in install_script
    assert '[ "$current_fingerprint" = "$expected_fingerprint" ]' in install_script
    assert "./tools/build-native-image-processor-vips.sh" in install_script
    assert install_script.index("ensure_vips_image_processor") < install_script.index("VIPS_INSTALL=\"$(native_install_root vips-image-processor-install)\"")


def test_synology_install_accepts_packaged_windows_worker_bundle_path():
    install_script = Path("SynoBuildConf/install").read_text(encoding="utf-8")

    assert '[ "$target" = "windows-x86_64" ] && [ -d "${source_dir}.package" ]' in install_script
    assert 'source_dir="${source_dir}.package"' in install_script
    assert "archive_path=\"$package_tgz_dir/workers/${bundle_name}.zip\"" in install_script


def test_ui_makefile_uses_unquoted_dist_targets_and_utf8_snpm():
    makefile = Path("ui/Makefile").read_text(encoding="utf-8")
    config_define = Path("ui/config.define").read_text(encoding="utf-8")

    assert "JS_DIR=dist" in makefile
    assert "JS_NAMESPACE=SYNO.SDS.App.AV_ImgData" in makefile
    assert "BUNDLE_JS=dist/av-img-data.bundle.js" in makefile
    assert "BUNDLE_CSS=dist/style/av-img-data.bundle.css" in makefile
    assert "APP_JS=AV_ImgData.js" in makefile
    assert "APP_CONFIG_INDEX=config" in makefile
    assert "MAKEFILE_JS_INC=Makefile.js.inc" in makefile
    assert "MODULE_GENERATOR?=/pkgscripts-ng/tool/GenerateModuleFiles.php" in makefile
    assert "AUTO_CONFIG_TOOL?=/usr/local/tool/parse_requires.py" in makefile
    assert "JS_DEPENDER?=/usr/syno/bin/GenerateJSDepend.php" in makefile
    assert 'JS_DIR="dist"' not in makefile
    assert 'BUNDLE_JS="dist/av-img-data.bundle.js"' not in makefile
    assert "PYTHONIOENCODING=utf-8 /usr/local/tool/snpm install" in makefile
    assert "PYTHONIOENCODING=utf-8 /usr/local/tool/snpm run build" in makefile
    assert '"$(MODULE_GENERATOR)" . .' in makefile
    assert "GenerateModuleFiles.php . ." in makefile
    assert '"$(AUTO_CONFIG_TOOL)" --makegoal=JSCompress $(JS_DIR) "$(JS_NAMESPACE)"' in makefile
    assert '"$(JS_DEPENDER)" "$$(pwd)" ""' in makefile
    assert "install -m 644 $(APP_JS) $(INSTALLDIR)/$(APP_JS)" in makefile
    assert "install -m 644 style.css $(INSTALLDIR)/style.css" in makefile
    assert "install -m 644 $(APP_CONFIG_INDEX) $(INSTALLDIR)/$(APP_CONFIG_INDEX)" in makefile
    assert '{"AV_ImgData.js":{"SYNO.SDS.App.AV_ImgData.Instance"' in makefile
    assert '"icon":"images\\\\/icon.png"' in makefile
    assert "packageinstall: $(SUBDIR)" in makefile
    assert '"AV_ImgData.js"' in config_define
    assert '"dist/av-img-data.bundle.js"' in config_define
    assert "$(MAKE) -f $(MAKEFILE_JS_INC) JSCompress" not in makefile
    assert "install_JSCompress" not in makefile
    assert "shrinksafe.php" not in makefile


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


def test_worker_build_generates_and_verifies_third_party_notices():
    build_worker = Path("tools/build-worker.sh").read_text(encoding="utf-8")
    verifier = Path("tools/verify-third-party-licenses.py").read_text(encoding="utf-8")

    assert "verify-third-party-licenses.py" in build_worker
    assert "--root \"${DIST_DIR}\" --write" in build_worker
    assert "THIRD-PARTY-NOTICES.json" in verifier
    assert "bundled native runtime files without license mapping" in verifier
    assert "libstdc\\+\\+-6\\.dll" in verifier
    assert "libvips" in verifier
    assert "onnxruntime" in verifier


def test_package_wrapper_moves_local_artifacts_before_toolkit_link():
    build_package = Path("tools/build-package.sh").read_text(encoding="utf-8")

    assert 'BUILD_EXTERNAL_WORKERS="${AV_IMGDATA_BUILD_EXTERNAL_WORKERS:-1}"' in build_package
    assert "External worker bundles are built by default before the Synology package build:" in build_package
    assert "AV_IMGDATA_PACKAGE_EXTERNAL_WORKERS=0 Skip embedding external worker archives in the DSM package" in build_package
    assert "cleanup_existing_image_packages" in build_package
    assert "info_sh_value" in build_package
    assert 'image_package_dir="${WORKSPACE_ROOT}/build_env/ds.${platform}-${version}/image/packages"' in build_package
    assert 'pattern="${image_package_dir}/${package_title}-*-${package_version}*.spk"' in build_package
    assert 'cleanup_existing_image_packages "$@"' in build_package
    assert 'cleanup_existing_image_packages "${DEFAULT_ARGS[@]}"' in build_package
    assert build_package.index("cleanup_existing_toolkit_link_target") < build_package.index('log "Running structure checks"')
    assert build_package.index("cleanup_existing_image_packages") < build_package.index('log "Running structure checks"')
    assert "sanitize_project_for_toolkit_link" in build_package
    assert "restore_local_build_artifacts" in build_package
    assert "cleanup_stale_generated_backup_roots" in build_package
    assert "configure_noninteractive_linux_worker_vips_build" in build_package
    assert "find_existing_linux_worker_vips_artifact_root" in build_package
    assert "existing_linux_worker_vips_artifact_ready" in build_package
    assert "preserve_existing_linux_worker_vips_artifact" in build_package
    assert "host_linux_worker_vips_build_dependencies_ready" not in build_package
    assert "move_stale_generated_path_out_of_way" in build_package
    assert "prepare_generated_worker_paths" in build_package
    assert "assert_no_nobody_generated_paths" in build_package
    assert "-user nobody -o -group nogroup" in build_package
    assert "build/worker build/native dist worker/native_deps" in build_package
    assert "for rel in build dist worker/native_deps" not in build_package
    assert '"${PACKAGE_ROOT}/.av_imgdata-stale-generated.XXXXXX"' in build_package
    assert '"${PACKAGE_ROOT}"/.av_imgdata-stale-generated.*' in build_package
    assert 'rm -rf "${STALE_GENERATED_BACKUP_ROOT}"' in build_package
    assert "sudo -n true" in build_package
    assert 'AV_IMGDATA_LINUX_CHROOT_ROOT:-${WORKSPACE_ROOT}/build_env/${PACKAGE_NAME}-linux-chroot/linux-x86_64}' in build_package
    assert "export AV_IMGDATA_BUILD_WORKER_VIPS=0" in build_package
    assert "export AV_IMGDATA_VIPS_PROCESSOR_ROOT" in build_package
    assert "export AV_IMGDATA_VIPS_PROCESSOR_BIN" in build_package
    assert "package-worker-vips-artifact" in build_package
    assert "dist/av-imgdata-worker-linux-x86_64" in build_package
    assert "dist/av-imgdata-worker-docker-linux-x86_64" in build_package
    assert "cp -RL --no-preserve=ownership" in build_package
    assert "export AV_IMGDATA_LINUX_CHROOT=0" not in build_package
    assert "Using existing Linux worker libvips artifact because non-interactive sudo is not available" in build_package
    assert "non-interactive sudo is not available" in build_package
    assert "Using host build for Linux worker libvips because non-interactive sudo is not available" not in build_package
    assert "host pkg-config dependencies are incomplete" not in build_package
    assert "libjpeg libpng libtiff-4 libwebp lcms2 zlib" not in build_package
    assert '"build/worker/${target}"' in build_package
    assert '"dist/av-imgdata-worker-${target}"' in build_package
    assert '[[ "${target}" == "windows-x86_64" ]] && continue' in build_package
    assert '"build/native/windows-x86_64/face_processor-build"' not in build_package
    assert "prepare_generated_worker_paths" in build_package.split('log "Building Windows native face processor for external worker bundle"', 1)[0]
    assert "windows_native_deps_ready" in build_package
    assert "ensure_windows_native_deps" in build_package
    assert "linux_native_deps_ready" in build_package
    assert "ensure_linux_native_deps" in build_package
    assert "BUILD_LINUX_FACE_PROCESSOR" in build_package
    assert "AV_IMGDATA_BUILD_LINUX_FACE_PROCESSOR:-1" in build_package
    assert "target_list_contains_linux_face_worker" in build_package
    assert "build_linux_face_processor_for_worker_bundle" in build_package
    assert "tools/build-native-face-processor-linux.sh" in build_package
    assert "--no-fetch-deps --no-update-check" in build_package
    assert "worker_face_processor_path" in build_package
    assert "assert_worker_face_processor_bundled" in build_package
    assert "External worker bundle is incomplete: missing executable face processor" in build_package
    assert "tools/fetch-worker-native-deps.sh --target linux-x86_64 --no-update-check" in build_package
    assert "ensure_linux_native_deps" in build_package.split("build_external_worker_bundles", 1)[0]
    assert "build_linux_face_processor_for_worker_bundle" in build_package.split('log "Building Windows native face processor for external worker bundle"', 1)[0]
    assert "assert_worker_face_processor_bundled" in build_package.split('log "External worker bundles built: ${EXTERNAL_WORKER_TARGETS}"', 1)[0]
    assert "run_pkgcreate" in build_package
    assert "assert_pkgcreate_log_has_no_critical_errors" in build_package
    assert "PkgCreate.py returned success" in build_package
    assert "AV_IMGDATA_NATIVE_FETCH_DEPS=0 python3 \"${PKGCREATE}\"" in build_package
    assert "sudo -n true" in build_package
    assert "[[ -t 0 ]]" in build_package
    assert "sudo env AV_IMGDATA_NATIVE_FETCH_DEPS=0 python3 \"${PKGCREATE}\"" in build_package
    assert "PkgCreate.py failed; preserved PkgCreate output log:" in build_package
    assert "rm -f \"${pkgcreate_log}\"\n      fail \"PkgCreate.py failed" not in build_package
    assert "PkgCreate.py requires root privileges for the Synology Toolkit chroot step" in build_package
    assert "tee \"${pkgcreate_log}\"" in build_package
    assert "ERROR: (native|optional|external worker|Windows external worker|ui/index.cgi|libjpeg|ONNXRuntime|duplicate package runtime library SONAMEs)" in build_package
    assert "duplicate package runtime library SONAMEs" in build_package
    assert "tools/fetch-worker-windows-deps.sh" in build_package
    assert 'onnxruntime/include/onnxruntime_c_api.h' in build_package
    assert 'jpeg/include/jpeglib.h' in build_package
    assert "AV_IMGDATA_FACE_PROCESSOR_WINDOWS_BUILD_ROOT" in build_package
    assert "av-imgdata-face-processor-windows-x86_64.package" in build_package
    assert "AV_IMGDATA_WORKER_BUILD_DIR" in build_package
    assert "AV_IMGDATA_WORKER_DIST_DIR" in build_package
    assert "av-imgdata-worker-windows-x86_64.package" in build_package
    assert "ensure_windows_native_deps" in build_package.split('log "Building Windows native face processor for external worker bundle"', 1)[0]
    assert '".test-venv"' in build_package
    assert '"build"' not in build_package
    assert '"build/chroot/*"' in build_package
    assert "SANITIZE_NATIVE_BUILD_PATTERNS" in build_package
    assert "cleanup_existing_toolkit_link_target" in build_package
    assert "PYTHONDONTWRITEBYTECODE=1" in build_package
    assert 'target="${WORKSPACE_ROOT}/build_env/ds.${platform}-${version}/source/${PACKAGE_NAME}"' in build_package
    assert '[[ -e "${target}" ]] || return 0' in build_package
    assert "Removing Toolkit link target with sudo because it contains files owned by another user" in build_package
    assert "sudo rm -rf \"${target}\"" in build_package
    assert "Suggested cleanup:" in build_package
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
    assert '"src/av_imgdata/__pycache__"' in build_package
    assert '"src/av_imgdata/db/__pycache__"' in build_package
    assert 'mktemp -d "${PACKAGE_ROOT}/../.av_imgdata-link-sanitize.XXXXXX"' in build_package
    assert "sanitize_project_for_toolkit_link" in build_package.split('log "Building Synology package"', 1)[0]
    assert "assert_no_nobody_generated_paths" in build_package.split("build_external_worker_bundles", 1)[0]
    assert "assert_no_nobody_generated_paths" in build_package.split('log "Temporarily moving local build artifacts out of the Toolkit link tree"', 1)[0]

    build_worker = Path("tools/build-worker.sh").read_text(encoding="utf-8")
    assert '"${PROJECT_DIR}/dist/av-imgdata-worker-docker-linux-x86_64/bin/${target_binary_name}"' in build_worker


def test_package_info_is_platform_specific_for_native_binary():
    info_script = Path("INFO.sh").read_text(encoding="utf-8")

    assert 'arch="$(pkg_get_platform)"' in info_script
    assert 'arch="noarch"' not in info_script


def test_build_packaging_copies_do_not_preserve_source_ownership():
    checked_files = [
        Path("SynoBuildConf/install"),
        Path("tools/build-native-face-processor-linux.sh"),
        Path("tools/build-native-face-processor-windows.sh"),
        Path("tools/build-native-face-processor.sh"),
        Path("tools/build-native-image-processor-vips.sh"),
        Path("tools/build-native-image-processor-vips-windows.sh"),
        Path("tools/build-worker.sh"),
        Path("tools/fetch-worker-windows-deps.sh"),
        Path("tools/fetch-worker-native-deps.sh"),
    ]

    offenders = []
    archive_copy = re.compile(r"\bcp\s+-a\S*")
    for path in checked_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if archive_copy.search(line) and "--no-preserve=ownership" not in line:
                offenders.append(f"{path}:{lineno}: {line.strip()}")

    assert offenders == []
