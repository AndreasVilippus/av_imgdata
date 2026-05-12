#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PACKAGE_ROOT}/../.." && pwd)"
TOOLKIT_ROOT="${WORKSPACE_ROOT}/pkgscripts-ng"
PKGCREATE="${TOOLKIT_ROOT}/PkgCreate.py"
PACKAGE_NAME="av_imgdata"

DEFAULT_ARGS=(-v 7.3 -p geminilake)

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
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

[[ -d "tests" ]] || fail "Required directory not found: tests"
[[ -d "ui" ]] || fail "Required directory not found: ui"
[[ -f "${PKGCREATE}" ]] || fail "PkgCreate.py not found: ${PKGCREATE}"

log "Running structure checks"
python3 tools/check_syntax_and_structure.py

log "Running Python tests"
TEST_PKGVAR="$(mktemp -d)"
trap 'rm -rf "${TEST_PKGVAR}"' EXIT
export SYNOPKG_PKGVAR="${TEST_PKGVAR}"

PYTHONPATH=src python3 -m pytest tests

log "Building Synology package"
cd "${TOOLKIT_ROOT}"

if [[ "$#" -gt 0 ]]; then
  python3 "${PKGCREATE}" "$@" "${PACKAGE_NAME}"
else
  python3 "${PKGCREATE}" "${DEFAULT_ARGS[@]}" "${PACKAGE_NAME}"
fi

log "Package build completed"
