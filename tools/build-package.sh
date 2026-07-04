#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PACKAGE_ROOT}/../.." && pwd)"
TOOLKIT_ROOT="${WORKSPACE_ROOT}/pkgscripts-ng"
PKGCREATE="${TOOLKIT_ROOT}/PkgCreate.py"
PACKAGE_NAME="av_imgdata"

DEFAULT_ARGS=(-v 7.3 -p geminilake -c)

log() {
  printf '\n==> %s\n' "$*"
}

SANITIZE_DIRS=(
  ".test-venv"
  "ui/node_modules"
  "src/__pycache__"
  "src/services/__pycache__"
  "app/__pycache__"
)
SANITIZE_NATIVE_BUILD_PATTERNS=(
  "build/native/*/face_processor-build"
  "build/native/*/face_processor-install"
  "build/native/*/libvips-build"
  "build/native/*/libvips-source"
  "build/native/*/vips-image-processor-build"
  "build/native/*/vips-image-processor-install"
)
SANITIZE_BACKUP_ROOT=""
SANITIZED_DIRS=()
TEST_PKGVAR=""

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

restore_local_build_artifacts() {
  local rel
  local backup

  if [[ -n "${SANITIZE_BACKUP_ROOT}" && -d "${SANITIZE_BACKUP_ROOT}" ]]; then
    for rel in "${SANITIZED_DIRS[@]}"; do
      backup="${SANITIZE_BACKUP_ROOT}/${rel}"
      if [[ -e "${backup}" ]]; then
        mkdir -p "$(dirname "${PACKAGE_ROOT}/${rel}")"
        if [[ -e "${PACKAGE_ROOT}/${rel}" ]]; then
          rm -rf "${PACKAGE_ROOT:?}/${rel}"
        fi
        mv "${backup}" "${PACKAGE_ROOT}/${rel}"
      fi
    done
    rm -rf "${SANITIZE_BACKUP_ROOT}"
  fi

  if [[ -n "${TEST_PKGVAR}" ]]; then
    rm -rf "${TEST_PKGVAR}"
  fi
}

sanitize_project_for_toolkit_link() {
  local rel
  local backup

  SANITIZE_BACKUP_ROOT="$(mktemp -d "${PACKAGE_ROOT}/../.av_imgdata-link-sanitize.XXXXXX")"
  for rel in "${SANITIZE_DIRS[@]}"; do
    if [[ -e "${PACKAGE_ROOT}/${rel}" ]]; then
      backup="${SANITIZE_BACKUP_ROOT}/${rel}"
      mkdir -p "$(dirname "${backup}")"
      mv "${PACKAGE_ROOT}/${rel}" "${backup}"
      SANITIZED_DIRS+=("${rel}")
    fi
  done
  for pattern in "${SANITIZE_NATIVE_BUILD_PATTERNS[@]}"; do
    for rel in ${pattern}; do
      if [[ -e "${PACKAGE_ROOT}/${rel}" ]]; then
        backup="${SANITIZE_BACKUP_ROOT}/${rel}"
        mkdir -p "$(dirname "${backup}")"
        mv "${PACKAGE_ROOT}/${rel}" "${backup}"
        SANITIZED_DIRS+=("${rel}")
      fi
    done
  done
}

usage() {
  cat <<'EOF'
Usage:
  tools/build-package.sh [PkgCreate.py options...]

Examples:
  tools/build-package.sh
  tools/build-package.sh -v 7.3 -p geminilake
  tools/build-package.sh -v 7.3 -p apollolake

The script always builds the av_imgdata package. If no arguments are passed,
it uses:
  -v 7.3 -p geminilake
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

cd "${PACKAGE_ROOT}"
trap restore_local_build_artifacts EXIT

[[ -d "tests" ]] || fail "Required directory not found: tests"
[[ -d "ui" ]] || fail "Required directory not found: ui"
[[ -f "${PKGCREATE}" ]] || fail "PkgCreate.py not found: ${PKGCREATE}"

log "Running structure checks"
python3 tools/check_syntax_and_structure.py

log "Running Python tests"
TEST_PKGVAR="$(mktemp -d)"
export SYNOPKG_PKGVAR="${TEST_PKGVAR}"

PYTHONPATH=src python3 -m pytest tests

log "Temporarily moving local build artifacts out of the Toolkit link tree"
sanitize_project_for_toolkit_link

log "Building Synology package"
cd "${TOOLKIT_ROOT}"

if [[ "$#" -gt 0 ]]; then
  python3 "${PKGCREATE}" "$@" "${PACKAGE_NAME}"
else
  python3 "${PKGCREATE}" "${DEFAULT_ARGS[@]}" "${PACKAGE_NAME}"
fi

log "Package build completed"
