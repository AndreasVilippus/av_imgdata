#!/usr/bin/env bash
set -Eeuo pipefail

#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PACKAGE_ROOT}/../.." && pwd)"
TOOLKIT_ROOT="${WORKSPACE_ROOT}/pkgscripts-ng"
PKGCREATE="${TOOLKIT_ROOT}/PkgCreate.py"

DEFAULT_ARGS=(-v 7.3 -p geminilake -c av_imgdata)

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
  tools/build-package.sh [PkgCreate.py arguments...]

Examples:
  tools/build-package.sh
  tools/build-package.sh -v 7.3 -p geminilake -c av_imgdata
  tools/build-package.sh -v 7.3 -p apollolake -c av_imgdata

If no arguments are passed, the script uses:
  -v 7.3 -p geminilake -c av_imgdata
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

log "Running Python tests"
python3 -m unittest discover -s tests -p 'test_*.py'

log "Installing UI dependencies"
cd "${PACKAGE_ROOT}/ui"

if [[ -f pnpm-lock.yaml ]]; then
  pnpm install --frozen-lockfile
else
  pnpm install
fi

log "Building UI"
pnpm run build

log "Building Synology package"
cd "${TOOLKIT_ROOT}"

if [[ "$#" -gt 0 ]]; then
  python3 "${PKGCREATE}" "$@"
else
  python3 "${PKGCREATE}" "${DEFAULT_ARGS[@]}"
fi

log "Package build completed"