#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
BUILD_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}"
BUILD_DIR="${BUILD_ROOT}/vips-image-processor-build"
INSTALL_DIR="${BUILD_ROOT}/vips-image-processor-install"

rm -rf "${BUILD_DIR}" "${INSTALL_DIR}"
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

cd "${BUILD_DIR}"
CMAKE_ARGS=(
  "${PROJECT_DIR}/processors/native/image_backend_vips"
  "-DCMAKE_BUILD_TYPE=Release"
  "-DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData"
)
if [ -n "${CC:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_C_COMPILER=${CC}")
fi
if [ -n "${CXX:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=${CXX}")
fi
cmake "${CMAKE_ARGS[@]}"
make -j"$(nproc 2>/dev/null || echo 2)"
make install DESTDIR="${INSTALL_DIR}"

NATIVE_BINARY="${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-image-processor"
if [ "${AV_IMGDATA_NATIVE_STRIP:-1}" != "0" ] && [ -x "${NATIVE_BINARY}" ]; then
  STRIP_TOOL="${STRIP:-strip}"
  if command -v "${STRIP_TOOL}" >/dev/null 2>&1; then
    "${STRIP_TOOL}" --strip-unneeded "${NATIVE_BINARY}" || "${STRIP_TOOL}" "${NATIVE_BINARY}" || true
  fi
fi

if [ ! -x "${NATIVE_BINARY}" ]; then
  echo "ERROR: optional libvips image processor build did not produce an executable binary."
  exit 1
fi
