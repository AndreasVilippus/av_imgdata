#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
BUILD_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}"
BUILD_DIR="${BUILD_ROOT}/face_processor-build"
INSTALL_DIR="${BUILD_ROOT}/face_processor-install"

rm -rf "${BUILD_DIR}" "${INSTALL_DIR}"
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

cd "${BUILD_DIR}"
CMAKE_ARGS=(
  "${PROJECT_DIR}/processors/native/face_processor"
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

if [ -n "${STRIP:-}" ] && [ -x "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" ]; then
  "${STRIP}" "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" || true
fi

if [ ! -x "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" ]; then
  echo "ERROR: native face processor build did not produce an executable binary."
  exit 1
fi
