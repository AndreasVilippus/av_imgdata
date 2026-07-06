#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="linux-x86_64"
BUILD_DOCKER_IMAGE=0
CLEAN=0

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
  AV_IMGDATA_MINGW_BIN            Optional MinGW bin directory containing runtime DLLs.

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

copy_if_exists() {
  local source="$1"
  local target="$2"
  if [ -f "${source}" ]; then
    mkdir -p "$(dirname "${target}")"
    cp -a "${source}" "${target}"
    return 0
  fi
  return 1
}

copy_dir_if_exists() {
  local source="$1"
  local target="$2"
  if [ -d "${source}" ]; then
    mkdir -p "${target}"
    cp -a "${source}/." "${target}/"
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
      cp -aL "${source}" "${target_dir}/"
    done
  done
}

copy_mingw_runtime_dlls() {
  local target_dir="$1"
  local mingw_bin="${AV_IMGDATA_MINGW_BIN:-}"
  if [ -z "${mingw_bin}" ]; then
    local compiler
    compiler="$(command -v x86_64-w64-mingw32-g++ 2>/dev/null || true)"
    if [ -n "${compiler}" ]; then
      mingw_bin="$(dirname "${compiler}")"
    fi
  fi
  if [ -z "${mingw_bin}" ] || [ ! -d "${mingw_bin}" ]; then
    echo "WARNING: MinGW bin directory not found; runtime DLLs were not bundled." >&2
    echo "         Set AV_IMGDATA_MINGW_BIN=/path/to/mingw/bin if Windows reports missing libstdc++/libgcc/libwinpthread DLLs." >&2
    return 0
  fi
  copy_matching_files_if_exists "${mingw_bin}" "${target_dir}" \
    "libstdc++-6.dll" \
    "libgcc_s_seh-1.dll" \
    "libgcc_s_sjlj-1.dll" \
    "libgcc_s_dw2-1.dll" \
    "libwinpthread-1.dll"
  echo "Bundled MinGW runtime DLLs from ${mingw_bin} into ${target_dir}"
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
    cp -a "${AV_IMGDATA_FACE_PROCESSOR_BIN}" "${DIST_DIR}/bin/${target_binary_name}"
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

BUILD_DIR="${PROJECT_DIR}/build/worker/${TARGET}"
DIST_DIR="${PROJECT_DIR}/dist/av-imgdata-worker-${TARGET}"

if [ "${CLEAN}" = "1" ]; then
  rm -rf "${BUILD_DIR}" "${DIST_DIR}"
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

mkdir -p "${DIST_DIR}/models" "${DIST_DIR}/logs" "${DIST_DIR}/work" "${DIST_DIR}/bin"
if [ ! -f "${DIST_DIR}/models/README.txt" ]; then
  cat >"${DIST_DIR}/models/README.txt" <<'MODEL_README'
Place InsightFace-compatible model files here for local worker tests.

Expected default model layout:
  models/buffalo_l/det_10g.onnx
  models/buffalo_l/w600k_r50.onnx
MODEL_README
fi

bundle_face_processor_if_available

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
