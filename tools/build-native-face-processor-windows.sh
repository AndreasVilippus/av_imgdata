#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="windows-x86_64"
DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
BUILD_ROOT="${AV_IMGDATA_FACE_PROCESSOR_WINDOWS_BUILD_ROOT:-${PROJECT_DIR}/build/native/${TARGET}}"
PATCHED_SOURCE_DIR="${BUILD_ROOT}/face_processor-source"
BUILD_DIR="${BUILD_ROOT}/face_processor-build"
INSTALL_DIR="${BUILD_ROOT}/face_processor-install"
DIST_DIR="${AV_IMGDATA_FACE_PROCESSOR_WINDOWS_DIST_DIR:-${PROJECT_DIR}/dist/av-imgdata-face-processor-${TARGET}}"
CLEAN=0

usage() {
  cat <<'EOF'
Usage: tools/build-native-face-processor-windows.sh [options]

Options:
  --clean        Remove build, install, and dist directories before building
  -h, --help     Show this help

Dependency defaults:
  worker/native_deps/windows-x86_64/onnxruntime
  worker/native_deps/windows-x86_64/onnxruntime-win-x64-*
  worker/native_deps/windows-x86_64/jpeg
  worker/native_deps/windows-x86_64/libjpeg*
  worker/native_deps/windows-x86_64/vips       optional HEIF/libheif source
  worker/native_deps/windows-x86_64/heif       optional HEIF/libheif source

Environment overrides:
  ONNXRUNTIME_ROOT   Optional. Windows ONNXRuntime C API root containing include/ and lib/ or bin/.
  JPEG_ROOT          Optional. Windows JPEG/libjpeg root containing include/ and lib/ or bin/.
  HEIF_ROOT          Optional. Windows libheif root containing include/libheif/heif.h and bin/libheif.dll.
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
      cp -L "${source}" "${target_dir}/"
    done
  done
}

copy_optional_license_file() {
  local source="$1"
  local target="$2"
  if [ -f "${source}" ]; then
    mkdir -p "$(dirname "${target}")"
    cp -L "${source}" "${target}"
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
      "${DEPS_ROOT}"/onnxruntime-win-x64* \
      "${DEPS_ROOT}"/onnxruntime* \
      2>/dev/null || true)"
  fi
  if [ -z "${JPEG_ROOT:-}" ]; then
    JPEG_ROOT="$(first_existing_dir \
      "${DEPS_ROOT}/jpeg" \
      "${DEPS_ROOT}/libjpeg" \
      "${DEPS_ROOT}/libjpeg-turbo" \
      "${DEPS_ROOT}"/jpeg* \
      "${DEPS_ROOT}"/libjpeg* \
      2>/dev/null || true)"
  fi
  if [ -z "${HEIF_ROOT:-}" ]; then
    HEIF_ROOT="$(first_existing_dir \
      "${DEPS_ROOT}/vips" \
      "${DEPS_ROOT}/heif" \
      "${DEPS_ROOT}"/libheif* \
      "${DEPS_ROOT}"/heif* \
      2>/dev/null || true)"
  fi
}

prepare_windows_source_tree() {
  require_command python3
  rm -rf "${PATCHED_SOURCE_DIR}"
  mkdir -p "$(dirname "${PATCHED_SOURCE_DIR}")"
  cp -a "${PROJECT_DIR}/processors/native/face_processor" "${PATCHED_SOURCE_DIR}"

  python3 - "${PATCHED_SOURCE_DIR}" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
cmake = root / "CMakeLists.txt"
main = root / "src" / "main.cpp"

cmake_text = cmake.read_text()
cmake_text = cmake_text.replace("set(CMAKE_CXX_STANDARD 11)", "set(CMAKE_CXX_STANDARD 17)")
cmake.write_text(cmake_text)

text = main.read_text()
old_create = '''bool create_session(OrtHandles& ort, const std::string& model_path, std::string* error) {
    OrtSession* session = NULL;
    OrtStatus* status = ort.api->CreateSession(ort.env, model_path.c_str(), ort.options, &session);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    ort.api->ReleaseSession(session);
    return true;
}'''
new_create = '''bool create_session(OrtHandles& ort, const std::string& model_path, std::string* error) {
    const std::string model_data = read_text(model_path);
    if (model_data.empty()) {
        *error = "failed to read model file: " + model_path;
        return false;
    }
    OrtSession* session = NULL;
    OrtStatus* status = ort.api->CreateSessionFromArray(
        ort.env,
        model_data.data(),
        model_data.size(),
        ort.options,
        &session
    );
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }
    ort.api->ReleaseSession(session);
    return true;
}'''
old_load = '''bool load_session(OrtHandles& ort, const std::string& model_path, OnnxSession* loaded, std::string* error) {
    loaded->ort = &ort;
    OrtStatus* status = ort.api->CreateSession(ort.env, model_path.c_str(), ort.options, &loaded->session);
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }'''
new_load = '''bool load_session(OrtHandles& ort, const std::string& model_path, OnnxSession* loaded, std::string* error) {
    loaded->ort = &ort;
    const std::string model_data = read_text(model_path);
    if (model_data.empty()) {
        *error = "failed to read model file: " + model_path;
        return false;
    }
    OrtStatus* status = ort.api->CreateSessionFromArray(
        ort.env,
        model_data.data(),
        model_data.size(),
        ort.options,
        &loaded->session
    );
    if (status) {
        *error = status_message(ort.api, status);
        return false;
    }'''
for old, new in ((old_create, new_create), (old_load, new_load)):
    if old not in text:
        raise SystemExit("expected source block not found while preparing Windows source tree")
    text = text.replace(old, new, 1)
main.write_text(text)
PY
}

resolve_deps

if [ -z "${ONNXRUNTIME_ROOT:-}" ]; then
  echo "ERROR: ONNXRUNTIME_ROOT is required for the Windows face processor build." >&2
  echo "       Expected one of:" >&2
  echo "       ${DEPS_ROOT}/onnxruntime" >&2
  echo "       ${DEPS_ROOT}/onnxruntime-win-x64-*" >&2
  echo "       or set ONNXRUNTIME_ROOT=/path/to/onnxruntime" >&2
  exit 1
fi
if [ -z "${JPEG_ROOT:-}" ]; then
  echo "ERROR: JPEG_ROOT is required for the Windows face processor build." >&2
  echo "       Expected one of:" >&2
  echo "       ${DEPS_ROOT}/jpeg" >&2
  echo "       ${DEPS_ROOT}/libjpeg*" >&2
  echo "       or set JPEG_ROOT=/path/to/jpeg" >&2
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
  rm -rf "${PATCHED_SOURCE_DIR}" "${BUILD_DIR}" "${INSTALL_DIR}" "${DIST_DIR}"
fi
if [ -e "${BUILD_DIR}" ] && [ ! -w "${BUILD_DIR}" ]; then
  echo "ERROR: Windows face processor build directory is not writable: ${BUILD_DIR}" >&2
  echo "       Remove or chown this generated directory, then rerun the build." >&2
  exit 1
fi
if [ -f "${BUILD_DIR}/CMakeCache.txt" ] && grep -Eq '^JPEG_INCLUDE_DIR:PATH=/usr/include$' "${BUILD_DIR}/CMakeCache.txt"; then
  if [ ! -w "${BUILD_DIR}" ]; then
    echo "ERROR: stale Windows face processor CMake cache uses host JPEG include path, but build dir is not writable: ${BUILD_DIR}" >&2
    echo "       Remove or chown this generated build directory, then rerun the build." >&2
    exit 1
  fi
  echo "Removing stale Windows face processor CMake cache with host JPEG include path: ${BUILD_DIR}"
  rm -rf "${BUILD_DIR}"
fi
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}" "${DIST_DIR}"
prepare_windows_source_tree

CMAKE_ARGS=(
  -S "${PATCHED_SOURCE_DIR}"
  -B "${BUILD_DIR}"
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}/usr/local/AV_ImgData"
  -DCMAKE_SYSTEM_NAME=Windows
  -DCMAKE_C_COMPILER="${CC:-x86_64-w64-mingw32-gcc}"
  -DCMAKE_CXX_COMPILER="${CXX:-x86_64-w64-mingw32-g++}"
  -DONNXRUNTIME_ROOT="${ONNXRUNTIME_ROOT}"
  -DJPEG_ROOT="${JPEG_ROOT}"
  -UJPEG_INCLUDE_DIR
  -UJPEG_LIBRARY
  -UHEIF_INCLUDE_DIR
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
cp -L "${NATIVE_BINARY}" "${DIST_DIR}/bin/av-imgdata-face-processor.exe"

copy_matching_files "${ONNXRUNTIME_ROOT}/lib" "${DIST_DIR}/lib" "onnxruntime.dll" "onnxruntime*.dll" "*.dll"
copy_matching_files "${ONNXRUNTIME_ROOT}/bin" "${DIST_DIR}/bin" "onnxruntime.dll" "onnxruntime*.dll" "*.dll"
copy_matching_files "${JPEG_ROOT}/bin" "${DIST_DIR}/bin" "*.dll"
copy_matching_files "${JPEG_ROOT}/lib" "${DIST_DIR}/lib" "*.dll" "libjpeg*.a" "jpeg*.a"
if [ -n "${HEIF_ROOT:-}" ]; then
  copy_matching_files "${HEIF_ROOT}/bin" "${DIST_DIR}/bin" \
    "libheif*.dll" \
    "libde265*.dll" \
    "libaom*.dll" \
    "libsharpyuv*.dll" \
    "libstdc++-6.dll" \
    "libgcc_s_seh-1.dll" \
    "libwinpthread-1.dll"
fi

cat > "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/README.txt" <<EOF
AV_ImgData Windows native face processor bundle.

Bundled runtime libraries may include:
- ONNXRuntime from ONNXRUNTIME_ROOT=${ONNXRUNTIME_ROOT}
- JPEG/libjpeg runtime from JPEG_ROOT=${JPEG_ROOT}
- HEIF/libheif runtime from HEIF_ROOT=${HEIF_ROOT:-not configured}
EOF
copy_optional_license_file "${ONNXRUNTIME_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.LICENSE"
copy_optional_license_file "${ONNXRUNTIME_ROOT}/ThirdPartyNotices.txt" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/onnxruntime.ThirdPartyNotices.txt"
copy_optional_license_file "${JPEG_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/jpeg.LICENSE"
copy_optional_license_file "${JPEG_ROOT}/share/licenses/libjpeg-turbo/LICENSE.md" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libjpeg-turbo.LICENSE.md"
if [ -n "${HEIF_ROOT:-}" ]; then
  copy_optional_license_file "${HEIF_ROOT}/LICENSE" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libheif.LICENSE"
  copy_optional_license_file "${HEIF_ROOT}/COPYING" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libheif.COPYING"
  copy_optional_license_file "${HEIF_ROOT}/share/doc/libheif/COPYING" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libheif.COPYING"
  copy_optional_license_file "${HEIF_ROOT}/share/doc/libde265/COPYING" "${DIST_DIR}/share/licenses/AV_ImgData/native-face-processor/libde265.COPYING"
fi

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
