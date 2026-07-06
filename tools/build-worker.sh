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

mkdir -p "${DIST_DIR}/models" "${DIST_DIR}/logs" "${DIST_DIR}/work"
if [ ! -f "${DIST_DIR}/models/README.txt" ]; then
  cat >"${DIST_DIR}/models/README.txt" <<'EOF'
Place InsightFace-compatible model files here for local worker tests.

Expected default model layout:
  models/buffalo_l/det_10g.onnx
  models/buffalo_l/w600k_r50.onnx
EOF
fi

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
