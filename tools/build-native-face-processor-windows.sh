#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="windows-x86_64"
DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
BUILD_DIR="${PROJECT_DIR}/build/native/${TARGET}/face_processor-build"
INSTALL_DIR="${PROJECT_DIR}/build/native/${TARGET}/face_processor-install"
DIST_DIR="${PROJECT_DIR}/dist/av-imgdata-face-processor-${TARGET}"
CLEAN=0

usage() {
  cat <<'EOF'
Usage: tools/build-native-face-processor-windows.sh [options]

Options:
  --clean        Remove build, install, and dist directories before building
  -h, --help     Show this help

Dependency defaults:
  worker/native_deps/windows-x86_64/onnxruntime
  worker/native_deps/windows-x86_64/jpeg
  worker/native_deps/windows-x86_64/heif       optional

Environment overrides:
  ONNXRUNTIME_ROOT   Optional. Windows ONNXRuntime C API root containing include/ and lib/ or bin/.
  JPEG_ROOT          Optional. Windows JPEG/libjpeg root containing include/ and lib/ or bin/.
  HEIF_ROOT          Optional. Windows libheif root containing include/libheif/heif.h.
  CC                 Optional. Defaults to x86_64-w64-mingw32-gcc.
  CXX                Optional. Defaults to x86_64-w64-mingw32-g++.
  STRIP              Optional. Defaults to x86_64-w64-mingw32-strip.

Output:
  dist/av-imgdata-face-processor-windows-x86_64/bin/av-imgdata-face-processor.exe
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

require_file() {
  if [ ! -f "$1" ]; then
    echo "ERROR: required file not found: $1" >&2
    exit 1
  fi
}

require_dir() {
  if [ ! -d "$1" ]; then
    echo "ERROR: required directory not found: $1" >&2
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
      cp -aL "${source}" "${target_dir}/"
    done
  done
}

copy_optional_license_file() {
  local source="$1"
  local target="$2"
  if [ -f "${source}" ]; then
    mkdir -p "$(dirname "${target}")"
    cp -a "${source}" "${target}"
  fi
}

resolve_deps() {
  if [ -z "${ONNXRUNTIME_ROOT:-}" ]; then
    if [ -d "${DEPS_ROOT}/onnxruntime" ]; then
      ONNXRUNTIME_ROOT="${DEPS_ROOT}/onnxruntime"
    fi
  fi
  if [ -z "${JPEG_ROOT:-}" ]; then
    if [ -d "${DEPS_ROOT}/jpeg" ]; then
      JPEG_ROOT="${DEPS_ROOT}/jpeg"
    elif [ -d "${DEPS_ROOT}/libjpeg" ]; then
      JPEG_ROOT="${DEPS_ROOT}/libjpeg"
    elif [ -d "${DEPS_ROOT}/libjpeg-turbo" ]; then
      JPEG_ROOT="${DEPS_ROOT}/libjpeg-turbo"
    fi
  fi
  if [ -z "${HEIF_ROOT:-}" ] && [ -d "${DEPS_ROOT}/heif" ]; then
    HEIF_ROOT="${DEPS_ROOT}/heif"
  fi
}

resolve_deps

if [ -z "${ONNXRUNTIME_ROOT:-}" ]; then
  echo "ERROR: ONNXRUNTIME_ROOT is required for the Windows face processor build." >&2
  echo "       Expected default: ${DEPS_ROOT}/onnxruntime" >&2
  exit 1
fi
if [ -z "${JPEG_ROOT:-}" ]; then
  echo "ERROR: JPEG_ROOT is required for the Windows face processor build." >&2
  echo "       Expected default: ${DEPS_ROOT}/jpeg" >&2
  exit 1
fi

require_command cmake
require_command "${CC:-x86_64-w64-mingw32-gcc}"
require_command "${CXX:-x86_64-w64-mingw32-g++}"

require_dir "${ONNXRUNTIME_ROOT}/include"
require_dir "${JPEG_ROOT}/include"
require_file "${ONNXRUNTIME_ROOT}/include/onnxruntime_c_api.h"
require_file "${JPEG_ROOT}/include/jpeglib.h"

if [ "${CLEAN}" = "1" ]; then
  rm -rf "${BUILD_DIR}" "${INSTALL_DIR}" "${DIST_DIR}"
fi
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}" "${DIST_DIR}"

CMAKE_ARGS=(
  -S "${PROJECT_DIR}/processors/native/face_processor"
  -B "${BUILD_DIR}"
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData
  -DCMAKE_SYSTEM_NAME=Windows
  -DCMAKE_C_COMPILER="${CC:-x86_64-w64-mingw32-gcc}"
  -DCMAKE_CXX_COMPILER="${CXX:-x86_64-w64-mingw32-g++}"
  -DONNXRUNTIME_ROOT="${ONNXRUNTIME_ROOT}"
  -DJPEG_ROOT="${JPEG_ROOT}"
)

if command -v ninja >/dev/null 2>&1; then
  CMAKE_ARGS+=(-G Ninja)
fi
if [ -n "${HEIF_ROOT:-}" ]; then
  CMAKE_ARGS+=(-DHEIF_ROOT="${HEIF_ROOT}")
fi

cmake "${CMAKE_ARGS[@]}"
cmake --build "${BUILD_DIR}"
cmake --install "${BUILD_DIR}" --prefix /usr/local/AV_ImgData --strip -- DESTDIR="${INSTALL_DIR}" 2>/dev/null || cmake --install "${BUILD_DIR}" --prefix /usr/local/AV_ImgData -- DESTDIR="${INSTALL_DIR}"

NATIVE_BINARY="${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor.exe"
if [ ! -f "${NATIVE_BINARY}" ]; then
  echo "ERROR: Windows face processor build did not produce ${NATIVE_BINARY}" >&2
  exit 1
fi

if [ "${AV_IMGDATA_NATIVE_STRIP:-1}" != "0" ]; then
  STRIP_TOOL="${STRIP:-x86_64-w64-mingw32-strip}"
  if command -v "${STRIP_TOOL}" >/dev/null 2>&1; then
    "${STRIP_TOOL}" --strip-unneeded "${NATIVE_BINARY}" || true
  else
    echo "WARNING: strip tool not found: ${STRIP_TOOL}; native binary remains unstripped." >&2
  fi
fi

mkdir -p "${DIST_DIR}/bin" "${DIST_DIR}/lib" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor"
cp -a "${NATIVE_BINARY}" "${DIST_DIR}/bin/av-imgdata-face-processor.exe"

copy_matching_files "${ONNXRUNTIME_ROOT}/lib" "${DIST_DIR}/lib" "onnxruntime.dll" "onnxruntime*.dll" "*.dll"
copy_matching_files "${ONNXRUNTIME_ROOT}/bin" "${DIST_DIR}/bin" "onnxruntime.dll" "onnxruntime*.dll" "*.dll"
copy_matching_files "${JPEG_ROOT}/bin" "${DIST_DIR}/bin" "*.dll"
copy_matching_files "${JPEG_ROOT}/lib" "${DIST_DIR}/lib" "*.dll" "libjpeg*.a" "jpeg*.a"

cat > "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/README.txt" <<EOF
AV_ImgData Windows native face processor bundle.

Bundled runtime libraries may include:
- ONNXRuntime from ONNXRUNTIME_ROOT=${ONNXRUNTIME_ROOT}
- JPEG/libjpeg runtime from JPEG_ROOT=${JPEG_ROOT}
EOF
copy_optional_license_file "${ONNXRUNTIME_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.LICENSE"
copy_optional_license_file "${ONNXRUNTIME_ROOT}/ThirdPartyNotices.txt" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.ThirdPartyNotices.txt"
copy_optional_license_file "${JPEG_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/jpeg.LICENSE"
copy_optional_license_file "${JPEG_ROOT}/share/licenses/libjpeg-turbo/LICENSE.md" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libjpeg-turbo.LICENSE.md"

cat > "${DIST_DIR}/README.txt" <<'README_EOF'
AV_ImgData Windows native face processor bundle.

Use with worker bundling:
  AV_IMGDATA_FACE_PROCESSOR_BIN=dist/av-imgdata-face-processor-windows-x86_64/bin/av-imgdata-face-processor.exe \
  AV_IMGDATA_FACE_PROCESSOR_ROOT=dist/av-imgdata-face-processor-windows-x86_64 \
  bash tools/build-worker.sh --target windows-x86_64 --clean

Runtime model files are not included. Put InsightFace model files into the worker bundle under:
  models/buffalo_l/det_10g.onnx
  models/buffalo_l/w600k_r50.onnx
README_EOF

echo "Windows native face processor build completed: ${DIST_DIR}"
echo "Binary: ${DIST_DIR}/bin/av-imgdata-face-processor.exe"
