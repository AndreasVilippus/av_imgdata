#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="linux-x86_64"
DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
DOWNLOAD_DIR="${DEPS_ROOT}/downloads"
FORCE=0
CHECK_UPDATES=1

ONNXRUNTIME_VERSION="${ONNXRUNTIME_VERSION:-1.20.1}"
LIBJPEG_TURBO_VERSION="${LIBJPEG_TURBO_VERSION:-3.2.0}"

usage() {
  cat <<'EOF'
Usage: tools/fetch-worker-native-deps.sh [options]

Options:
  --target <name>       linux-x86_64. Default: linux-x86_64
  --force               Re-download and re-extract dependency bundles
  --no-update-check     Do not query GitHub release metadata for newer versions
  -h, --help            Show this help

Environment:
  ONNXRUNTIME_VERSION       Default: 1.20.1
  LIBJPEG_TURBO_VERSION     Default: 3.2.0

This script downloads upstream native runtime dependencies into worker/native_deps/.
It does not install system packages and does not commit downloaded binaries.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --no-update-check)
      CHECK_UPDATES=0
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
  linux-x86_64) ;;
  *)
    echo "ERROR: unsupported dependency target: ${TARGET}" >&2
    echo "Supported targets: linux-x86_64" >&2
    exit 2
    ;;
esac

DEPS_ROOT="${PROJECT_DIR}/worker/native_deps/${TARGET}"
DOWNLOAD_DIR="${DEPS_ROOT}/downloads"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $1" >&2
    exit 1
  fi
}

require_command curl
require_command tar
require_command dpkg-deb

fetch_url() {
  local url="$1"
  local output="$2"
  if [ "${FORCE}" != "1" ] && [ -s "${output}" ]; then
    echo "Dependency archive already present: ${output}"
    return 0
  fi
  mkdir -p "$(dirname "${output}")"
  echo "Downloading: ${url}"
  curl -L -f --retry 3 --retry-delay 2 -o "${output}" "${url}"
}

latest_github_tag() {
  local repo="$1"
  curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" \
    | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -n 1
}

check_update_hint() {
  local name="$1"
  local repo="$2"
  local current="$3"
  local latest=""
  latest="$(latest_github_tag "${repo}" || true)"
  latest="${latest#v}"
  if [ -z "${latest}" ]; then
    echo "Update check: ${name}: unable to query latest release"
    return 0
  fi
  if [ "${latest}" != "${current}" ]; then
    echo "Update available: ${name} current=${current} latest=${latest}"
    echo "  Rebuild with ${name^^}_VERSION=${latest} if compatible and validated."
  else
    echo "Update check: ${name} current=${current} latest=${latest} ok"
  fi
}

write_manifest() {
  local path="$1"
  mkdir -p "$(dirname "${path}")"
  cat > "${path}" <<EOF
{
  "target": "${TARGET}",
  "onnxruntime_version": "${ONNXRUNTIME_VERSION}",
  "libjpeg_turbo_version": "${LIBJPEG_TURBO_VERSION}",
  "onnxruntime_url": "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}.tgz",
  "libjpeg_turbo_url": "https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/${LIBJPEG_TURBO_VERSION}/libjpeg-turbo-official_${LIBJPEG_TURBO_VERSION}_amd64.deb"
}
EOF
}

mkdir -p "${DOWNLOAD_DIR}"

ONNX_ARCHIVE="${DOWNLOAD_DIR}/onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}.tgz"
ONNX_URL="https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}.tgz"
ONNX_DIR="${DEPS_ROOT}/onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}"

JPEG_DEB="${DOWNLOAD_DIR}/libjpeg-turbo-official_${LIBJPEG_TURBO_VERSION}_amd64.deb"
JPEG_URL="https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/${LIBJPEG_TURBO_VERSION}/libjpeg-turbo-official_${LIBJPEG_TURBO_VERSION}_amd64.deb"
JPEG_ROOT="${DEPS_ROOT}/jpeg"

if [ "${CHECK_UPDATES}" = "1" ]; then
  check_update_hint "onnxruntime" "microsoft/onnxruntime" "${ONNXRUNTIME_VERSION}"
  check_update_hint "libjpeg_turbo" "libjpeg-turbo/libjpeg-turbo" "${LIBJPEG_TURBO_VERSION}"
fi

if [ "${FORCE}" = "1" ]; then
  rm -rf "${ONNX_DIR}" "${DEPS_ROOT}/onnxruntime" "${JPEG_ROOT}"
fi

if [ ! -f "${DEPS_ROOT}/onnxruntime/include/onnxruntime_c_api.h" ]; then
  fetch_url "${ONNX_URL}" "${ONNX_ARCHIVE}"
  rm -rf "${ONNX_DIR}"
  tar -xzf "${ONNX_ARCHIVE}" -C "${DEPS_ROOT}"
  ln -sfn "onnxruntime-linux-x64-${ONNXRUNTIME_VERSION}" "${DEPS_ROOT}/onnxruntime"
else
  echo "ONNXRuntime dependency ready: ${DEPS_ROOT}/onnxruntime"
fi

if [ ! -f "${JPEG_ROOT}/include/jpeglib.h" ] || ! compgen -G "${JPEG_ROOT}/lib/libjpeg.so*" >/dev/null; then
  fetch_url "${JPEG_URL}" "${JPEG_DEB}"
  rm -rf "${JPEG_ROOT}"
  mkdir -p "${JPEG_ROOT}"
  dpkg-deb -x "${JPEG_DEB}" "${JPEG_ROOT}"
  if [ ! -d "${JPEG_ROOT}/opt/libjpeg-turbo" ]; then
    echo "ERROR: libjpeg-turbo package did not contain /opt/libjpeg-turbo" >&2
    exit 1
  fi
  ln -sfn "opt/libjpeg-turbo/include" "${JPEG_ROOT}/include"
  if [ -d "${JPEG_ROOT}/opt/libjpeg-turbo/lib64" ]; then
    ln -sfn "opt/libjpeg-turbo/lib64" "${JPEG_ROOT}/lib"
  else
    ln -sfn "opt/libjpeg-turbo/lib" "${JPEG_ROOT}/lib"
  fi
else
  echo "libjpeg-turbo dependency ready: ${JPEG_ROOT}"
fi

if [ ! -f "${DEPS_ROOT}/onnxruntime/include/onnxruntime_c_api.h" ]; then
  echo "ERROR: ONNXRuntime header missing after fetch" >&2
  exit 1
fi
if [ ! -f "${JPEG_ROOT}/include/jpeglib.h" ]; then
  echo "ERROR: libjpeg-turbo header missing after fetch" >&2
  exit 1
fi
if ! compgen -G "${JPEG_ROOT}/lib/libjpeg.so*" >/dev/null; then
  echo "ERROR: libjpeg-turbo runtime missing after fetch" >&2
  exit 1
fi

write_manifest "${DEPS_ROOT}/native-deps-manifest.json"

cat <<EOF
Native worker dependencies ready:
  target: ${TARGET}
  ONNXRUNTIME_ROOT=${DEPS_ROOT}/onnxruntime
  JPEG_ROOT=${JPEG_ROOT}
  manifest: ${DEPS_ROOT}/native-deps-manifest.json
EOF
