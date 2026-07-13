#!/bin/bash
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHROOT_ROOT="${AV_IMGDATA_LINUX_CHROOT_ROOT:-${PROJECT_DIR}/build/chroot/linux-x86_64}"
CHROOT_SUITE="${AV_IMGDATA_LINUX_CHROOT_SUITE:-bookworm}"
CHROOT_MIRROR="${AV_IMGDATA_LINUX_CHROOT_MIRROR:-http://deb.debian.org/debian}"
BUILD_PLATFORM="${AV_IMGDATA_NATIVE_PLATFORM:-linux-x86_64}"
CHROOT_WORKDIR="${PROJECT_DIR}"
APT_MARKER="${CHROOT_ROOT}/.av-imgdata-build-deps-installed"

usage() {
  cat <<'EOF'
Usage: tools/build-native-image-processor-vips-linux-chroot.sh [options]

Options:
  --clean-chroot   Remove the chroot before recreating it
  -h, --help       Show this help

Environment:
  AV_IMGDATA_LINUX_CHROOT_ROOT    Default: build/chroot/linux-x86_64
  AV_IMGDATA_LINUX_CHROOT_SUITE   Default: bookworm
  AV_IMGDATA_LINUX_CHROOT_MIRROR  Default: http://deb.debian.org/debian
  AV_IMGDATA_NATIVE_PLATFORM      Default: linux-x86_64

The script keeps Linux libvips build dependencies inside a chroot. It bind-mounts
the project directory and runs tools/build-native-image-processor-vips.sh as the
calling UID/GID, so generated build artifacts stay owned by the local user.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --clean-chroot)
      if [ -d "${CHROOT_ROOT}" ]; then
        sudo rm -rf "${CHROOT_ROOT}"
      fi
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

sudo_chroot() {
  sudo chroot "${CHROOT_ROOT}" "$@"
}

ensure_chroot() {
  require_command sudo
  require_command mountpoint

  if [ ! -x "${CHROOT_ROOT}/bin/bash" ]; then
    require_command debootstrap
    mkdir -p "$(dirname "${CHROOT_ROOT}")"
    sudo debootstrap --variant=minbase "${CHROOT_SUITE}" "${CHROOT_ROOT}" "${CHROOT_MIRROR}"
  fi

  if [ -f /etc/resolv.conf ]; then
    sudo cp -L /etc/resolv.conf "${CHROOT_ROOT}/etc/resolv.conf"
  fi
}

ensure_build_dependencies() {
  if [ -f "${APT_MARKER}" ]; then
    return 0
  fi

  sudo_chroot env DEBIAN_FRONTEND=noninteractive apt-get update
  sudo_chroot env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    ninja-build \
    meson \
    pkg-config \
    curl \
    xz-utils \
    tar \
    gzip \
    file \
    binutils \
    python3 \
    make \
    libglib2.0-dev \
    libexpat1-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    liblcms2-dev \
    zlib1g-dev \
    liblzma-dev \
    libffi-dev \
    libmount-dev \
    uuid-dev
  sudo touch "${APT_MARKER}"
}

mount_project() {
  local target="${CHROOT_ROOT}${PROJECT_DIR}"
  sudo mkdir -p "${target}"
  if ! mountpoint -q "${target}"; then
    sudo mount --bind "${PROJECT_DIR}" "${target}"
  fi
}

unmount_project() {
  local target="${CHROOT_ROOT}${PROJECT_DIR}"
  if mountpoint -q "${target}"; then
    sudo umount "${target}"
  fi
}

run_build_inside_chroot() {
  local uid
  local gid
  uid="$(id -u)"
  gid="$(id -g)"
  sudo chroot --userspec="${uid}:${gid}" "${CHROOT_ROOT}" /bin/bash -lc \
    "cd '${CHROOT_WORKDIR}' && HOME=/tmp AV_IMGDATA_NATIVE_PLATFORM='${BUILD_PLATFORM}' AV_IMGDATA_IN_LINUX_CHROOT=1 bash tools/build-native-image-processor-vips.sh"
}

ensure_chroot
ensure_build_dependencies
mount_project
trap unmount_project EXIT
run_build_inside_chroot
