#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="linux-x86_64"
DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
BUILD_ROOT="${PROJECT_DIR}/build/native/${TARGET}"
BUILD_DIR="${BUILD_ROOT}/face_processor-build"
INSTALL_DIR="${BUILD_ROOT}/face_processor-install"
DIST_DIR="${PROJECT_DIR}/dist/av-imgdata-face-processor-${TARGET}"
CLEAN=0
FETCH_DEPS=1
FORCE_DEPS=0
UPDATE_CHECK=1

usage() {
  cat <<'EOF'
Usage: tools/build-native-face-processor-linux.sh [options]

Options:
  --clean             Remove build, install, and dist directories before building
  --no-fetch-deps     Do not auto-download missing Linux native dependencies
  --force-deps        Re-download and re-extract Linux native dependencies
  --no-update-check   Do not query GitHub release metadata for newer dependency versions
  -h, --help          Show this help

Dependency defaults:
  worker/native_deps/linux-x86_64/onnxruntime
  worker/native_deps/linux-x86_64/onnxruntime-linux-x64-*
  worker/native_deps/linux-x86_64/jpeg
  worker/native_deps/linux-x86_64/libjpeg-turbo
  worker/native_deps/linux-x86_64/libjpeg*
  worker/native_deps/linux-x86_64/heif       optional

Environment overrides:
  ONNXRUNTIME_ROOT       Optional. Linux ONNXRuntime C API root containing include/ and lib/.
  JPEG_ROOT              Optional. Linux libjpeg-turbo root containing include/ and lib/ or lib64/.
  HEIF_ROOT              Optional. Linux libheif root containing include/libheif/heif.h.
  ONNXRUNTIME_VERSION    Optional for auto-fetch. Default is set by tools/fetch-worker-native-deps.sh.
  LIBJPEG_TURBO_VERSION  Optional for auto-fetch. Default is set by tools/fetch-worker-native-deps.sh.
  CC                     Optional. Defaults to cc.
  CXX                    Optional. Defaults to c++.

Output:
  dist/av-imgdata-face-processor-linux-x86_64/bin/av-imgdata-face-processor
  dist/av-imgdata-face-processor-linux-x86_64/lib/libjpeg.so*
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --clean)
      CLEAN=1
      shift
      ;;
    --no-fetch-deps)
      FETCH_DEPS=0
      shift
      ;;
    --force-deps)
      FORCE_DEPS=1
      shift
      ;;
    --no-update-check)
      UPDATE_CHECK=0
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

copy_optional_license_file() {
  local source="$1"
  local target="$2"
  if [ -f "${source}" ]; then
    mkdir -p "$(dirname "${target}")"
    cp -a "${source}" "${target}"
  fi
}

first_existing_dir() {
  local candidate
  for candidate in "$@"; do
    [ -d "${candidate}" ] || continue
    printf '%s\n' "${candidate}"
    return 0
  done
  return 1
}

resolve_deps() {
  if [ -z "${ONNXRUNTIME_ROOT:-}" ]; then
    ONNXRUNTIME_ROOT="$(first_existing_dir \
      "${DEPS_ROOT}/onnxruntime" \
      "${DEPS_ROOT}"/onnxruntime-linux-x64* \
      "${DEPS_ROOT}"/onnxruntime* \
      2>/dev/null || true)"
  fi
  if [ -z "${JPEG_ROOT:-}" ]; then
    JPEG_ROOT="$(first_existing_dir \
      "${DEPS_ROOT}/jpeg" \
      "${DEPS_ROOT}/libjpeg-turbo" \
      "${DEPS_ROOT}/libjpeg" \
      "${DEPS_ROOT}"/libjpeg-turbo* \
      "${DEPS_ROOT}"/jpeg* \
      "${DEPS_ROOT}"/libjpeg* \
      2>/dev/null || true)"
  fi
  if [ -z "${HEIF_ROOT:-}" ]; then
    HEIF_ROOT="$(first_existing_dir \
      "${DEPS_ROOT}/heif" \
      "${DEPS_ROOT}"/libheif* \
      "${DEPS_ROOT}"/heif* \
      2>/dev/null || true)"
  fi
}

fetch_missing_deps() {
  [ "${FETCH_DEPS}" = "1" ] || return 0
  if [ -n "${ONNXRUNTIME_ROOT:-}" ] && [ -n "${JPEG_ROOT:-}" ] && [ "${FORCE_DEPS}" != "1" ]; then
    return 0
  fi
  local fetch_args=(--target "${TARGET}")
  if [ "${FORCE_DEPS}" = "1" ]; then
    fetch_args+=(--force)
  fi
  if [ "${UPDATE_CHECK}" != "1" ]; then
    fetch_args+=(--no-update-check)
  fi
  echo "Preparing Linux native dependencies..."
  "${PROJECT_DIR}/tools/fetch-worker-native-deps.sh" "${fetch_args[@]}"
}

resolve_deps
fetch_missing_deps
resolve_deps

if [ -z "${ONNXRUNTIME_ROOT:-}" ]; then
  echo "ERROR: ONNXRUNTIME_ROOT is required for the Linux face processor build." >&2
  echo "       Expected one of:" >&2
  echo "       ${DEPS_ROOT}/onnxruntime" >&2
  echo "       ${DEPS_ROOT}/onnxruntime-linux-x64-*" >&2
  echo "       or set ONNXRUNTIME_ROOT=/path/to/onnxruntime" >&2
  exit 1
fi
if [ -z "${JPEG_ROOT:-}" ]; then
  echo "ERROR: JPEG_ROOT is required for the Linux face processor build." >&2
  echo "       Expected one of:" >&2
  echo "       ${DEPS_ROOT}/jpeg" >&2
  echo "       ${DEPS_ROOT}/libjpeg-turbo" >&2
  echo "       ${DEPS_ROOT}/libjpeg*" >&2
  echo "       or set JPEG_ROOT=/path/to/libjpeg-turbo" >&2
  exit 1
fi

require_command cmake
require_command "${CC:-cc}"
require_command "${CXX:-c++}"

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
  -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}/usr/local/AV_ImgData"
  -DONNXRUNTIME_ROOT="${ONNXRUNTIME_ROOT}"
  -DJPEG_ROOT="${JPEG_ROOT}"
  -DAV_FACE_PROCESSOR_BUNDLE_JPEG=ON
)

if command -v ninja >/dev/null 2>&1; then
  CMAKE_ARGS+=(-G Ninja)
fi
if [ -n "${HEIF_ROOT:-}" ]; then
  CMAKE_ARGS+=(-DHEIF_ROOT="${HEIF_ROOT}")
fi

cmake "${CMAKE_ARGS[@]}"
cmake --build "${BUILD_DIR}"
cmake --install "${BUILD_DIR}" --strip || cmake --install "${BUILD_DIR}"

NATIVE_BINARY="${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor"
if [ ! -f "${NATIVE_BINARY}" ]; then
  echo "ERROR: Linux face processor build did not produce ${NATIVE_BINARY}" >&2
  exit 1
fi

mkdir -p "${DIST_DIR}/bin" "${DIST_DIR}/lib" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor"
cp -a "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" "${DIST_DIR}/bin/"
cp -a "${INSTALL_DIR}/usr/local/AV_ImgData/lib/." "${DIST_DIR}/lib/"

cat > "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/README.txt" <<EOF
AV_ImgData Linux native face processor bundle.

Bundled runtime libraries may include:
- ONNXRuntime from ONNXRUNTIME_ROOT=${ONNXRUNTIME_ROOT}
- libjpeg/libjpeg-turbo runtime from JPEG_ROOT=${JPEG_ROOT}

The processor is built and packaged with matching libjpeg headers and runtime from JPEG_ROOT.
EOF
copy_optional_license_file "${ONNXRUNTIME_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.LICENSE"
copy_optional_license_file "${ONNXRUNTIME_ROOT}/ThirdPartyNotices.txt" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.ThirdPartyNotices.txt"
copy_optional_license_file "${JPEG_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/jpeg.LICENSE"
copy_optional_license_file "${JPEG_ROOT}/share/doc/libjpeg-turbo/LICENSE.md" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libjpeg-turbo.LICENSE.md"
copy_optional_license_file "${JPEG_ROOT}/share/licenses/libjpeg-turbo/LICENSE.md" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libjpeg-turbo.LICENSE.md"
copy_optional_license_file "${JPEG_ROOT}/opt/libjpeg-turbo/LICENSE.md" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libjpeg-turbo.LICENSE.md"

if command -v ldd >/dev/null 2>&1; then
  echo "Linux native face processor runtime dependencies:"
  LD_LIBRARY_PATH="${DIST_DIR}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ldd "${DIST_DIR}/bin/av-imgdata-face-processor" || true
fi

echo "Linux native face processor build completed: ${DIST_DIR}"
echo "Binary: ${DIST_DIR}/bin/av-imgdata-face-processor"
