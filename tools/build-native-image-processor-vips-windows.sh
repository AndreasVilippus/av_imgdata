#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="windows-x86_64"
DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
BUILD_ROOT="${PROJECT_DIR}/build/native/${TARGET}"
BUILD_DIR="${BUILD_ROOT}/vips-image-processor-build"
INSTALL_DIR="${BUILD_ROOT}/vips-image-processor-install"
DIST_DIR="${PROJECT_DIR}/dist/av-imgdata-image-processor-${TARGET}"
VIPS_ROOT="${VIPS_ROOT:-${DEPS_ROOT}/vips}"
MXE_BUILD_ROOT="${AV_IMGDATA_WINDOWS_VIPS_BUILD_ROOT:-${BUILD_ROOT}/libvips-win64-mxe}"
MXE_REPO_URL="${AV_IMGDATA_WINDOWS_VIPS_REPO_URL:-https://github.com/libvips/build-win64-mxe.git}"
MXE_REPO_TAG="${AV_IMGDATA_WINDOWS_VIPS_REPO_TAG:-v8.16.1}"
MXE_TMPDIR="${AV_IMGDATA_WINDOWS_VIPS_TMPDIR:-${BUILD_ROOT}/mxe-tmp}"
MXE_PODMAN_RUNTIME_DIR="${AV_IMGDATA_WINDOWS_VIPS_PODMAN_RUNTIME_DIR:-}"
MXE_PODMAN_HOME="${AV_IMGDATA_WINDOWS_VIPS_PODMAN_HOME:-}"
MXE_CONTAINER_USER_ARGS="${AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS:--u $(id -u):$(id -g)}"
MXE_BUILD_ARGS="${AV_IMGDATA_WINDOWS_VIPS_BUILD_ARGS:---tmpdir ${MXE_TMPDIR} avimgdata --with-jpeg-turbo --without-llvm}"
CLEAN=0

usage() {
  cat <<'EOF'
Usage: tools/build-native-image-processor-vips-windows.sh [options]

Options:
  --clean        Remove build, install, and dist directories before building
  -h, --help     Show this help

Environment overrides:
  VIPS_ROOT                         Output Windows libvips root. Default: worker/native_deps/windows-x86_64/vips.
  AV_IMGDATA_WINDOWS_VIPS_BUILD_ROOT
                                    build-win64-mxe checkout/build root. Default: build/native/windows-x86_64/libvips-win64-mxe.
  AV_IMGDATA_WINDOWS_VIPS_REPO_URL  Default: https://github.com/libvips/build-win64-mxe.git
  AV_IMGDATA_WINDOWS_VIPS_REPO_TAG  Default: v8.16.1
  AV_IMGDATA_WINDOWS_VIPS_TMPDIR
                                    Default: build/native/windows-x86_64/mxe-tmp
  AV_IMGDATA_WINDOWS_VIPS_PODMAN_RUNTIME_DIR
                                    Optional Podman XDG_RUNTIME_DIR override.
  AV_IMGDATA_WINDOWS_VIPS_PODMAN_HOME
                                    Optional Podman HOME/XDG_DATA_HOME override.
  AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS
                                    Optional container user args. Default: -u <current uid>:<current gid>.
  AV_IMGDATA_WINDOWS_VIPS_BUILD_ARGS
                                    Default: --tmpdir <repo build tmpdir> avimgdata --with-jpeg-turbo --without-llvm
  PKG_CONFIG     Optional. Defaults to x86_64-w64-mingw32-pkg-config or pkg-config.
  CC             Optional. Defaults to x86_64-w64-mingw32-gcc.
  CXX            Optional. Defaults to x86_64-w64-mingw32-g++.
  STRIP          Optional. Defaults to x86_64-w64-mingw32-strip.

Output:
  dist/av-imgdata-image-processor-windows-x86_64/bin/av-imgdata-image-processor.exe
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --clean)
      CLEAN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $1" >&2
    exit 1
  fi
}

copy_matching_files() {
  local source_dir="$1"
  local target_dir="$2"
  shift 2
  local pattern
  local source
  [ -d "${source_dir}" ] || return 0
  mkdir -p "${target_dir}"
  for pattern in "$@"; do
    for source in "${source_dir}"/${pattern}; do
      [ -e "${source}" ] || continue
      cp -L "${source}" "${target_dir}/"
    done
  done
}

copy_dir_if_exists() {
  local source="$1"
  local target="$2"
  if [ -d "${source}" ]; then
    mkdir -p "${target}"
    cp -a --no-preserve=ownership "${source}/." "${target}/"
  fi
}

select_pkg_config() {
  if [ -n "${PKG_CONFIG:-}" ]; then
    require_command "${PKG_CONFIG}"
    return
  fi
  if command -v x86_64-w64-mingw32-pkg-config >/dev/null 2>&1; then
    PKG_CONFIG=x86_64-w64-mingw32-pkg-config
  else
    PKG_CONFIG=pkg-config
  fi
  require_command "${PKG_CONFIG}"
}

write_avimgdata_mxe_profile() {
  local build_dir="${MXE_BUILD_ROOT}/build"
  local profile="${build_dir}/vips-avimgdata.mk"
  local overrides="${build_dir}/overrides.mk"
  local libde265_source="${build_dir}/plugins/hevc/libde265.mk"
  local libde265_target="${build_dir}/libde265.mk"

  if [ ! -f "${libde265_source}" ]; then
    echo "ERROR: build-win64-mxe libde265 recipe not found: ${libde265_source}" >&2
    exit 1
  fi

  cp -f "${libde265_source}" "${libde265_target}"
  cat >"${profile}" <<'PROFILE_EOF'
PKG             := vips-avimgdata
$(PKG)_WEBSITE  := https://libvips.github.io/libvips/
$(PKG)_DESCR    := AV_ImgData reduced libvips build for worker image decoding.
$(PKG)_IGNORE   :=
$(PKG)_VERSION  := 8.16.1
$(PKG)_CHECKSUM := d114d7c132ec5b45f116d654e17bb4af84561e3041183cd4bfd79abfb85cf724
$(PKG)_PATCHES  := $(realpath $(sort $(wildcard $(dir $(lastword $(MAKEFILE_LIST)))/patches/vips-[0-9]*.patch)))
$(PKG)_GH_CONF  := libvips/libvips/releases,v,,,,.tar.xz
$(PKG)_SUBDIR   := vips-$($(PKG)_VERSION)
$(PKG)_FILE     := vips-$($(PKG)_VERSION).tar.xz
$(PKG)_DEPS     := cc meson-wrapper libwebp glib expat libjpeg-turbo tiff lcms \
                   libheif libde265 libpng libspng highway cgif zlib

define $(PKG)_PRE_CONFIGURE
    mkdir -p $(PREFIX)/$(TARGET)/vips-packaging
    $(foreach f, ChangeLog LICENSE README.md, \
        cp '$(SOURCE_DIR)/$(f)' '$(PREFIX)/$(TARGET)/vips-packaging';)

    (printf '{\n'; \
     printf '  "cgif": "$(cgif_VERSION)",\n'; \
     printf '  "de265": "$(libde265_VERSION)",\n'; \
     printf '  "expat": "$(expat_VERSION)",\n'; \
     printf '  "glib": "$(glib_VERSION)",\n'; \
     printf '  "heif": "$(libheif_VERSION)",\n'; \
     printf '  "highway": "$(highway_VERSION)",\n'; \
     $(if $(IS_JPEGLI), \
          printf '  "jpegli": "$(jpegli_VERSION)"$(comma)\n';, \
          $(if $(IS_MOZJPEG),,printf '  "jpeg": "$(libjpeg-turbo_VERSION)"$(comma)\n';)) \
     printf '  "lcms": "$(lcms_VERSION)",\n'; \
     $(if $(IS_MOZJPEG),printf '  "mozjpeg": "$(mozjpeg_VERSION)"$(comma)\n';) \
     printf '  "png": "$(libpng_VERSION)",\n'; \
     printf '  "spng": "$(libspng_VERSION)",\n'; \
     printf '  "tiff": "$(tiff_VERSION)",\n'; \
     printf '  "vips": "$(vips-avimgdata_VERSION)",\n'; \
     printf '  "webp": "$(libwebp_VERSION)",\n'; \
     $(if $(IS_ZLIB_NG), \
          printf '  "zlib-ng": "$(zlib-ng_VERSION)"\n';, \
          printf '  "zlib": "$(zlib_VERSION)"\n';) \
     printf '}';) \
     > '$(PREFIX)/$(TARGET)/vips-packaging/versions.json'
endef

define $(PKG)_BUILD
    $($(PKG)_PRE_CONFIGURE)

    $(eval export CFLAGS += -O3)
    $(eval export CXXFLAGS += -O3)

    $(MXE_MESON_WRAPPER) \
        --default-library=shared \
        -Ddeprecated=false \
        -Dexamples=false \
        -Dintrospection=disabled \
        -Dmodules=disabled \
        -Darchive=disabled \
        -Dcfitsio=disabled \
        -Dcplusplus=false \
        -Dexif=disabled \
        -Dfftw=disabled \
        -Dfontconfig=disabled \
        -Dheif=enabled \
        -Djpeg=enabled \
        -Djpeg-xl=disabled \
        -Dlcms=enabled \
        -Dmagick=disabled \
        -Dmatio=disabled \
        -Dnifti=disabled \
        -Dopenexr=disabled \
        -Dopenjpeg=disabled \
        -Dopenslide=disabled \
        -Dorc=disabled \
        -Dpangocairo=disabled \
        -Dpdfium=disabled \
        -Dpng=enabled \
        -Dpoppler=disabled \
        -Dquantizr=disabled \
        -Drsvg=disabled \
        -Dtiff=enabled \
        -Dwebp=enabled \
        -Dzlib=enabled \
        -Dnsgif=false \
        -Dppm=false \
        -Danalyze=false \
        -Dradiance=false \
        '$(SOURCE_DIR)' \
        '$(BUILD_DIR)'

    $(MXE_NINJA) -C '$(BUILD_DIR)' -j '$(JOBS)' install
endef
PROFILE_EOF

  if ! grep -q "AV_ImgData reduced libheif override" "${overrides}"; then
    cat >>"${overrides}" <<'OVERRIDE_EOF'

# AV_ImgData reduced libheif override: enable HEIC decoding via libde265 without x265/GPL encoder.
libheif_DEPS := $(libheif_DEPS) libde265

define libheif_BUILD
    $(eval export CFLAGS += -O3)
    $(eval export CXXFLAGS += -O3)

    cd '$(BUILD_DIR)' && $(TARGET)-cmake \
        -DENABLE_PLUGIN_LOADING=0 \
        -DBUILD_TESTING=0 \
        -DWITH_EXAMPLES=0 \
        -DWITH_LIBDE265=1 \
        -DWITH_X265=0 \
        $(if $(and $(IS_JPEGLI),$(BUILD_STATIC)), -DCMAKE_CXX_FLAGS='$(CXXFLAGS) -DHAVE_JPEG_WRITE_ICC_PROFILE') \
        '$(SOURCE_DIR)'
    $(MAKE) -C '$(BUILD_DIR)' -j '$(JOBS)'
    $(MAKE) -C '$(BUILD_DIR)' -j 1 $(subst -,/,$(INSTALL_STRIP_LIB))
endef
OVERRIDE_EOF
  elif ! grep -q 'libheif_DEPS := $(libheif_DEPS) libde265' "${overrides}"; then
    sed -i '/AV_ImgData reduced libheif override/a libheif_DEPS := $(libheif_DEPS) libde265' "${overrides}"
  fi
}

patch_build_win64_mxe_runner() {
  local runner="${MXE_BUILD_ROOT}/build.sh"

  if grep -q -- '-u $(id -u):$(id -g)' "${runner}"; then
    sed -i 's/  -u $(id -u):$(id -g) \\/  ${AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS} \\/' "${runner}"
  fi
}

find_built_vips_root() {
  local candidate
  for candidate in \
    "${MXE_BUILD_ROOT}"/vips-dev-w64-* \
    "${MXE_BUILD_ROOT}"/vips-dev-x64-* \
    "${MXE_BUILD_ROOT}"/vips-dev-* \
    "${MXE_BUILD_ROOT}"/build/vips-dev-w64-* \
    "${MXE_BUILD_ROOT}"/build/vips-dev-x64-* \
    "${MXE_BUILD_ROOT}"/build/vips-dev-* \
    "${MXE_BUILD_ROOT}"/dist/vips-dev-w64-* \
    "${MXE_BUILD_ROOT}"/dist/vips-dev-x64-* \
    "${MXE_BUILD_ROOT}"/dist/vips-dev-* \
    "${MXE_BUILD_ROOT}"/build/mxe/usr/x86_64-w64-mingw32.shared.win32.avimgdata; do
    if [ -f "${candidate}/lib/pkgconfig/vips.pc" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

find_built_vips_zip() {
  local candidate
  for candidate in \
    "${MXE_BUILD_ROOT}"/vips-dev-w64-*.zip \
    "${MXE_BUILD_ROOT}"/vips-dev-x64-*.zip \
    "${MXE_BUILD_ROOT}"/build/vips-dev-w64-*.zip \
    "${MXE_BUILD_ROOT}"/build/vips-dev-x64-*.zip \
    "${MXE_BUILD_ROOT}"/dist/vips-dev-w64-*.zip \
    "${MXE_BUILD_ROOT}"/dist/vips-dev-x64-*.zip; do
    if [ -f "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

extract_built_vips_zip() {
  local zip_path="$1"
  local extract_root="${BUILD_ROOT}/vips-dev-extracted"

  rm -rf "${extract_root}"
  mkdir -p "${extract_root}"
  unzip -q "${zip_path}" -d "${extract_root}"

  local candidate
  for candidate in \
    "${extract_root}" \
    "${extract_root}"/vips-dev-w64-* \
    "${extract_root}"/vips-dev-x64-* \
    "${extract_root}"/*/vips-dev-w64-* \
    "${extract_root}"/*/vips-dev-x64-*; do
    if [ -f "${candidate}/lib/pkgconfig/vips.pc" ]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

install_built_vips_root() {
  local built_root="$1"
  rm -rf "${VIPS_ROOT}"
  mkdir -p "$(dirname "${VIPS_ROOT}")"
  cp -a --no-preserve=ownership "${built_root}" "${VIPS_ROOT}"
  normalize_vips_pkgconfig_prefix
}

normalize_vips_pkgconfig_prefix() {
  local pc_file
  [ -d "${VIPS_ROOT}/lib/pkgconfig" ] || return 0
  for pc_file in "${VIPS_ROOT}"/lib/pkgconfig/*.pc; do
    [ -f "${pc_file}" ] || continue
    sed -i "s|^prefix=.*|prefix=${VIPS_ROOT}|" "${pc_file}"
  done
}

ensure_vips_root() {
  if [ -f "${VIPS_ROOT}/lib/pkgconfig/vips.pc" ]; then
    normalize_vips_pkgconfig_prefix
    return 0
  fi

  require_command git
  require_command unzip
  require_command make

  mkdir -p "$(dirname "${MXE_BUILD_ROOT}")"
  if [ ! -d "${MXE_BUILD_ROOT}/.git" ]; then
    git clone --depth 1 --branch "${MXE_REPO_TAG}" "${MXE_REPO_URL}" "${MXE_BUILD_ROOT}"
  fi
  write_avimgdata_mxe_profile
  patch_build_win64_mxe_runner

  echo "Building Windows libvips with build-win64-mxe: ${MXE_REPO_TAG}"
  mkdir -p "${MXE_TMPDIR}"
  if ! (
    cd "${MXE_BUILD_ROOT}"
    if [ -n "${MXE_PODMAN_HOME}" ]; then
      mkdir -p "${MXE_PODMAN_HOME}/.local/share"
      export HOME="${MXE_PODMAN_HOME}"
      export XDG_DATA_HOME="${MXE_PODMAN_HOME}/.local/share"
    fi
    if [ -n "${MXE_PODMAN_RUNTIME_DIR}" ]; then
      mkdir -p "${MXE_PODMAN_RUNTIME_DIR}"
      chmod 700 "${MXE_PODMAN_RUNTIME_DIR}" || true
      export XDG_RUNTIME_DIR="${MXE_PODMAN_RUNTIME_DIR}"
    fi
    export AV_IMGDATA_WINDOWS_VIPS_CONTAINER_USER_ARGS="${MXE_CONTAINER_USER_ARGS}"
    ./build.sh ${MXE_BUILD_ARGS}
  ); then
    if find_built_vips_root >/dev/null; then
      echo "WARNING: build-win64-mxe packaging failed, but a usable Windows libvips root was produced; continuing." >&2
    else
      return 1
    fi
  fi

  local built_root
  if ! built_root="$(find_built_vips_root)"; then
    local built_zip
    if built_zip="$(find_built_vips_zip)"; then
      echo "Extracting Windows libvips artifact: ${built_zip}"
      if ! built_root="$(extract_built_vips_zip "${built_zip}")"; then
        echo "ERROR: ${built_zip} does not contain a Windows libvips root with lib/pkgconfig/vips.pc" >&2
        exit 1
      fi
    else
      echo "ERROR: build-win64-mxe did not produce a Windows libvips root or vips-dev zip below ${MXE_BUILD_ROOT}" >&2
      echo "       Check the build output and AV_IMGDATA_WINDOWS_VIPS_BUILD_ARGS." >&2
      exit 1
    fi
  fi
  install_built_vips_root "${built_root}"

  if [ ! -f "${VIPS_ROOT}/lib/pkgconfig/vips.pc" ]; then
    echo "ERROR: Windows libvips build did not install ${VIPS_ROOT}/lib/pkgconfig/vips.pc" >&2
    exit 1
  fi
}

copy_mingw_runtime_file() {
  local dll_name="$1"
  local target_dir="$2"
  local compiler="${CXX:-x86_64-w64-mingw32-g++}"
  local resolved=""

  if command -v "${compiler}" >/dev/null 2>&1; then
    resolved="$(${compiler} -print-file-name="${dll_name}" 2>/dev/null || true)"
    if [ -n "${resolved}" ] && [ "${resolved}" != "${dll_name}" ] && [ -f "${resolved}" ]; then
      cp -L "${resolved}" "${target_dir}/"
      return 0
    fi
  fi
  return 1
}

strip_native_binary() {
  local binary="$1"
  local strip_tool="${STRIP:-x86_64-w64-mingw32-strip}"
  if ! command -v "${strip_tool}" >/dev/null 2>&1; then
    echo "WARNING: strip tool not found: ${strip_tool}; native binary remains unstripped." >&2
    return
  fi
  "${strip_tool}" --strip-unneeded "${binary}" || "${strip_tool}" "${binary}" || true
}

if [ "${CLEAN}" = "1" ]; then
  rm -rf "${BUILD_DIR}" "${INSTALL_DIR}" "${DIST_DIR}" "${VIPS_ROOT}"
fi

require_command cmake
require_command x86_64-w64-mingw32-gcc
require_command x86_64-w64-mingw32-g++
ensure_vips_root
select_pkg_config
rm -rf "${BUILD_DIR}"

export CC="${CC:-x86_64-w64-mingw32-gcc}"
export CXX="${CXX:-x86_64-w64-mingw32-g++}"
export PKG_CONFIG
export PKG_CONFIG_PATH="${VIPS_ROOT}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"

cmake \
  -S "${PROJECT_DIR}/processors/native/image_backend_vips" \
  -B "${BUILD_DIR}" \
  -DCMAKE_TOOLCHAIN_FILE="${PROJECT_DIR}/worker/cmake/toolchains/windows-mingw-x86_64.cmake" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData
cmake --build "${BUILD_DIR}" --parallel "$(nproc 2>/dev/null || echo 2)"
cmake --install "${BUILD_DIR}" --prefix "${INSTALL_DIR}/usr/local/AV_ImgData"

mkdir -p "${DIST_DIR}/bin"
cp -L "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-image-processor.exe" "${DIST_DIR}/bin/"
copy_matching_files "${VIPS_ROOT}/bin" "${DIST_DIR}/bin" "*.dll" "*.DLL"
copy_matching_files "${VIPS_ROOT}/lib" "${DIST_DIR}/bin" "*.dll" "*.DLL"
copy_dir_if_exists "${VIPS_ROOT}/share/licenses" "${DIST_DIR}/share/licenses"
copy_dir_if_exists "${VIPS_ROOT}/share/doc" "${DIST_DIR}/share/doc"
copy_mingw_runtime_file "libgcc_s_seh-1.dll" "${DIST_DIR}/bin" || true
copy_mingw_runtime_file "libstdc++-6.dll" "${DIST_DIR}/bin" || true
copy_mingw_runtime_file "libwinpthread-1.dll" "${DIST_DIR}/bin" || true

if [ "${AV_IMGDATA_NATIVE_STRIP:-1}" != "0" ]; then
  strip_native_binary "${DIST_DIR}/bin/av-imgdata-image-processor.exe"
fi

mkdir -p "${INSTALL_DIR}/usr/local/AV_ImgData"
cp -a --no-preserve=ownership "${DIST_DIR}/bin" "${INSTALL_DIR}/usr/local/AV_ImgData/"
copy_dir_if_exists "${DIST_DIR}/share" "${INSTALL_DIR}/usr/local/AV_ImgData/share"

echo "Windows libvips image processor built: ${DIST_DIR}/bin/av-imgdata-image-processor.exe"
