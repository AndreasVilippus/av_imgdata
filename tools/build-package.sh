#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PACKAGE_ROOT}/../.." && pwd)"
TOOLKIT_ROOT="${WORKSPACE_ROOT}/pkgscripts-ng"
PKGCREATE="${TOOLKIT_ROOT}/PkgCreate.py"
PACKAGE_NAME="av_imgdata"

DEFAULT_ARGS=(-v 7.4 -p geminilake -c)
BUILD_EXTERNAL_WORKERS="${AV_IMGDATA_BUILD_EXTERNAL_WORKERS:-1}"
EXTERNAL_WORKER_TARGETS="${AV_IMGDATA_WORKER_TARGETS:-linux-x86_64 docker-linux-x86_64 windows-x86_64}"
BUILD_LINUX_FACE_PROCESSOR="${AV_IMGDATA_BUILD_LINUX_FACE_PROCESSOR:-1}"
BUILD_WINDOWS_FACE_PROCESSOR="${AV_IMGDATA_BUILD_WINDOWS_FACE_PROCESSOR:-1}"
WORKER_CLEAN="${AV_IMGDATA_WORKER_CLEAN:-1}"

log() {
  printf '\n==> %s\n' "$*"
}

SANITIZE_DIRS=(
  ".test-venv"
  "ui/node_modules"
  "src/__pycache__"
  "src/av_imgdata/__pycache__"
  "src/av_imgdata/db/__pycache__"
  "src/services/__pycache__"
  "app/__pycache__"
)
SANITIZE_NATIVE_BUILD_PATTERNS=(
  "build/worker/*"
  "build/chroot/*"
  "build/native/*/face_processor-build"
  "build/native/*/face_processor-source"
  "build/native/*/libde265-build"
  "build/native/*/libde265-source"
  "build/native/*/libheif-build"
  "build/native/*/libheif-source"
  "build/native/*/libvips-build"
  "build/native/*/libvips-source"
  "build/native/*/vips-image-processor-build"
)
SANITIZE_BACKUP_ROOT=""
STALE_GENERATED_BACKUP_ROOT=""
PRESERVED_LINUX_WORKER_VIPS_ROOT=""
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

  if [[ -n "${STALE_GENERATED_BACKUP_ROOT}" && -d "${STALE_GENERATED_BACKUP_ROOT}" ]]; then
    rm -rf "${STALE_GENERATED_BACKUP_ROOT}"
  fi

  if [[ -n "${TEST_PKGVAR}" ]]; then
    rm -rf "${TEST_PKGVAR}"
  fi
}

cleanup_stale_generated_backup_roots() {
  local stale_root

  for stale_root in "${PACKAGE_ROOT}"/.av_imgdata-stale-generated.*; do
    [[ -e "${stale_root}" ]] || continue
    [[ -d "${stale_root}" ]] || fail "Stale generated backup path is not a directory: ${stale_root}"
    rm -rf "${stale_root}"
  done
}

move_stale_generated_path_out_of_way() {
  local rel="$1"
  local source="${PACKAGE_ROOT}/${rel}"
  local target

  [[ -e "${source}" ]] || return 0
  [[ -w "${source}" ]] && return 0

  if [[ -z "${STALE_GENERATED_BACKUP_ROOT}" ]]; then
    STALE_GENERATED_BACKUP_ROOT="$(mktemp -d "${PACKAGE_ROOT}/.av_imgdata-stale-generated.XXXXXX")"
  fi

  target="${STALE_GENERATED_BACKUP_ROOT}/${rel}"
  mkdir -p "$(dirname "${target}")"
  log "Moving non-writable generated path out of the build tree: ${rel}"
  mv "${source}" "${target}" || fail "Cannot move non-writable generated path out of the build tree: ${rel}"
}

prepare_generated_worker_paths() {
  local target

  for target in ${EXTERNAL_WORKER_TARGETS}; do
    [[ "${target}" == "windows-x86_64" ]] && continue
    move_stale_generated_path_out_of_way "build/worker/${target}"
    move_stale_generated_path_out_of_way "dist/av-imgdata-worker-${target}"
  done
}

assert_no_nobody_generated_paths() {
  local roots=()
  local rel
  local matches

  for rel in build/worker build/native dist worker/native_deps; do
    [[ -e "${PACKAGE_ROOT}/${rel}" ]] && roots+=("${PACKAGE_ROOT}/${rel}")
  done

  [[ ${#roots[@]} -gt 0 ]] || return 0

  matches="$(find "${roots[@]}" -xdev \( -user nobody -o -group nogroup \) -print 2>/dev/null | sed -n '1,40p')"
  [[ -z "${matches}" ]] || fail "Generated paths owned by nobody/nogroup detected.
Remove or chown these generated paths before continuing:
${matches}"
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

pkgcreate_option_value() {
  local opt="$1"
  local default_value="$2"
  shift 2
  local args=("$@")
  local i

  for ((i = 0; i < ${#args[@]}; i++)); do
    if [[ "${args[$i]}" == "${opt}" && $((i + 1)) -lt ${#args[@]} ]]; then
      printf '%s\n' "${args[$((i + 1))]}"
      return
    fi
  done
  printf '%s\n' "${default_value}"
}

cleanup_existing_toolkit_link_target() {
  local args=("$@")
  local version
  local platform
  local target
  local error_log

  version="$(pkgcreate_option_value -v 7.4 "${args[@]}")"
  platform="$(pkgcreate_option_value -p geminilake "${args[@]}")"
  target="${WORKSPACE_ROOT}/build_env/ds.${platform}-${version}/source/${PACKAGE_NAME}"

  [[ -e "${target}" ]] || return 0

  error_log="$(mktemp)"
  if ! rm -rf "${target}" 2>"${error_log}"; then
    if command -v sudo >/dev/null 2>&1 && { sudo -n true >/dev/null 2>&1 || [[ -t 0 ]]; }; then
      log "Removing Toolkit link target with sudo because it contains files owned by another user: ${target}"
      if sudo rm -rf "${target}" 2>"${error_log}"; then
        rm -f "${error_log}"
        return 0
      fi
    fi
    local error_text
    error_text="$(sed -n '1,40p' "${error_log}")"
    rm -f "${error_log}"
    fail "Existing Toolkit link target cannot be removed: ${target}
This usually means the previous build left files owned by another user in the chroot source tree.
Fix ownership or remove the target outside this script, then rerun the package build.
Suggested cleanup:
sudo rm -rf '${target}'
First rm errors:
${error_text}"
  fi
  rm -f "${error_log}"
}

info_sh_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key {
    value = $2
    gsub(/^"/, "", value)
    gsub(/"$/, "", value)
    print value
    exit
  }' "${PACKAGE_ROOT}/INFO.sh"
}

cleanup_existing_image_packages() {
  local args=("$@")
  local version
  local platform
  local image_package_dir
  local package_title
  local package_version
  local pattern
  local error_log

  version="$(pkgcreate_option_value -v 7.4 "${args[@]}")"
  platform="$(pkgcreate_option_value -p geminilake "${args[@]}")"
  image_package_dir="${WORKSPACE_ROOT}/build_env/ds.${platform}-${version}/image/packages"

  [[ -d "${image_package_dir}" ]] || return 0

  package_title="$(info_sh_value package)"
  package_version="$(info_sh_value version)"
  [[ -n "${package_title}" && -n "${package_version}" ]] || return 0

  pattern="${image_package_dir}/${package_title}-*-${package_version}*.spk"
  compgen -G "${pattern}" >/dev/null || return 0

  error_log="$(mktemp)"
  if ! rm -f ${pattern} 2>"${error_log}"; then
    if command -v sudo >/dev/null 2>&1 && { sudo -n true >/dev/null 2>&1 || [[ -t 0 ]]; }; then
      log "Removing stale Toolkit image packages with sudo: ${image_package_dir}/${package_title}-*-${package_version}*.spk"
      if sudo rm -f ${pattern} 2>"${error_log}"; then
        rm -f "${error_log}"
        return 0
      fi
    fi
    local error_text
    error_text="$(sed -n '1,20p' "${error_log}")"
    rm -f "${error_log}"
    fail "Existing Toolkit image packages cannot be removed: ${image_package_dir}/${package_title}-*-${package_version}*.spk
First rm errors:
${error_text}"
  fi
  rm -f "${error_log}"
}

target_list_contains() {
  local wanted="$1"
  local target
  for target in ${EXTERNAL_WORKER_TARGETS}; do
    [[ "${target}" == "${wanted}" ]] && return 0
  done
  return 1
}

target_list_contains_linux_face_worker() {
  target_list_contains linux-x86_64 || target_list_contains docker-linux-x86_64
}

worker_clean_args() {
  if [[ "${WORKER_CLEAN}" != "0" ]]; then
    printf '%s\n' --clean
  fi
}

windows_native_deps_ready() {
  local deps_root="${PACKAGE_ROOT}/worker/native_deps/windows-x86_64"

  [[ -f "${deps_root}/onnxruntime/include/onnxruntime_c_api.h" ]] || return 1
  [[ -f "${deps_root}/jpeg/include/jpeglib.h" ]] || return 1
}

linux_native_deps_ready() {
  local deps_root="${PACKAGE_ROOT}/worker/native_deps/linux-x86_64"

  [[ -f "${deps_root}/onnxruntime/include/onnxruntime_c_api.h" ]] || return 1
  [[ -f "${deps_root}/jpeg/include/jpeglib.h" ]] || return 1
  compgen -G "${deps_root}/onnxruntime/lib/libonnxruntime.so*" >/dev/null || return 1
  compgen -G "${deps_root}/jpeg/lib/libjpeg.so*" >/dev/null || return 1
}

ensure_linux_native_deps() {
  linux_native_deps_ready && return 0

  log "Preparing Linux native worker dependencies"
  bash tools/fetch-worker-native-deps.sh --target linux-x86_64 --no-update-check
}

build_linux_face_processor_for_worker_bundle() {
  local clean_args=("$@")

  [[ "${BUILD_LINUX_FACE_PROCESSOR}" != "0" ]] || {
    log "Skipping Linux native face processor build because AV_IMGDATA_BUILD_LINUX_FACE_PROCESSOR=0"
    return 0
  }

  ensure_linux_native_deps
  log "Building Linux native face processor for external worker bundle"
  bash tools/build-native-face-processor-linux.sh "${clean_args[@]}" --no-fetch-deps --no-update-check
}

worker_face_processor_path() {
  local target="$1"
  local dist_dir="${PACKAGE_ROOT}/dist/av-imgdata-worker-${target}"
  local binary_name="av-imgdata-face-processor"

  if [[ "${target}" == "windows-x86_64" ]]; then
    dist_dir="${PACKAGE_ROOT}/dist/av-imgdata-worker-windows-x86_64.package"
    binary_name="av-imgdata-face-processor.exe"
  fi

  printf '%s\n' "${dist_dir}/bin/${binary_name}"
}

assert_worker_face_processor_bundled() {
  local target="$1"
  local binary

  binary="$(worker_face_processor_path "${target}")"
  [[ -x "${binary}" ]] || fail "External worker bundle is incomplete: missing executable face processor for ${target}: ${binary}"
}

find_existing_linux_worker_vips_artifact_root() {
  local root

  for root in \
    "${PACKAGE_ROOT}/build/native/linux-x86_64/vips-image-processor-install/usr/local/AV_ImgData" \
    "${PACKAGE_ROOT}/dist/av-imgdata-image-processor-linux-x86_64" \
    "${PACKAGE_ROOT}/dist/native-image-processor-vips-linux-x86_64" \
    "${PACKAGE_ROOT}/dist/av-imgdata-worker-linux-x86_64" \
    "${PACKAGE_ROOT}/dist/av-imgdata-worker-docker-linux-x86_64" \
    "${PACKAGE_ROOT}/worker/native_deps/linux-x86_64/vips"; do
    [[ -f "${root}/bin/av-imgdata-image-processor" ]] || continue
    compgen -G "${root}/lib/libvips.so*" >/dev/null || continue
    printf '%s\n' "${root}"
    return 0
  done

  return 1
}

existing_linux_worker_vips_artifact_ready() {
  find_existing_linux_worker_vips_artifact_root >/dev/null
}

preserve_existing_linux_worker_vips_artifact() {
  local source_root
  local target_root

  source_root="$(find_existing_linux_worker_vips_artifact_root)" || return 1
  target_root="${PACKAGE_ROOT}/build/native/linux-x86_64/package-worker-vips-artifact/usr/local/AV_ImgData"

  rm -rf "${target_root}"
  mkdir -p "${target_root}"
  cp -RL --no-preserve=ownership "${source_root}/bin" "${target_root}/bin"
  cp -RL --no-preserve=ownership "${source_root}/lib" "${target_root}/lib"
  if [[ -d "${source_root}/share" ]]; then
    cp -RL --no-preserve=ownership "${source_root}/share" "${target_root}/share"
  fi

  PRESERVED_LINUX_WORKER_VIPS_ROOT="${target_root}"
  export AV_IMGDATA_VIPS_PROCESSOR_ROOT="${target_root}"
  export AV_IMGDATA_VIPS_PROCESSOR_BIN="${target_root}/bin/av-imgdata-image-processor"
}

configure_noninteractive_linux_worker_vips_build() {
  if [[ -n "${AV_IMGDATA_LINUX_CHROOT+x}" ]]; then
    return 0
  fi
  if [[ -n "${AV_IMGDATA_BUILD_WORKER_VIPS+x}" ]]; then
    return 0
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    export AV_IMGDATA_LINUX_CHROOT=1
    export AV_IMGDATA_LINUX_CHROOT_ROOT="${AV_IMGDATA_LINUX_CHROOT_ROOT:-${WORKSPACE_ROOT}/build_env/${PACKAGE_NAME}-linux-chroot/linux-x86_64}"
    return 0
  fi

  if existing_linux_worker_vips_artifact_ready; then
    preserve_existing_linux_worker_vips_artifact
    export AV_IMGDATA_BUILD_WORKER_VIPS=0
    log "Using existing Linux worker libvips artifact because non-interactive sudo is not available"
    return 0
  fi

  fail "Cannot build Linux worker libvips non-interactively.
non-interactive sudo is not available and no existing Linux libvips worker artifact was found.
Run tools/build-package.sh with sudo, configure non-interactive sudo for the chroot build, or provide an existing artifact with AV_IMGDATA_BUILD_WORKER_VIPS=0."
}

ensure_windows_native_deps() {
  windows_native_deps_ready && return 0

  log "Preparing Windows native worker dependencies"
  bash tools/fetch-worker-windows-deps.sh
}

assert_pkgcreate_log_has_no_critical_errors() {
  local pkgcreate_log="$1"
  local critical_errors

  critical_errors="$(grep -E '(^|[[:space:]])ERROR: (native|optional|external worker|Windows external worker|ui/index.cgi|libjpeg|ONNXRuntime|duplicate package runtime library SONAMEs)' "${pkgcreate_log}" || true)"
  [[ -z "${critical_errors}" ]] || fail "Synology package build output contained critical errors although PkgCreate.py returned success:
${critical_errors}"
}

run_pkgcreate() {
  local pkgcreate_log

  pkgcreate_log="$(mktemp)"
  if [[ "$(id -u)" == "0" ]]; then
    if ! AV_IMGDATA_NATIVE_FETCH_DEPS=0 python3 "${PKGCREATE}" "$@" "${PACKAGE_NAME}" 2>&1 | tee "${pkgcreate_log}"; then
      fail "PkgCreate.py failed; preserved PkgCreate output log: ${pkgcreate_log}"
    fi
  elif command -v sudo >/dev/null 2>&1 && { sudo -n true >/dev/null 2>&1 || [[ -t 0 ]]; }; then
    if ! sudo env AV_IMGDATA_NATIVE_FETCH_DEPS=0 python3 "${PKGCREATE}" "$@" "${PACKAGE_NAME}" 2>&1 | tee "${pkgcreate_log}"; then
      fail "PkgCreate.py failed; preserved PkgCreate output log: ${pkgcreate_log}"
    fi
  else
    rm -f "${pkgcreate_log}"
    fail "PkgCreate.py requires root privileges for the Synology Toolkit chroot step.
Run tools/build-package.sh with sudo, or configure non-interactive sudo for the current user."
  fi
  assert_pkgcreate_log_has_no_critical_errors "${pkgcreate_log}"
  rm -f "${pkgcreate_log}"
}

build_external_worker_bundles() {
  local target
  local clean_args=()

  [[ "${BUILD_EXTERNAL_WORKERS}" != "0" ]] || {
    log "Skipping external worker bundles because AV_IMGDATA_BUILD_EXTERNAL_WORKERS=0"
    return 0
  }

  mapfile -t clean_args < <(worker_clean_args)
  prepare_generated_worker_paths

  if target_list_contains_linux_face_worker; then
    build_linux_face_processor_for_worker_bundle "${clean_args[@]}"
  fi

  if target_list_contains windows-x86_64 && [[ "${BUILD_WINDOWS_FACE_PROCESSOR}" != "0" ]]; then
    ensure_windows_native_deps
    log "Building Windows native face processor for external worker bundle"
    AV_IMGDATA_FACE_PROCESSOR_WINDOWS_BUILD_ROOT="${PACKAGE_ROOT}/build/native/windows-x86_64-package-face" \
    AV_IMGDATA_FACE_PROCESSOR_WINDOWS_DIST_DIR="${PACKAGE_ROOT}/dist/av-imgdata-face-processor-windows-x86_64.package" \
      bash tools/build-native-face-processor-windows.sh "${clean_args[@]}"
  fi

  for target in ${EXTERNAL_WORKER_TARGETS}; do
    log "Building external worker bundle: ${target}"
    if [[ "${target}" == "windows-x86_64" && "${BUILD_WINDOWS_FACE_PROCESSOR}" != "0" ]]; then
      AV_IMGDATA_FACE_PROCESSOR_ROOT="${PACKAGE_ROOT}/dist/av-imgdata-face-processor-windows-x86_64.package" \
      AV_IMGDATA_FACE_PROCESSOR_BIN="${PACKAGE_ROOT}/dist/av-imgdata-face-processor-windows-x86_64.package/bin/av-imgdata-face-processor.exe" \
      AV_IMGDATA_WORKER_BUILD_DIR="${PACKAGE_ROOT}/build/worker/windows-x86_64.package" \
      AV_IMGDATA_WORKER_DIST_DIR="${PACKAGE_ROOT}/dist/av-imgdata-worker-windows-x86_64.package" \
        bash tools/build-worker.sh --target "${target}" "${clean_args[@]}"
    else
      bash tools/build-worker.sh --target "${target}" "${clean_args[@]}"
    fi
    assert_worker_face_processor_bundled "${target}"
  done

  log "External worker bundles built: ${EXTERNAL_WORKER_TARGETS}"
}

usage() {
  cat <<'EOF'
Usage:
  tools/build-package.sh [PkgCreate.py options...]

Examples:
  tools/build-package.sh
  tools/build-package.sh -v 7.4 -p geminilake
  tools/build-package.sh -v 7.4 -p apollolake

The script always builds the av_imgdata package. If no arguments are passed,
it uses:
  -v 7.4 -p geminilake

External worker bundles are built by default before the Synology package build:
  linux-x86_64 docker-linux-x86_64 windows-x86_64

Environment overrides:
  AV_IMGDATA_BUILD_EXTERNAL_WORKERS=0   Skip external worker bundle builds
  AV_IMGDATA_PACKAGE_EXTERNAL_WORKERS=0 Skip embedding external worker archives in the DSM package
  AV_IMGDATA_WORKER_TARGETS="..."       Worker targets to build
  AV_IMGDATA_BUILD_LINUX_FACE_PROCESSOR=0
                                      Skip Linux face processor build
  AV_IMGDATA_BUILD_WINDOWS_FACE_PROCESSOR=0
                                      Skip Windows face processor build
  AV_IMGDATA_BUILD_WORKER_VIPS=0      Skip rebuilding worker libvips image processor and use existing artifacts only
  AV_IMGDATA_BUNDLE_WORKER_VIPS=0     Skip worker libvips image processor integration entirely
  AV_IMGDATA_LINUX_CHROOT=0           Build Linux worker libvips on the host instead of in build/chroot/linux-x86_64
  AV_IMGDATA_WORKER_CLEAN=0             Reuse worker build directories
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
cleanup_stale_generated_backup_roots

if [[ "$#" -gt 0 ]]; then
  cleanup_existing_toolkit_link_target "$@"
  cleanup_existing_image_packages "$@"
else
  cleanup_existing_toolkit_link_target "${DEFAULT_ARGS[@]}"
  cleanup_existing_image_packages "${DEFAULT_ARGS[@]}"
fi

[[ -d "tests" ]] || fail "Required directory not found: tests"
[[ -d "ui" ]] || fail "Required directory not found: ui"
[[ -f "${PKGCREATE}" ]] || fail "PkgCreate.py not found: ${PKGCREATE}"

log "Running structure checks"
python3 tools/check_syntax_and_structure.py

log "Running Python tests"
TEST_PKGVAR="$(mktemp -d)"
export SYNOPKG_PKGVAR="${TEST_PKGVAR}"
export PYTHONDONTWRITEBYTECODE=1

PYTHONPATH=src python3 -m pytest tests

assert_no_nobody_generated_paths
ensure_linux_native_deps
configure_noninteractive_linux_worker_vips_build
build_external_worker_bundles
assert_no_nobody_generated_paths

log "Temporarily moving local build artifacts out of the Toolkit link tree"
sanitize_project_for_toolkit_link

log "Building Synology package"
cd "${TOOLKIT_ROOT}"

if [[ "$#" -gt 0 ]]; then
  run_pkgcreate "$@"
else
  run_pkgcreate "${DEFAULT_ARGS[@]}"
fi

log "Package build completed"
