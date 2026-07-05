#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
BUILD_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}"
BUILD_DIR="${BUILD_ROOT}/vips-image-processor-build"
LIBVIPS_BUILD_DIR="${BUILD_ROOT}/libvips-build"
INSTALL_DIR="${BUILD_ROOT}/vips-image-processor-install"
VIPS_PREFIX="${INSTALL_DIR}/usr/local/AV_ImgData"
DEPS_ROOT="${BUILD_ROOT}/deps"
SOURCE_CACHE="${DEPS_ROOT}/source-cache"

LIBDE265_VERSION="${AV_IMGDATA_LIBDE265_VERSION:-1.0.16}"
LIBDE265_TARBALL="libde265-${LIBDE265_VERSION}.tar.gz"
LIBDE265_URL="${AV_IMGDATA_LIBDE265_URL:-https://github.com/strukturag/libde265/releases/download/v${LIBDE265_VERSION}/${LIBDE265_TARBALL}}"
LIBDE265_SHA256="${AV_IMGDATA_LIBDE265_SHA256:-b92beb6b53c346db9a8fae968d686ab706240099cdd5aff87777362d668b0de7}"
LIBDE265_SOURCE_PARENT="${BUILD_ROOT}/libde265-source"
LIBDE265_SOURCE_DIR="${LIBDE265_SOURCE_PARENT}/libde265-${LIBDE265_VERSION}"
LIBDE265_BUILD_DIR="${BUILD_ROOT}/libde265-build"

LIBHEIF_VERSION="${AV_IMGDATA_LIBHEIF_VERSION:-1.12.0}"
LIBHEIF_TARBALL="libheif-${LIBHEIF_VERSION}.tar.gz"
LIBHEIF_URL="${AV_IMGDATA_LIBHEIF_URL:-https://github.com/strukturag/libheif/releases/download/v${LIBHEIF_VERSION}/${LIBHEIF_TARBALL}}"
LIBHEIF_SHA256="${AV_IMGDATA_LIBHEIF_SHA256:-e1ac2abb354fdc8ccdca71363ebad7503ad731c84022cf460837f0839e171718}"
LIBHEIF_SOURCE_PARENT="${BUILD_ROOT}/libheif-source"
LIBHEIF_SOURCE_DIR="${LIBHEIF_SOURCE_PARENT}/libheif-${LIBHEIF_VERSION}"
LIBHEIF_BUILD_DIR="${BUILD_ROOT}/libheif-build"

LIBVIPS_VERSION="${AV_IMGDATA_LIBVIPS_VERSION:-8.16.1}"
LIBVIPS_TARBALL="vips-${LIBVIPS_VERSION}.tar.xz"
LIBVIPS_URL="${AV_IMGDATA_LIBVIPS_URL:-https://github.com/libvips/libvips/releases/download/v${LIBVIPS_VERSION}/${LIBVIPS_TARBALL}}"
LIBVIPS_SHA256="${AV_IMGDATA_LIBVIPS_SHA256:-d114d7c132ec5b45f116d654e17bb4af84561e3041183cd4bfd79abfb85cf724}"
LIBVIPS_SOURCE_PARENT="${BUILD_ROOT}/libvips-source"
LIBVIPS_SOURCE_DIR="${LIBVIPS_SOURCE_PARENT}/vips-${LIBVIPS_VERSION}"

rm -rf \
  "${BUILD_DIR}" \
  "${LIBDE265_BUILD_DIR}" \
  "${LIBDE265_SOURCE_PARENT}" \
  "${LIBHEIF_BUILD_DIR}" \
  "${LIBHEIF_SOURCE_PARENT}" \
  "${LIBVIPS_BUILD_DIR}" \
  "${INSTALL_DIR}" \
  "${LIBVIPS_SOURCE_PARENT}"
mkdir -p "${BUILD_DIR}" "${LIBDE265_BUILD_DIR}" "${LIBHEIF_BUILD_DIR}" "${LIBVIPS_BUILD_DIR}" "${INSTALL_DIR}" "${SOURCE_CACHE}"

require_tool() {
  local tool="$1"
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "ERROR: required tool not found: ${tool}" >&2
    exit 1
  fi
}

download_source_tarball() {
  local label="$1"
  local url="$2"
  local sha256="$3"
  local tarball_path="$4"

  if [ ! -f "${tarball_path}" ]; then
    require_tool curl
    echo "Downloading ${label} from ${url}"
    if ! curl -fL "${url}" -o "${tarball_path}"; then
      echo "WARNING: ${label} download failed with default TLS settings; retrying without CA verification." >&2
      curl -fkL "${url}" -o "${tarball_path}"
    fi
  fi

  if ! printf '%s  %s\n' "${sha256}" "${tarball_path}" | sha256sum -c - >/dev/null; then
    echo "WARNING: cached ${label} source checksum mismatch; downloading again: ${tarball_path}" >&2
    rm -f "${tarball_path}"
    if ! curl -fL "${url}" -o "${tarball_path}"; then
      echo "WARNING: ${label} download failed with default TLS settings; retrying without CA verification." >&2
      curl -fkL "${url}" -o "${tarball_path}"
    fi
    if ! printf '%s  %s\n' "${sha256}" "${tarball_path}" | sha256sum -c - >/dev/null; then
      echo "ERROR: ${label} source checksum mismatch: ${tarball_path}" >&2
      exit 1
    fi
  fi
}

download_libvips() {
  local tarball_path="${SOURCE_CACHE}/${LIBVIPS_TARBALL}"
  if [ ! -f "${tarball_path}" ]; then
    require_tool curl
    echo "Downloading libvips ${LIBVIPS_VERSION} from ${LIBVIPS_URL}"
    if ! curl -fL "${LIBVIPS_URL}" -o "${tarball_path}"; then
      echo "WARNING: libvips download failed with default TLS settings; retrying without CA verification." >&2
      curl -fkL "${LIBVIPS_URL}" -o "${tarball_path}"
    fi
  fi

  if ! printf '%s  %s\n' "${LIBVIPS_SHA256}" "${tarball_path}" | sha256sum -c - >/dev/null; then
    echo "WARNING: cached libvips source checksum mismatch; downloading again: ${tarball_path}" >&2
    rm -f "${tarball_path}"
    if ! curl -fL "${LIBVIPS_URL}" -o "${tarball_path}"; then
      echo "WARNING: libvips download failed with default TLS settings; retrying without CA verification." >&2
      curl -fkL "${LIBVIPS_URL}" -o "${tarball_path}"
    fi
    if ! printf '%s  %s\n' "${LIBVIPS_SHA256}" "${tarball_path}" | sha256sum -c - >/dev/null; then
      echo "ERROR: libvips source checksum mismatch: ${tarball_path}" >&2
      exit 1
    fi
  fi

  mkdir -p "${LIBVIPS_SOURCE_PARENT}"
  tar -xf "${tarball_path}" -C "${LIBVIPS_SOURCE_PARENT}"
}

download_heif_stack() {
  download_source_tarball "libde265 ${LIBDE265_VERSION}" "${LIBDE265_URL}" "${LIBDE265_SHA256}" "${SOURCE_CACHE}/${LIBDE265_TARBALL}"
  download_source_tarball "libheif ${LIBHEIF_VERSION}" "${LIBHEIF_URL}" "${LIBHEIF_SHA256}" "${SOURCE_CACHE}/${LIBHEIF_TARBALL}"

  mkdir -p "${LIBDE265_SOURCE_PARENT}" "${LIBHEIF_SOURCE_PARENT}"
  tar -xzf "${SOURCE_CACHE}/${LIBDE265_TARBALL}" -C "${LIBDE265_SOURCE_PARENT}"
  tar -xzf "${SOURCE_CACHE}/${LIBHEIF_TARBALL}" -C "${LIBHEIF_SOURCE_PARENT}"
}

install_heif_stack_license_files() {
  local license_dir="${VIPS_PREFIX}/share/licenses/AV_ImgData/heif-stack"
  mkdir -p "${license_dir}/sources"
  cp -a "${LIBDE265_SOURCE_DIR}/COPYING" "${license_dir}/libde265.COPYING"
  cp -a "${LIBHEIF_SOURCE_DIR}/COPYING" "${license_dir}/libheif.COPYING"
  cp -a "${SOURCE_CACHE}/${LIBDE265_TARBALL}" "${license_dir}/sources/${LIBDE265_TARBALL}"
  cp -a "${SOURCE_CACHE}/${LIBHEIF_TARBALL}" "${license_dir}/sources/${LIBHEIF_TARBALL}"
  cat > "${license_dir}/README.txt" <<EOF
AV_ImgData ships libheif and libde265 as dynamically linked shared libraries for HEIC decoding.

libheif ${LIBHEIF_VERSION}
Source: ${LIBHEIF_URL}
SHA256: ${LIBHEIF_SHA256}
License: LGPL, see libheif.COPYING

libde265 ${LIBDE265_VERSION}
Source: ${LIBDE265_URL}
SHA256: ${LIBDE265_SHA256}
License: LGPL, see libde265.COPYING

The packaged source tarballs are included under sources/.
EOF
}

build_heif_stack() {
  require_tool cmake
  require_tool make
  require_tool pkg-config

  download_heif_stack

  local synology_sysroot
  local synology_include_dir=""
  synology_sysroot="$(resolve_synology_toolchain_sysroot || true)"
  if [ -n "${synology_sysroot}" ]; then
    synology_include_dir="${synology_sysroot}/usr/include"
  fi

  echo "Building libde265 ${LIBDE265_VERSION} for HEIC decode support"
  cmake -S "${LIBDE265_SOURCE_DIR}" -B "${LIBDE265_BUILD_DIR}" \
    "-DCMAKE_BUILD_TYPE=Release" \
    "-DCMAKE_INSTALL_PREFIX=${VIPS_PREFIX}" \
    "-DCMAKE_INSTALL_LIBDIR=lib" \
    "-DBUILD_SHARED_LIBS=ON" \
    "-DENABLE_DECODER=OFF" \
    "-DENABLE_ENCODER=OFF" \
    "-DENABLE_SDL=OFF"
  make -C "${LIBDE265_BUILD_DIR}" -j"$(nproc 2>/dev/null || echo 2)"
  make -C "${LIBDE265_BUILD_DIR}" install

  export PKG_CONFIG_PATH="${VIPS_PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
  export LD_LIBRARY_PATH="${VIPS_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

  if ! pkg-config --exists libde265; then
    echo "ERROR: libde265 build did not install libde265.pc." >&2
    exit 1
  fi

  echo "Building libheif ${LIBHEIF_VERSION} with libde265 HEIC decoder and without x265 encoder"
  (
    cd "${LIBHEIF_SOURCE_DIR}"
    CPPFLAGS="-I${VIPS_PREFIX}/include${synology_include_dir:+ -I${synology_include_dir}}" \
    LDFLAGS="-L${VIPS_PREFIX}/lib" \
    PKG_CONFIG_PATH="${VIPS_PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}" \
    LD_LIBRARY_PATH="${VIPS_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    ./configure \
      "--prefix=${VIPS_PREFIX}" \
      "--libdir=${VIPS_PREFIX}/lib" \
      "--enable-shared" \
      "--disable-static" \
      "--disable-examples" \
      "--disable-go" \
      "--disable-aom" \
      "--disable-x265" \
      "--disable-gdk-pixbuf" \
      "--disable-rav1e"
  )
  make -C "${LIBHEIF_SOURCE_DIR}" -j"$(nproc 2>/dev/null || echo 2)"
  make -C "${LIBHEIF_SOURCE_DIR}" install

  if ! pkg-config --exists libheif; then
    echo "ERROR: libheif build did not install libheif.pc." >&2
    exit 1
  fi
  if ! grep -Eq '^builtin_h265_decoder=yes$' "${VIPS_PREFIX}/lib/pkgconfig/libheif.pc"; then
    echo "ERROR: libheif was built without the libde265 HEIC decoder." >&2
    exit 1
  fi
  if grep -Eq '^builtin_h265_encoder=yes$' "${VIPS_PREFIX}/lib/pkgconfig/libheif.pc"; then
    echo "ERROR: libheif unexpectedly enabled an H.265 encoder; x265/GPL must stay out of this package." >&2
    exit 1
  fi

  install_heif_stack_license_files
}

patch_libvips_source() {
  local meson_file="${LIBVIPS_SOURCE_DIR}/meson.build"
  local iofuncs_meson="${LIBVIPS_SOURCE_DIR}/libvips/iofuncs/meson.build"
  local dzsave_file="${LIBVIPS_SOURCE_DIR}/libvips/foreign/dzsave.c"
  local exif_file="${LIBVIPS_SOURCE_DIR}/libvips/foreign/exif.c"
  local type_file="${LIBVIPS_SOURCE_DIR}/libvips/iofuncs/type.c"
  local util_file="${LIBVIPS_SOURCE_DIR}/libvips/iofuncs/util.c"
  local vips_file="${LIBVIPS_SOURCE_DIR}/libvips/iofuncs/vips.c"
  local patched_iofuncs="${iofuncs_meson}.patched"
  local old_line="    if cc.get_define('COMPRESSION_WEBP', prefix: '#include <tiff.h>', dependencies: libtiff_dep) != ''"
  local new_line="    if cc.has_header_symbol('tiff.h', 'COMPRESSION_WEBP', dependencies: libtiff_dep)"

  if grep -Fq "${old_line}" "${meson_file}"; then
    sed -i "s|${old_line}|${new_line}|" "${meson_file}"
  elif ! grep -Fq "${new_line}" "${meson_file}"; then
    echo "ERROR: libvips meson COMPRESSION_WEBP probe not found in ${meson_file}" >&2
    exit 1
  fi

  sed -i \
    -e "s/^subdir('tools')/# AV_ImgData package build skips upstream libvips tools/" \
    -e "s/^subdir('test')/# AV_ImgData package build skips upstream libvips tests/" \
    -e "s/^subdir('fuzz')/# AV_ImgData package build skips upstream libvips fuzzers/" \
    "${meson_file}"
  if grep -Eq "^subdir\\('(tools|test|fuzz)'\\)" "${meson_file}"; then
    echo "ERROR: libvips meson tool/test/fuzz subdirs were not disabled." >&2
    exit 1
  fi

  if grep -Fq "vipsmarshal = gnome.genmarshal(" "${iofuncs_meson}"; then
    awk '
      /^vipsmarshal = gnome\.genmarshal\(/ {
        print "vipsmarshal_h = custom_target("
        print "    '\''vipsmarshal_h'\'',"
        print "    input: '\''vipsmarshal.list'\'',"
        print "    output: '\''vipsmarshal.h'\'',"
        print "    command: [ '\''sh'\'', '\''-c'\'', '\''glib-genmarshal --prefix=vips --header \"$1\" > \"$2\"'\'', '\''sh'\'', '\''@INPUT@'\'', '\''@OUTPUT@'\'' ],"
        print ")"
        print ""
        print "vipsmarshal_c = custom_target("
        print "    '\''vipsmarshal_c'\'',"
        print "    input: '\''vipsmarshal.list'\'',"
        print "    output: '\''vipsmarshal.c'\'',"
        print "    command: [ '\''sh'\'', '\''-c'\'', '\''glib-genmarshal --prefix=vips --body \"$1\" > \"$2\"'\'', '\''sh'\'', '\''@INPUT@'\'', '\''@OUTPUT@'\'' ],"
        print ")"
        print ""
        print "vipsmarshal = [vipsmarshal_h, vipsmarshal_c]"
        skip = 1
        next
      }
      skip && /^\)/ {
        skip = 0
        next
      }
      !skip { print }
    ' "${iofuncs_meson}" > "${patched_iofuncs}"
    mv "${patched_iofuncs}" "${iofuncs_meson}"
  elif ! grep -Fq "vipsmarshal_h = custom_target(" "${iofuncs_meson}"; then
    echo "ERROR: libvips vipsmarshal meson target not found in ${iofuncs_meson}" >&2
    exit 1
  fi

  # The Synology Toolkit GLib is older than libvips 8.16.1 expects. Keep the
  # libvips build on that runtime instead of linking newer sysroot GLib builds
  # that require a newer libc than the Toolkit linker can satisfy.
  sed -i \
    -e 's/g_utf8_make_valid(text, -1)/g_strdup(text)/' \
    "${exif_file}"
  sed -i \
    -e 's/g_utf8_make_valid(str, -1)/g_strdup(str)/' \
    "${type_file}"
  sed -i \
    -e 's/g_utf8_make_valid(vips_value_get_save_string(&save_value), -1)/g_strdup(vips_value_get_save_string(\&save_value))/' \
    "${vips_file}"
  sed -i \
    -e 's/#if GLIB_CHECK_VERSION(2, 62, 0)/#if 0 \&\& GLIB_CHECK_VERSION(2, 62, 0)/' \
    "${util_file}"
  sed -i \
    -e '/if (!(str = g_utf8_make_valid(/,+1c\	if (!(str = g_strdup(\n			  vips_value_get_save_string(&save_value)))) {' \
    "${dzsave_file}"

  if grep -R -Fq "g_utf8_make_valid" "${dzsave_file}" "${exif_file}" "${type_file}" "${vips_file}"; then
    echo "ERROR: libvips GLib compatibility patch did not remove all g_utf8_make_valid calls." >&2
    exit 1
  fi
  if grep -Fq "#if GLIB_CHECK_VERSION(2, 62, 0)" "${util_file}"; then
    echo "ERROR: libvips GLib compatibility patch did not disable g_date_time_format_iso8601." >&2
    exit 1
  fi
}

resolve_synology_toolchain_sysroot() {
  local env_file
  local value
  local candidate

  if [ -n "${AV_IMGDATA_SYNOLOGY_SYSROOT:-}" ] && [ -d "${AV_IMGDATA_SYNOLOGY_SYSROOT}" ]; then
    printf '%s\n' "${AV_IMGDATA_SYNOLOGY_SYSROOT}"
    return
  fi

  for env_file in /env64.mak /env.mak; do
    [ -f "${env_file}" ] || continue
    value="$(grep -E '^ToolChainSysRoot[[:space:]]*=' "${env_file}" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
    value="${value%$'\r'}"
    if [ -n "${value}" ] && [ -d "${value}" ]; then
      printf '%s\n' "${value}"
      return
    fi
  done

  for candidate in /usr/local/*/*/sys-root; do
    [ -d "${candidate}" ] || continue
    if [ -d "${candidate}/usr/include" ] && [ -d "${candidate}/usr/lib" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
}

patch_libvips_ninja_link_args() {
  local sysroot="$1"
  local libdir="${sysroot}/usr/lib"
  local ninja_file="${LIBVIPS_BUILD_DIR}/build.ninja"
  local patched_ninja="${ninja_file}.patched"
  local jpeg_lib
  local png16_lib
  local webp_lib
  local webpmux_lib
  local webpdemux_lib
  local tiff_lib
  local lcms2_lib

  [ -d "${libdir}" ] || return
  if [ ! -f "${ninja_file}" ]; then
    echo "ERROR: libvips ninja build file missing: ${ninja_file}" >&2
    exit 1
  fi

  jpeg_lib="$(resolve_synology_library_file "${libdir}" libjpeg)"
  png16_lib="$(resolve_synology_library_file "${libdir}" libpng16)"
  webp_lib="$(resolve_synology_library_file "${libdir}" libwebp)"
  webpmux_lib="$(resolve_synology_library_file "${libdir}" libwebpmux)"
  webpdemux_lib="$(resolve_synology_library_file "${libdir}" libwebpdemux)"
  tiff_lib="$(resolve_synology_library_file "${libdir}" libtiff)"
  lcms2_lib="$(resolve_synology_library_file "${libdir}" liblcms2)"

  awk \
    -v libdir="${libdir}" \
    -v jpeg_lib="${jpeg_lib}" \
    -v png16_lib="${png16_lib}" \
    -v webp_lib="${webp_lib}" \
    -v webpmux_lib="${webpmux_lib}" \
    -v webpdemux_lib="${webpdemux_lib}" \
    -v tiff_lib="${tiff_lib}" \
    -v lcms2_lib="${lcms2_lib}" '
    function patch_link_args(line,   prefix, args, n, i, token, out) {
      prefix = " LINK_ARGS = "
      args = substr(line, length(prefix) + 1)
      n = split(args, tokens, " ")
      out = prefix
      for (i = 1; i <= n; i++) {
        token = tokens[i]
        if (token ~ /^-Wl,--sysroot=/) {
          continue
        } else if (token == "-ljpeg") {
          token = jpeg_lib
        } else if (token == "-lpng16") {
          token = png16_lib
        } else if (token == "-lwebp") {
          token = webp_lib
        } else if (token == "-lwebpmux") {
          token = webpmux_lib
        } else if (token == "-lwebpdemux") {
          token = webpdemux_lib
        } else if (token == "-ltiff") {
          token = tiff_lib
        } else if (token == "-llcms2") {
          token = lcms2_lib
        } else if (token ~ "^" libdir "/libglib-2\\.0\\.so") {
          token = "-lglib-2.0"
        } else if (token ~ "^" libdir "/libgio-2\\.0\\.so") {
          token = "-lgio-2.0"
        } else if (token ~ "^" libdir "/libgobject-2\\.0\\.so") {
          token = "-lgobject-2.0"
        } else if (token == "-L" libdir) {
          continue
        }
        out = out (out == prefix ? "" : " ") token
      }
      return out
    }
    /^build .*: (c|cpp)_LINKER/ {
      in_dynamic_link = 1
      print
      next
    }
    in_dynamic_link && /^ LINK_ARGS = / {
      print patch_link_args($0)
      in_dynamic_link = 0
      next
    }
    in_dynamic_link && /^build / {
      in_dynamic_link = 0
    }
    { print }
  ' "${ninja_file}" > "${patched_ninja}"
  mv "${patched_ninja}" "${ninja_file}"

  if ! grep -Fq -- "${jpeg_lib}" "${ninja_file}"; then
    echo "ERROR: failed to patch Synology sysroot libraries into libvips ninja link args." >&2
    exit 1
  fi
}

resolve_synology_library_file() {
  local libdir="$1"
  local stem="$2"
  local candidate

  for candidate in "${libdir}/${stem}.so" "${libdir}/${stem}.a"; do
    if [ -e "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  for candidate in "${libdir}/${stem}.so".*; do
    if [ -e "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  echo "ERROR: required Synology sysroot library missing: ${libdir}/${stem}.so" >&2
  exit 1
}

build_libvips() {
  require_tool meson
  require_tool ninja
  require_tool pkg-config
  require_tool strings

  if ! pkg-config --exists libheif || ! grep -Eq '^builtin_h265_decoder=yes$' "${VIPS_PREFIX}/lib/pkgconfig/libheif.pc"; then
    echo "ERROR: libvips HEIC build requires packaged libheif with builtin libde265 decoder." >&2
    exit 1
  fi

  download_libvips
  patch_libvips_source

  local synology_sysroot
  local meson_args=(
    setup "${LIBVIPS_BUILD_DIR}" "${LIBVIPS_SOURCE_DIR}"
    "--prefix=${VIPS_PREFIX}"
    "--libdir=lib"
    "--buildtype=release"
    "--default-library=shared"
    "-Ddeprecated=false"
    "-Dexamples=false"
    "-Dcplusplus=false"
    "-Dmodules=disabled"
    "-Dintrospection=disabled"
    "-Djpeg=enabled"
    "-Dpng=enabled"
    "-Dtiff=enabled"
    "-Dwebp=enabled"
    "-Dzlib=enabled"
    "-Dlcms=enabled"
    "-Dmagick=disabled"
    "-Dheif=enabled"
    "-Dfftw=disabled"
    "-Dfontconfig=disabled"
    "-Darchive=disabled"
    "-Dcfitsio=disabled"
    "-Dcgif=disabled"
    "-Dexif=disabled"
    "-Dimagequant=disabled"
    "-Djpeg-xl=disabled"
    "-Dmatio=disabled"
    "-Dnifti=disabled"
    "-Dopenexr=disabled"
    "-Dopenjpeg=disabled"
    "-Dopenslide=disabled"
    "-Dhighway=disabled"
    "-Dorc=disabled"
    "-Dpangocairo=disabled"
    "-Dpdfium=disabled"
    "-Dpoppler=disabled"
    "-Dquantizr=disabled"
    "-Drsvg=disabled"
    "-Dspng=disabled"
    "-Dnsgif=false"
    "-Dppm=false"
    "-Danalyze=false"
    "-Dradiance=false"
    "-Dgtk_doc=false"
    "-Ddoxygen=false"
    "-Dvapi=false"
  )

  synology_sysroot="$(resolve_synology_toolchain_sysroot)"
  if [ -n "${synology_sysroot}" ]; then
    if [ -f "${synology_sysroot}/usr/include/jpeglib.h" ]; then
      echo "Using Synology sysroot headers for libvips: ${synology_sysroot}/usr/include"
      meson_args+=(
        "-Dc_args=-I${synology_sysroot}/usr/include"
      )
    fi
    if [ -d "${synology_sysroot}/usr/lib" ]; then
      echo "Using Synology sysroot libraries for libvips: ${synology_sysroot}/usr/lib"
      meson_args+=(
        "-Dc_link_args=-L${synology_sysroot}/usr/lib"
      )
    fi
  fi

  echo "Running meson setup for libvips ${LIBVIPS_VERSION}"
  meson "${meson_args[@]}"
  if [ -n "${synology_sysroot}" ]; then
    patch_libvips_ninja_link_args "${synology_sysroot}"
  fi
  meson compile -C "${LIBVIPS_BUILD_DIR}"
  meson install -C "${LIBVIPS_BUILD_DIR}"

  if [ ! -f "${VIPS_PREFIX}/lib/pkgconfig/vips.pc" ]; then
    echo "ERROR: libvips build did not install vips.pc." >&2
    exit 1
  fi
  if [ -z "$(find "${VIPS_PREFIX}/lib" -maxdepth 1 -name 'libvips.so*' -print -quit 2>/dev/null)" ]; then
    echo "ERROR: libvips build did not install libvips.so*." >&2
    exit 1
  fi
}

copy_library_family() {
  local pattern="$1"
  local target_dir="${VIPS_PREFIX}/lib"
  local dirs=(
    "${target_dir}"
    "/usr/lib"
    "/usr/lib64"
    "/usr/local/lib"
  )
  local dir
  local source
  local target

  for dir in /usr/local/*/*/sys-root/usr/lib; do
    dirs+=("${dir}")
  done

  mkdir -p "${target_dir}"
  for dir in "${dirs[@]}"; do
    [ -d "${dir}" ] || continue
    for source in "${dir}"/${pattern}; do
      [ -e "${source}" ] || continue
      target="${target_dir}/$(basename "${source}")"
      if [ "$(readlink -f "${source}")" = "$(readlink -f "${target}" 2>/dev/null || true)" ]; then
        continue
      fi
      if [ -e "${target}" ]; then
        continue
      fi
      cp -aL "${source}" "${target}"
    done
  done
}

copy_libvips_runtime_dependencies() {
  local patterns=(
    "libvips.so*"
    "libglib-2.0.so*"
    "libgobject-2.0.so*"
    "libgio-2.0.so*"
    "libgmodule-2.0.so*"
    "libgthread-2.0.so*"
    "libffi.so*"
    "libpcre.so*"
    "libmount.so*"
    "libblkid.so*"
    "libuuid.so*"
    "libexpat.so*"
    "libjpeg.so*"
    "libpng16.so*"
    "libtiff.so*"
    "libwebp.so*"
    "libwebpmux.so*"
    "libwebpdemux.so*"
    "libheif.so*"
    "libde265.so*"
    "liblcms2.so*"
    "libz.so*"
    "liblzma.so*"
  )
  local pattern

  for pattern in "${patterns[@]}"; do
    copy_library_family "${pattern}"
  done

  if [ -z "$(find "${VIPS_PREFIX}/lib" -maxdepth 1 -name 'libvips.so*' -print -quit 2>/dev/null)" ]; then
    echo "ERROR: libvips runtime library missing from ${VIPS_PREFIX}/lib." >&2
    exit 1
  fi
}

strip_native_binary() {
  local binary="$1"
  local strip_tool="${STRIP:-strip}"
  if ! command -v "${strip_tool}" >/dev/null 2>&1; then
    echo "WARNING: strip tool not found: ${strip_tool}; native binary remains unstripped." >&2
    return
  fi
  "${strip_tool}" --strip-unneeded "${binary}" || "${strip_tool}" "${binary}" || true
}

build_heif_stack
build_libvips
copy_libvips_runtime_dependencies

export PKG_CONFIG_PATH="${VIPS_PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LD_LIBRARY_PATH="${VIPS_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

cd "${BUILD_DIR}"
CMAKE_ARGS=(
  "${PROJECT_DIR}/processors/native/image_backend_vips"
  "-DCMAKE_BUILD_TYPE=Release"
  "-DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData"
)
if [ -n "${CC:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_C_COMPILER=${CC}")
fi
if [ -n "${CXX:-}" ]; then
  CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=${CXX}")
fi
cmake "${CMAKE_ARGS[@]}"
make -j"$(nproc 2>/dev/null || echo 2)"
make install DESTDIR="${INSTALL_DIR}"

NATIVE_BINARY="${VIPS_PREFIX}/bin/av-imgdata-image-processor"
if [ "${AV_IMGDATA_NATIVE_STRIP:-1}" != "0" ] && [ -x "${NATIVE_BINARY}" ]; then
  strip_native_binary "${NATIVE_BINARY}"
fi

if [ ! -x "${NATIVE_BINARY}" ]; then
  echo "ERROR: optional libvips image processor build did not produce an executable binary."
  exit 1
fi

if strings "${NATIVE_BINARY}" | grep -Eq '0\.1\.0-skeleton|libvips_not_linked'; then
  echo "ERROR: libvips image processor is only the skeleton binary; libvips is not linked."
  exit 1
fi

if ! PROBE_OUTPUT="$("${NATIVE_BINARY}" probe 2>&1)"; then
  if printf '%s\n' "${PROBE_OUTPUT}" | grep -Eq 'GLIBC_[0-9.]+|version `GLIBC_|version .*GLIBC_'; then
    echo "WARNING: libvips image processor runtime probe skipped: Toolkit build runtime is older than packaged Synology sysroot libraries." >&2
    echo "${PROBE_OUTPUT}" >&2
  else
    echo "ERROR: libvips image processor probe failed."
    echo "${PROBE_OUTPUT}"
    exit 1
  fi
fi
