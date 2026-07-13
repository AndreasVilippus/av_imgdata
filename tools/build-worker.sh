#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="linux-x86_64"
BUILD_DOCKER_IMAGE=0
CLEAN=0
AV_IMGDATA_BUNDLE_WORKER_VIPS="${AV_IMGDATA_BUNDLE_WORKER_VIPS:-${AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR:-1}}"
AV_IMGDATA_BUILD_WORKER_VIPS="${AV_IMGDATA_BUILD_WORKER_VIPS:-1}"
AV_IMGDATA_LINUX_CHROOT="${AV_IMGDATA_LINUX_CHROOT:-1}"
AV_IMGDATA_REQUIRE_WORKER_VIPS="${AV_IMGDATA_REQUIRE_WORKER_VIPS:-1}"

usage() {
  cat <<'EOF'
Usage: tools/build-worker.sh [options]

Options:
  --target <name>       linux-x86_64 | windows-x86_64 | docker-linux-x86_64
  --docker-build        For docker-linux-x86_64, also run docker build if docker is available
  --clean               Remove the target build and dist directories before building
  -h, --help            Show this help

Environment:
  AV_IMGDATA_FACE_PROCESSOR_BIN   Optional explicit path to an already built av-imgdata-face-processor binary.
  AV_IMGDATA_FACE_PROCESSOR_ROOT  Optional root containing bin/, lib/, and share/licenses/ for the face processor bundle.
  AV_IMGDATA_VIPS_PROCESSOR_BIN   Optional explicit path to an already built av-imgdata-image-processor binary.
  AV_IMGDATA_VIPS_PROCESSOR_ROOT  Optional root containing bin/, lib/, and share/licenses/ for the libvips image processor bundle.
  AV_IMGDATA_BUNDLE_WORKER_VIPS   Defaults to 1. Set to 0 to skip integrating libvips into the worker bundle.
  AV_IMGDATA_BUILD_WORKER_VIPS    Defaults to 1. Set to 0 to skip rebuilding libvips and use existing artifacts only.
  AV_IMGDATA_WORKER_BUNDLE_VIPS_PROCESSOR
                                  Compatibility alias for AV_IMGDATA_BUNDLE_WORKER_VIPS.
  AV_IMGDATA_REQUIRE_WORKER_VIPS  Defaults to 1. Set to 0 to allow worker bundles without a libvips image processor.
  AV_IMGDATA_LINUX_CHROOT         Defaults to 1. Set to 0 to build Linux libvips on the host instead of in a chroot.
  AV_IMGDATA_LINUX_CHROOT_ROOT    Optional chroot path. Default: build/chroot/linux-x86_64.
  AV_IMGDATA_MINGW_BIN            Optional MinGW bin directory containing runtime DLLs.

Defaults:
  For windows-x86_64, the worker automatically uses:
    dist/av-imgdata-face-processor-windows-x86_64/bin/av-imgdata-face-processor.exe
    dist/av-imgdata-face-processor-windows-x86_64
  if that bundle exists.

Phase B builds the UI-free external worker skeleton and local face-processor probe support. It does not build the DSM SPK and does not implement the DSM Worker API yet.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --docker-build)
      BUILD_DOCKER_IMAGE=1
      shift
      ;;
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

case "${TARGET}" in
  linux-x86_64|windows-x86_64|docker-linux-x86_64) ;;
  *)
    echo "ERROR: unsupported worker target: ${TARGET}" >&2
    echo "Supported targets: linux-x86_64, windows-x86_64, docker-linux-x86_64" >&2
    exit 2
    ;;
esac

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $1" >&2
    exit 1
  fi
}

require_worker_vips_build_tools() {
  local missing=0
  local tool
  local package
  for tool in curl cmake make meson ninja pkg-config strings; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      echo "ERROR: required libvips worker build tool not found: ${tool}" >&2
      missing=1
    fi
  done
  if command -v pkg-config >/dev/null 2>&1; then
    for package in glib-2.0 gio-2.0 gobject-2.0 expat; do
      if ! pkg-config --exists "${package}"; then
        echo "ERROR: required libvips worker build pkg-config package not found: ${package}" >&2
        missing=1
      fi
    done
  fi
  if [ "${missing}" = "1" ]; then
    echo "Install the Debian build host requirements, for example:" >&2
    echo "  sudo apt-get install -y build-essential cmake ninja-build meson pkg-config curl binutils libglib2.0-dev libexpat1-dev" >&2
    echo "Or set AV_IMGDATA_BUILD_WORKER_VIPS=0 to use an existing libvips worker artifact without rebuilding it." >&2
    exit 1
  fi
}

copy_if_exists() {
  local source="$1"
  local target="$2"
  if [ -f "${source}" ]; then
    mkdir -p "$(dirname "${target}")"
    cp -L "${source}" "${target}"
    return 0
  fi
  return 1
}

copy_dir_if_exists() {
  local source="$1"
  local target="$2"
  if [ -d "${source}" ]; then
    mkdir -p "${target}"
    cp -a --no-preserve=ownership "${source}/." "${target}/"
    return 0
  fi
  return 1
}

copy_matching_files_if_exists() {
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

copy_mingw_runtime_file() {
  local dll_name="$1"
  local target_dir="$2"
  local compiler="${CXX:-x86_64-w64-mingw32-g++}"
  local resolved=""

  if [ -f "${target_dir}/${dll_name}" ]; then
    echo "Keeping bundled runtime DLL already provided by processor bundle: ${dll_name}"
    return 0
  fi

  if command -v "${compiler}" >/dev/null 2>&1; then
    resolved="$(${compiler} -print-file-name="${dll_name}" 2>/dev/null || true)"
    if [ -n "${resolved}" ] && [ "${resolved}" != "${dll_name}" ] && [ -f "${resolved}" ]; then
      cp -L "${resolved}" "${target_dir}/"
      echo "Bundled MinGW runtime DLL: ${dll_name} from ${resolved}"
      return 0
    fi
  fi

  local mingw_bin="${AV_IMGDATA_MINGW_BIN:-}"
  if [ -z "${mingw_bin}" ] && command -v "${compiler}" >/dev/null 2>&1; then
    mingw_bin="$(dirname "$(command -v "${compiler}")")"
  fi
  if [ -n "${mingw_bin}" ] && [ -d "${mingw_bin}" ] && [ -f "${mingw_bin}/${dll_name}" ]; then
    cp -L "${mingw_bin}/${dll_name}" "${target_dir}/"
    echo "Bundled MinGW runtime DLL: ${dll_name} from ${mingw_bin}"
    return 0
  fi

  echo "WARNING: MinGW runtime DLL not found: ${dll_name}" >&2
  return 1
}

copy_mingw_runtime_dlls() {
  local target_dir="$1"
  mkdir -p "${target_dir}"
  local missing=0
  local dll
  for dll in \
    "libstdc++-6.dll" \
    "libgcc_s_seh-1.dll" \
    "libgcc_s_sjlj-1.dll" \
    "libgcc_s_dw2-1.dll" \
    "libwinpthread-1.dll"; do
    copy_mingw_runtime_file "${dll}" "${target_dir}" || missing=1
  done
  if [ "${missing}" = "1" ]; then
    echo "WARNING: Some optional MinGW runtime DLLs were not found. This is normal for unused exception models, but libstdc++-6.dll, libgcc_s_seh-1.dll and libwinpthread-1.dll should be present for this build." >&2
  fi
}

cleanup_generated_path() {
  local path="$1"
  local error_log
  [ -e "${path}" ] || return 0

  error_log="$(mktemp)"
  if ! rm -rf "${path}" 2>"${error_log}"; then
    echo "ERROR: generated worker path cannot be removed: ${path}" >&2
    echo "       Fix ownership or remove it outside this script, then rerun the worker build." >&2
    echo "       First rm errors:" >&2
    sed -n '1,20p' "${error_log}" >&2
    rm -f "${error_log}"
    exit 1
  fi
  rm -f "${error_log}"
}

apply_target_defaults() {
  if [ "${TARGET}" = "windows-x86_64" ] && [ -z "${AV_IMGDATA_FACE_PROCESSOR_BIN:-}" ]; then
    local default_face_root="${PROJECT_DIR}/dist/av-imgdata-face-processor-windows-x86_64"
    local default_face_bin="${default_face_root}/bin/av-imgdata-face-processor.exe"
    if [ -f "${default_face_bin}" ]; then
      AV_IMGDATA_FACE_PROCESSOR_ROOT="${AV_IMGDATA_FACE_PROCESSOR_ROOT:-${default_face_root}}"
      AV_IMGDATA_FACE_PROCESSOR_BIN="${default_face_bin}"
      echo "Using default Windows face processor bundle: ${default_face_root}"
    fi
  fi
}

bundle_face_processor_if_available() {
  local target_binary_name="av-imgdata-face-processor"
  local processor_target="${TARGET}"
  local copied=0
  local source_base=""

  if [ "${TARGET}" = "windows-x86_64" ]; then
    target_binary_name="av-imgdata-face-processor.exe"
  fi
  if [ "${TARGET}" = "docker-linux-x86_64" ]; then
    processor_target="linux-x86_64"
  fi

  if [ -n "${AV_IMGDATA_FACE_PROCESSOR_BIN:-}" ]; then
    if [ ! -f "${AV_IMGDATA_FACE_PROCESSOR_BIN}" ]; then
      echo "ERROR: AV_IMGDATA_FACE_PROCESSOR_BIN does not exist: ${AV_IMGDATA_FACE_PROCESSOR_BIN}" >&2
      exit 1
    fi
    cp -L "${AV_IMGDATA_FACE_PROCESSOR_BIN}" "${DIST_DIR}/bin/${target_binary_name}"
    source_base="${AV_IMGDATA_FACE_PROCESSOR_ROOT:-$(dirname "$(dirname "${AV_IMGDATA_FACE_PROCESSOR_BIN}")")}"
    copied=1
  fi

  local binary_candidates=(
    "${PROJECT_DIR}/build/native/${processor_target}/face_processor-install/usr/local/AV_ImgData/bin/${target_binary_name}"
    "${PROJECT_DIR}/build/native/local/face_processor-install/usr/local/AV_ImgData/bin/${target_binary_name}"
    "${PROJECT_DIR}/dist/av-imgdata-face-processor-${processor_target}/bin/${target_binary_name}"
    "${PROJECT_DIR}/dist/native-face-processor-${processor_target}/bin/${target_binary_name}"
  )

  local candidate
  if [ "${copied}" = "0" ]; then
    for candidate in "${binary_candidates[@]}"; do
      if copy_if_exists "${candidate}" "${DIST_DIR}/bin/${target_binary_name}"; then
        source_base="$(dirname "$(dirname "${candidate}")")"
        copied=1
        break
      fi
    done
  fi

  if [ "${copied}" = "1" ]; then
    echo "Bundled face processor: ${DIST_DIR}/bin/${target_binary_name}"
    copy_dir_if_exists "${source_base}/lib" "${DIST_DIR}/lib" || true
    copy_dir_if_exists "${source_base}/share/licenses" "${DIST_DIR}/share/licenses" || true
    if [ "${TARGET}" = "windows-x86_64" ]; then
      copy_matching_files_if_exists "${source_base}/bin" "${DIST_DIR}/bin" "*.dll" "*.DLL"
      copy_matching_files_if_exists "${source_base}/lib" "${DIST_DIR}/bin" "*.dll" "*.DLL"
      copy_mingw_runtime_dlls "${DIST_DIR}/bin"
      echo "Bundled Windows face processor runtime DLLs into ${DIST_DIR}/bin"
    fi
  else
    echo "WARNING: optional face processor binary not found for ${TARGET}; worker probe will report face_processor_binary_exists=false." >&2
    echo "         Build/copy ${target_binary_name} into ${DIST_DIR}/bin/ to enable processor probing." >&2
    echo "         Or set AV_IMGDATA_FACE_PROCESSOR_BIN=/path/to/${target_binary_name}." >&2
  fi
}

build_vips_processor_if_missing() {
  local processor_target="$1"

  case "${processor_target}" in
    linux-x86_64)
      if [ "${AV_IMGDATA_LINUX_CHROOT}" != "0" ]; then
        echo "Building libvips image processor for external worker target in Linux chroot: ${processor_target}"
        AV_IMGDATA_NATIVE_PLATFORM="${processor_target}" bash "${PROJECT_DIR}/tools/build-native-image-processor-vips-linux-chroot.sh"
      else
        require_worker_vips_build_tools
        echo "Building libvips image processor for external worker target: ${processor_target}"
        AV_IMGDATA_NATIVE_PLATFORM="${processor_target}" bash "${PROJECT_DIR}/tools/build-native-image-processor-vips.sh"
      fi
      ;;
    windows-x86_64)
      echo "Building Windows libvips image processor for external worker target: ${processor_target}"
      bash "${PROJECT_DIR}/tools/build-native-image-processor-vips-windows.sh"
      ;;
    *)
      echo "ERROR: unsupported libvips image processor target: ${processor_target}" >&2
      exit 1
      ;;
  esac
}

bundle_vips_processor() {
  local target_binary_name="av-imgdata-image-processor"
  local processor_target="${TARGET}"
  local copied=0
  local source_base=""

  if [ "${AV_IMGDATA_BUNDLE_WORKER_VIPS}" = "0" ]; then
    echo "Skipping libvips image processor integration because AV_IMGDATA_BUNDLE_WORKER_VIPS=0."
    return 0
  fi

  if [ "${TARGET}" = "windows-x86_64" ]; then
    target_binary_name="av-imgdata-image-processor.exe"
  fi
  if [ "${TARGET}" = "docker-linux-x86_64" ]; then
    processor_target="linux-x86_64"
  fi

  if [ -n "${AV_IMGDATA_VIPS_PROCESSOR_BIN:-}" ]; then
    if [ ! -f "${AV_IMGDATA_VIPS_PROCESSOR_BIN}" ]; then
      echo "ERROR: AV_IMGDATA_VIPS_PROCESSOR_BIN does not exist: ${AV_IMGDATA_VIPS_PROCESSOR_BIN}" >&2
      exit 1
    fi
    cp -L "${AV_IMGDATA_VIPS_PROCESSOR_BIN}" "${DIST_DIR}/bin/${target_binary_name}"
    source_base="${AV_IMGDATA_VIPS_PROCESSOR_ROOT:-$(dirname "$(dirname "${AV_IMGDATA_VIPS_PROCESSOR_BIN}")")}"
    copied=1
  fi

  if [ "${copied}" = "0" ] && [ "${AV_IMGDATA_BUILD_WORKER_VIPS}" != "0" ]; then
    build_vips_processor_if_missing "${processor_target}"
  fi

  local binary_candidates=(
    "${PROJECT_DIR}/build/native/${processor_target}/vips-image-processor-install/usr/local/AV_ImgData/bin/${target_binary_name}"
    "${PROJECT_DIR}/build/native/local/vips-image-processor-install/usr/local/AV_ImgData/bin/${target_binary_name}"
    "${PROJECT_DIR}/dist/av-imgdata-image-processor-${processor_target}/bin/${target_binary_name}"
    "${PROJECT_DIR}/dist/native-image-processor-vips-${processor_target}/bin/${target_binary_name}"
    "${PROJECT_DIR}/worker/native_deps/${processor_target}/vips/bin/${target_binary_name}"
  )

  local candidate
  if [ "${copied}" = "0" ]; then
    for candidate in "${binary_candidates[@]}"; do
      if copy_if_exists "${candidate}" "${DIST_DIR}/bin/${target_binary_name}"; then
        source_base="$(dirname "$(dirname "${candidate}")")"
        copied=1
        break
      fi
    done
  fi

  if [ "${copied}" = "0" ]; then
    if [ "${AV_IMGDATA_BUILD_WORKER_VIPS}" = "0" ]; then
      echo "Skipping libvips image processor rebuild because AV_IMGDATA_BUILD_WORKER_VIPS=0."
    fi
  fi

  if [ "${copied}" != "1" ]; then
    if [ "${AV_IMGDATA_REQUIRE_WORKER_VIPS}" = "0" ]; then
      echo "WARNING: optional libvips image processor binary not found for ${TARGET}; worker probe will report image_vips_binary_exists=false." >&2
      echo "         Build/copy ${target_binary_name} into ${DIST_DIR}/bin/ to enable worker image decoding." >&2
      echo "         Or set AV_IMGDATA_VIPS_PROCESSOR_BIN=/path/to/${target_binary_name}." >&2
      return 0
    fi
    echo "ERROR: required libvips image processor binary not found for ${TARGET}: ${target_binary_name}" >&2
    echo "       Build it first or set AV_IMGDATA_VIPS_PROCESSOR_BIN=/path/to/${target_binary_name}." >&2
    exit 1
  fi

  echo "Bundled libvips image processor: ${DIST_DIR}/bin/${target_binary_name}"
  copy_dir_if_exists "${source_base}/lib" "${DIST_DIR}/lib" || true
  copy_dir_if_exists "${source_base}/share/licenses" "${DIST_DIR}/share/licenses" || true
  if [ "${TARGET}" = "windows-x86_64" ]; then
    copy_matching_files_if_exists "${source_base}/bin" "${DIST_DIR}/bin" "*.dll" "*.DLL"
    copy_matching_files_if_exists "${source_base}/lib" "${DIST_DIR}/bin" "*.dll" "*.DLL"
    copy_mingw_runtime_dlls "${DIST_DIR}/bin"
    echo "Bundled Windows libvips image processor runtime DLLs into ${DIST_DIR}/bin"
  fi
}

write_worker_model_readme() {
  local readme="${DIST_DIR}/.models/face/README.txt"
  mkdir -p "$(dirname "${readme}")"
  cat >"${readme}" <<'MODEL_README'
Face model files are not distributed with this worker bundle.

Expected runtime layout:
  .models/face/buffalo_l/det_10g.onnx
  .models/face/buffalo_l/w600k_r50.onnx
  .models/face/buffalo_l/manifest.json
  .models/face/buffalo_l/LICENSE_ACK.json

Use tools/sync-worker-face-models.py from the source tree, or let the DSM package provide/sync these files after administrator acknowledgement.
MODEL_README
}

apply_target_defaults

BUILD_DIR="${PROJECT_DIR}/build/worker/${TARGET}"
DIST_DIR="${PROJECT_DIR}/dist/av-imgdata-worker-${TARGET}"

if [ "${CLEAN}" = "1" ]; then
  cleanup_generated_path "${BUILD_DIR}"
  cleanup_generated_path "${DIST_DIR}"
fi
if [ -e "${BUILD_DIR}" ] && [ ! -w "${BUILD_DIR}" ]; then
  echo "ERROR: worker build directory is not writable: ${BUILD_DIR}" >&2
  echo "       Remove or chown this generated build directory, then rerun the worker build." >&2
  exit 1
fi
if [ -e "${DIST_DIR}" ] && [ ! -w "${DIST_DIR}" ]; then
  echo "ERROR: worker dist directory is not writable: ${DIST_DIR}" >&2
  echo "       Remove or chown this generated dist directory, then rerun the worker build." >&2
  exit 1
fi

require_command cmake

CMAKE_ARGS=(
  -S "${PROJECT_DIR}/worker"
  -B "${BUILD_DIR}"
  -DCMAKE_INSTALL_PREFIX="${DIST_DIR}"
)

if command -v ninja >/dev/null 2>&1; then
  CMAKE_ARGS+=(-G Ninja)
fi

case "${TARGET}" in
  linux-x86_64)
    ;;
  docker-linux-x86_64)
    ;;
  windows-x86_64)
    require_command x86_64-w64-mingw32-g++
    CMAKE_ARGS+=(
      -DCMAKE_TOOLCHAIN_FILE="${PROJECT_DIR}/worker/cmake/toolchains/windows-mingw-x86_64.cmake"
    )
    ;;
esac

cmake "${CMAKE_ARGS[@]}"
cmake --build "${BUILD_DIR}"
cmake --install "${BUILD_DIR}"

mkdir -p "${DIST_DIR}/logs" "${DIST_DIR}/work" "${DIST_DIR}/bin"
write_worker_model_readme

bundle_face_processor_if_available
bundle_vips_processor

case "${TARGET}" in
  windows-x86_64)
    cp -a "${PROJECT_DIR}/worker/packaging/windows/README.md" "${DIST_DIR}/" 2>/dev/null || true
    if [ -f "${DIST_DIR}/config/worker-config.example.json" ]; then
      sed -i \
        -e 's#\.\./bin/av-imgdata-face-processor"#../bin/av-imgdata-face-processor.exe"#g' \
        -e 's#\.\./bin/av-imgdata-image-processor"#../bin/av-imgdata-image-processor.exe"#g' \
        "${DIST_DIR}/config/worker-config.example.json"
    fi
    ;;
  docker-linux-x86_64)
    cp -a "${PROJECT_DIR}/worker/packaging/docker/Dockerfile" "${DIST_DIR}/Dockerfile"
    cp -a "${PROJECT_DIR}/worker/packaging/docker/entrypoint.sh" "${DIST_DIR}/entrypoint.sh"
    chmod +x "${DIST_DIR}/entrypoint.sh"
    if [ "${BUILD_DOCKER_IMAGE}" = "1" ]; then
      require_command docker
      docker build -t av-imgdata-worker:phase-b "${DIST_DIR}"
    fi
    ;;
  linux-x86_64)
    cp -a "${PROJECT_DIR}/worker/packaging/systemd/av-imgdata-worker.service.example" "${DIST_DIR}/" 2>/dev/null || true
    ;;
esac

WORKER_BIN="${DIST_DIR}/bin/av-imgdata-worker"
if [ "${TARGET}" = "windows-x86_64" ]; then
  WORKER_BIN="${DIST_DIR}/bin/av-imgdata-worker.exe"
fi

if [ ! -f "${WORKER_BIN}" ]; then
  echo "ERROR: worker binary was not installed: ${WORKER_BIN}" >&2
  exit 1
fi

case "${TARGET}" in
  windows-x86_64)
    echo "Windows worker binary built: ${WORKER_BIN}"
    echo "Windows worker config uses .exe processor paths."
    echo "Local execution skipped on Debian/Linux host. Test this .exe on Windows 11."
    ;;
  *)
    if [ -x "${WORKER_BIN}" ]; then
      "${WORKER_BIN}" version
    else
      echo "ERROR: worker binary is not executable: ${WORKER_BIN}" >&2
      exit 1
    fi
    ;;
esac

echo "Worker Phase B build completed: target=${TARGET} dist=${DIST_DIR}"
