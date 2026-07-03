#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
TOOLKIT_DIR="$(cd "${PROJECT_DIR}/../.." && pwd)"
BUILD_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}"
BUILD_DIR="${BUILD_ROOT}/face_processor-build"
INSTALL_DIR="${BUILD_ROOT}/face_processor-install"

rm -rf "${BUILD_DIR}" "${INSTALL_DIR}"

has_onnxruntime_root() {
  [ -f "$1/include/onnxruntime_c_api.h" ] && { [ -f "$1/lib/libonnxruntime.so" ] || [ -f "$1/lib64/libonnxruntime.so" ]; }
}

has_jpeg_root() {
  [ -f "$1/include/jpeglib.h" ] && { [ -f "$1/lib/libjpeg.so" ] || [ -f "$1/usr/lib/libjpeg.so" ] || [ -f "$1/usr/lib64/libjpeg.so" ]; }
}

has_heif_root() {
  [ -f "$1/include/libheif/heif.h" ]
}

resolve_onnxruntime_root() {
  if [ -n "${ONNXRUNTIME_ROOT:-}" ]; then
    has_onnxruntime_root "${ONNXRUNTIME_ROOT}" || {
      echo "ERROR: ONNXRUNTIME_ROOT does not contain include/onnxruntime_c_api.h and lib/libonnxruntime.so: ${ONNXRUNTIME_ROOT}" >&2
      exit 1
    }
    return
  fi

  local candidates=(
    "${BUILD_ROOT}/deps/onnxruntime"
    "${PROJECT_DIR}/build/native/deps/onnxruntime"
    "${PROJECT_DIR}/native_deps/onnxruntime"
    "${PROJECT_DIR}/third_party/onnxruntime"
    "/tmp/onnxruntime-capi"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if has_onnxruntime_root "${candidate}"; then
      export ONNXRUNTIME_ROOT="${candidate}"
      return
    fi
  done

  echo "ERROR: ONNXRuntime C API is required." >&2
  echo "Set ONNXRUNTIME_ROOT to a directory containing include/onnxruntime_c_api.h and lib/libonnxruntime.so." >&2
  exit 1
}

resolve_jpeg_root() {
  if [ -n "${JPEG_ROOT:-}" ]; then
    has_jpeg_root "${JPEG_ROOT}" || {
      echo "ERROR: JPEG_ROOT does not contain include/jpeglib.h and lib/libjpeg.so: ${JPEG_ROOT}" >&2
      exit 1
    }
    return
  fi

  local candidates=(
    "/usr"
    "/usr/local"
  )
  local candidate
  for candidate in /usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done
  candidates+=("/tmp/av-imgdata-jpeg-root")
  for candidate in "${TOOLKIT_DIR}"/build_env/ds."${PLATFORM}"-*/usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done
  for candidate in "${TOOLKIT_DIR}"/build_env/ds.*-*/usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done

  for candidate in "${candidates[@]}"; do
    if has_jpeg_root "${candidate}"; then
      export JPEG_ROOT="${candidate}"
      return
    fi
  done

  echo "ERROR: libjpeg is required." >&2
  echo "Set JPEG_ROOT to a sysroot containing include/jpeglib.h and lib/libjpeg.so." >&2
  exit 1
}

resolve_heif_root() {
  if [ -n "${HEIF_ROOT:-}" ]; then
    has_heif_root "${HEIF_ROOT}" || {
      echo "ERROR: HEIF_ROOT does not contain include/libheif/heif.h: ${HEIF_ROOT}" >&2
      exit 1
    }
    return
  fi

  local candidates=(
    "/usr"
    "/usr/local"
  )
  local candidate
  for candidate in /usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done
  for candidate in "${TOOLKIT_DIR}"/build_env/ds."${PLATFORM}"-*/usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done
  for candidate in "${TOOLKIT_DIR}"/build_env/ds.*-*/usr/local/*/*/sys-root/usr; do
    candidates+=("${candidate}")
  done

  for candidate in "${candidates[@]}"; do
    if has_heif_root "${candidate}"; then
      export HEIF_ROOT="${candidate}"
      return
    fi
  done

  echo "WARNING: libheif headers not found; native HEIC runtime loader will be disabled." >&2
}

resolve_onnxruntime_root
resolve_jpeg_root
resolve_heif_root

mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

cd "${BUILD_DIR}"
CMAKE_ARGS=(
  "${PROJECT_DIR}/processors/native/face_processor"
  "-DCMAKE_BUILD_TYPE=Release"
  "-DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData"
)
if [ -n "${ONNXRUNTIME_ROOT:-}" ]; then
  CMAKE_ARGS+=("-DONNXRUNTIME_ROOT=${ONNXRUNTIME_ROOT}")
fi
if [ -n "${JPEG_ROOT:-}" ]; then
  CMAKE_ARGS+=("-DJPEG_ROOT=${JPEG_ROOT}")
fi
if [ -n "${HEIF_ROOT:-}" ]; then
  CMAKE_ARGS+=("-DHEIF_ROOT=${HEIF_ROOT}")
fi
if [ -n "${CC:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_C_COMPILER=${CC}")
fi
if [ -n "${CXX:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=${CXX}")
fi
cmake "${CMAKE_ARGS[@]}"

make -j"$(nproc 2>/dev/null || echo 2)"
make install DESTDIR="${INSTALL_DIR}"

LIB_DIR="${INSTALL_DIR}/usr/local/AV_ImgData/lib"

copy_library_family() {
  local root="$1"
  local pattern="$2"
  local dir
  local source
  local target
  for dir in "${root}/lib" "${root}/usr/lib" "${root}/usr/lib64"; do
    if [ -d "${dir}" ]; then
      for source in "${dir}"/${pattern}; do
        [ -e "${source}" ] || continue
        target="${LIB_DIR}/$(basename "${source}")"
        if [ "$(readlink -f "${source}")" = "$(readlink -f "${target}" 2>/dev/null || true)" ]; then
          continue
        fi
        rm -f "${target}"
        cp -aL "${source}" "${target}"
      done
    fi
  done
}

copy_library_family "${JPEG_ROOT}" "libjpeg.so*"

if [ -L "${LIB_DIR}/libjpeg.so" ]; then
  JPEG_LINK_TARGET="$(readlink "${LIB_DIR}/libjpeg.so")"
  if [ "${JPEG_LINK_TARGET#/}" != "${JPEG_LINK_TARGET}" ] && [ -e "${JPEG_LINK_TARGET}" ]; then
    JPEG_BASENAME="$(basename "${JPEG_LINK_TARGET}")"
    rm -f "${LIB_DIR}/libjpeg.so"
    cp -aL "${JPEG_LINK_TARGET}" "${LIB_DIR}/${JPEG_BASENAME}"
    ln -s "${JPEG_BASENAME}" "${LIB_DIR}/libjpeg.so"
  fi
fi

strip_native_binary() {
  local binary="$1"
  local strip_tool="${STRIP:-strip}"
  if ! command -v "${strip_tool}" >/dev/null 2>&1; then
    echo "WARNING: strip tool not found: ${strip_tool}; native binary remains unstripped." >&2
    return
  fi
  "${strip_tool}" --strip-unneeded "${binary}" || "${strip_tool}" "${binary}" || true
}

NATIVE_BINARY="${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor"
if [ "${AV_IMGDATA_NATIVE_STRIP:-1}" != "0" ] && [ -x "${NATIVE_BINARY}" ]; then
  strip_native_binary "${NATIVE_BINARY}"
fi

if [ ! -x "${NATIVE_BINARY}" ]; then
  echo "ERROR: native face processor build did not produce an executable binary."
  exit 1
fi
