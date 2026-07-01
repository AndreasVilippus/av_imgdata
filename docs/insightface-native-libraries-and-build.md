# Native Face Processor Libraries And Toolkit Build Concept

## Purpose

This document evaluates the required C/C++ libraries for replacing the optional `InsightFace` / `OpenCV` / `ONNXRuntime` Python wheelhouse block with native package-shipped processor binaries.

It also defines a detailed build process that fits the existing Synology Toolkit workflow:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The first implementation targets the currently supported DSM platform only. Additional platforms remain optional and additive.

## Current Build Assumptions

```text
- A Linux machine already contains the Synology Toolkit.
- The project is located at toolkit/source/av_imgdata.
- tools/build-package.sh is the canonical build entrypoint.
- build-package.sh runs structure checks and Python tests.
- build-package.sh forwards options to pkgscripts-ng/PkgCreate.py.
- The final SPK is collected under result_spk/.
- Current mandatory target is one DSM platform, e.g. geminilake.
```

The native processor build must not introduce a second mandatory build path.

## Required Native Function Blocks

Replacing the Python optional stack requires these blocks:

```text
1. CLI and process contract
2. JSON input/output
3. image decoding
4. image orientation/preprocessing
5. tensor preparation
6. inference runtime
7. face detector model runner
8. face embedding model runner
9. result normalization
10. diagnostics and self-test
```

The native processor must not own DSM workflow logic.

## Recommended Library Set

### Mandatory first-stage libraries

| Function | Recommended library | License | Include in first POC | Reason |
|---|---|---|---:|---|
| C++ standard runtime | Toolkit compiler/runtime | Toolchain/runtime dependent | Yes | Required for C++ processor. |
| JSON input/output | `nlohmann/json` header-only or equivalent small parser | MIT | Yes | Simple, portable, no runtime library. |
| JPEG decode | `libjpeg-turbo` | BSD-style / IJG / zlib-style combination | Yes | Fast, common, good first image format. |
| Inference | `ONNXRuntime` C API | MIT | Yes, after skeleton | Closest native replacement for current `onnxruntime` Python dependency. |
| Model I/O and filesystem | C++ stdlib | C++ runtime | Yes | Avoid extra dependencies. |

### Add only when required by fixtures

| Function | Candidate library | License | Add when |
|---|---|---|---|
| PNG decode | `libpng` + `zlib` | libpng/zlib | Supported face workflows require PNG. |
| TIFF decode | `libtiff` | BSD-like | TIFF face inference is required. |
| EXIF orientation | `exiv2` or minimal custom EXIF reader | GPL/commercial concerns for Exiv2 depending version; custom reader preferred | Native processor must handle orientation itself. |
| HEIF/HEIC | `libheif` + codec libs | Mixed; can pull LGPL/GPL/patent-sensitive codecs | Only after separate license review. |
| Full image processing | OpenCV C++ | Apache-2.0 | Only if narrow image layer is insufficient. |
| Lightweight inference alternative | ncnn / MNN / OpenCV DNN | Varies; verify per version | Only if ONNXRuntime Toolkit build fails or is too large. |

## Preferred Dependency Direction

Use the smallest dependency set that preserves behavior:

```text
Preferred first implementation:
  nlohmann/json
  libjpeg-turbo
  ONNXRuntime C API
  C++ standard library

Avoid initially:
  full OpenCV
  HEIF/HEIC stack
  TIFF stack
  Exiv2
  dynamic plugin ecosystems
```

Rationale:

```text
- Current Python OpenCV wheel is broad and conflict-prone.
- We likely need only image load, resize, color conversion, normalization.
- A narrow image layer is easier to build in the Toolkit.
- ONNXRuntime is the true functional replacement for model execution.
```

## License Assessment

### Current Python block

Current Python optional block:

```text
insightface
onnxruntime==1.16.3
opencv-python-headless==4.10.0.84
urllib3<2
```

The native plan does not automatically worsen licensing if the chosen C/C++ dependencies remain permissive.

### Proposed first-stage licenses

| Component | License impact | Obligations |
|---|---|---|
| Project C++ code | project license | Keep project license unchanged. |
| ONNXRuntime C API | MIT | Include copyright/license notice. |
| nlohmann/json | MIT | Include copyright/license notice. |
| libjpeg-turbo | BSD-style / IJG / zlib-style terms | Include required notices; binary distributions need documentation notice. |
| zlib if used | zlib | Keep notice; no source disclosure requirement. |
| libpng if used | libpng/zlib-style | Keep notice; no source disclosure requirement. |
| OpenCV if used | Apache-2.0 | Include license and NOTICE if applicable; patent grant/termination terms apply. |

### License change summary

```text
If we use ONNXRuntime + nlohmann/json + libjpeg-turbo:
  licensing remains permissive.
  no copyleft source disclosure is introduced.
  package must include third-party notices.

If we add OpenCV:
  Apache-2.0 is permissive, but NOTICE/license handling becomes more explicit.

If we add HEIF/HEIC or Exiv2:
  license and patent risk increases and must be reviewed separately before inclusion.
```

### Required package notice file

Add a package notice file:

```text
package/THIRD_PARTY_NOTICES/native-face-processor.md
```

It should list:

```text
- component name
- version / commit
- license
- source URL
- build mode: static or dynamic
- whether shipped in SPK
- copyright text
- required attribution text
```

At package build time, copy it to:

```text
/var/packages/AV_ImgData/target/THIRD_PARTY_NOTICES/native-face-processor.md
```

The UI status page may expose the notice path.

## Libraries To Avoid In The First Native Build

### Full OpenCV

OpenCV is not forbidden, but it should not be the first dependency.

Reasons:

```text
- large build surface
- many optional modules
- more transitive dependencies
- longer Toolkit build
- larger SPK
- easy to accidentally include unneeded codecs/features
```

Use OpenCV only if fixture parity proves that the narrow image layer is insufficient.

### HEIF/HEIC stack

Do not include in first build.

Reasons:

```text
- codec licensing can become complex
- patent-sensitive codecs may be pulled in
- platform build complexity is high
- not required for first parity proof unless current face workflow depends on HEIC input
```

### Exiv2

Avoid first.

Reason:

```text
EXIF orientation can be handled with a small targeted reader or by preserving existing backend metadata/orientation handling.
```

Do not introduce Exiv2 until its version-specific license and linkage model are reviewed.

## Native Build Modes

### Recommended first mode: dynamic internal libs

Use package-local shared libraries for heavy dependencies:

```text
target/bin/av-imgdata-face-processor
target/lib/libonnxruntime.so
target/lib/libjpeg.so or libturbojpeg.so if shipped
target/lib/libpng.so only if shipped
target/lib/libz.so only if shipped
```

Set runtime lookup so the binary uses package-local libs:

```text
-Wl,-rpath,'$ORIGIN/../lib'
```

Advantages:

```text
- smaller binary
- easier dependency inspection
- easier license inventory
- can replace one shared lib if needed
```

### Alternative: mostly static linking

Use only if dynamic linking is problematic in DSM.

Caution:

```text
- static linking increases binary size
- static linking can change license notice obligations
- static linking makes dependency inventory less visible
```

## Proposed Source Layout

```text
processors/native/face_processor/
  CMakeLists.txt
  cmake/
    ToolchainSynology.cmake
    FindOnnxRuntime.cmake
    LicenseInventory.cmake
  src/
    main.cpp
    cli.cpp
    json_io.cpp
    image_loader_jpeg.cpp
    image_preprocess.cpp
    onnx_session.cpp
    face_detect.cpp
    face_embed.cpp
    result_writer.cpp
    errors.cpp
  include/
    av_imgdata_face_processor/
  tests/
    fixtures/
  third_party/
    nlohmann_json/
```

Dependency source/cache layout:

```text
native_deps/
  sources/
    onnxruntime-<version>.tar.gz
    libjpeg-turbo-<version>.tar.gz
    libpng-<version>.tar.gz       # optional later
    zlib-<version>.tar.gz         # optional later
  patches/
    onnxruntime/
    libjpeg-turbo/
  licenses/
    ONNXRUNTIME_LICENSE
    LIBJPEG_TURBO_LICENSE
    NLOHMANN_JSON_LICENSE
    ZLIB_LICENSE
    LIBPNG_LICENSE
```

Do not download dependency sources during normal package build. Keep dependency source archives pinned and checksummed, or provide a controlled preparation command that is separate from `build-package.sh`.

## Build Process Overview

Normal user command remains:

```bash
cd toolkit
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Build sequence:

```text
1. build-package.sh parses flags.
2. build-package.sh runs existing structure checks.
3. build-package.sh runs Python tests.
4. build-package.sh validates native dependency source/cache if native build is enabled.
5. build-package.sh forwards options to pkgscripts-ng/PkgCreate.py.
6. PkgCreate.py runs SynoBuildConf/build inside Toolkit platform environment.
7. SynoBuildConf/build calls tools/build-native-face-processor.sh.
8. Native dependency libs are built or reused from build cache for the selected platform.
9. av-imgdata-face-processor is built and linked.
10. SynoBuildConf/install packages binary, libs, and notices into the SPK.
11. result_spk/ receives the final SPK.
```

## Build Flags

Add optional environment or wrapper flags:

```bash
AV_IMGDATA_NATIVE_FACE=0|1
AV_IMGDATA_NATIVE_FACE_DEPS=reuse|build
AV_IMGDATA_NATIVE_FACE_ONNX=0|1
AV_IMGDATA_NATIVE_FACE_OPENCV=0|1
```

Recommended defaults:

```text
Initial phase:
  AV_IMGDATA_NATIVE_FACE=0

Skeleton proof phase:
  AV_IMGDATA_NATIVE_FACE=1
  AV_IMGDATA_NATIVE_FACE_ONNX=0
  AV_IMGDATA_NATIVE_FACE_OPENCV=0

Inference proof phase:
  AV_IMGDATA_NATIVE_FACE=1
  AV_IMGDATA_NATIVE_FACE_ONNX=1
  AV_IMGDATA_NATIVE_FACE_OPENCV=0
```

The wrapper may later expose user-facing flags:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake --native-face=on
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake --native-face=off
```

Internally these map to `AV_IMGDATA_NATIVE_FACE`.

## Native Dependency Build Stages

### Stage 0: Dependency inventory validation

Script:

```text
tools/native/check-native-deps.sh
```

Responsibilities:

```text
- verify source archives exist
- verify SHA256 checksums
- verify license files exist
- verify platform allowlist contains requested platform if native build is on
- fail before invoking Toolkit build if dependency cache is incomplete
```

### Stage 1: Build libjpeg-turbo

Script:

```text
tools/native/build-libjpeg-turbo.sh
```

Output:

```text
build/native/${SYNO_PLATFORM}/deps/libjpeg-turbo/install/
  include/
  lib/
```

Recommended CMake flags:

```bash
cmake <src> \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local/AV_ImgData/native-deps \
  -DENABLE_SHARED=ON \
  -DENABLE_STATIC=OFF \
  -DWITH_JPEG8=1 \
  -DWITH_SIMD=0
```

`WITH_SIMD=0` for first build avoids CPU-instruction surprises. SIMD can be enabled per platform later after runtime tests.

### Stage 2: Build ONNXRuntime

Script:

```text
tools/native/build-onnxruntime.sh
```

Output:

```text
build/native/${SYNO_PLATFORM}/deps/onnxruntime/install/
  include/onnxruntime_c_api.h
  lib/libonnxruntime.so
```

Recommended build strategy:

```text
- CPU backend only
- no Python bindings
- no training APIs
- no tests in package build
- no CUDA/TensorRT/OpenVINO
- no telemetry
- minimal operator set only after model requirements are known
```

Candidate build options need verification against the pinned ONNXRuntime version. Final flags must be recorded in `docs/native-dependency-versions.md`.

### Stage 3: Optional libpng/zlib

Only after PNG support is required by fixtures.

Output:

```text
build/native/${SYNO_PLATFORM}/deps/zlib/install/
build/native/${SYNO_PLATFORM}/deps/libpng/install/
```

### Stage 4: Build face processor

Script:

```text
tools/build-native-face-processor.sh
```

Inputs:

```text
- Toolkit compiler variables
- dependency install prefixes
- processor source
- platform name
```

Output:

```text
build/native/${SYNO_PLATFORM}/face_processor-install/usr/local/AV_ImgData/
  bin/av-imgdata-face-processor
  lib/<package-local libs if any>
```

## CMake Contract

Minimum `CMakeLists.txt` expectations:

```cmake
cmake_minimum_required(VERSION 3.16)
project(av_imgdata_face_processor LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(AV_IMGDATA_ENABLE_ONNXRUNTIME "Enable ONNXRuntime backend" OFF)
option(AV_IMGDATA_ENABLE_PNG "Enable PNG decoding" OFF)
option(AV_IMGDATA_ENABLE_OPENCV "Enable OpenCV backend" OFF)

add_executable(av-imgdata-face-processor
  src/main.cpp
  src/cli.cpp
  src/json_io.cpp
  src/image_loader_jpeg.cpp
  src/image_preprocess.cpp
  src/result_writer.cpp
  src/errors.cpp
)

if(AV_IMGDATA_ENABLE_ONNXRUNTIME)
  target_sources(av-imgdata-face-processor PRIVATE src/onnx_session.cpp src/face_detect.cpp src/face_embed.cpp)
  target_include_directories(av-imgdata-face-processor PRIVATE ${ONNXRUNTIME_INCLUDE_DIR})
  target_link_libraries(av-imgdata-face-processor PRIVATE ${ONNXRUNTIME_LIBRARY})
endif()

target_link_libraries(av-imgdata-face-processor PRIVATE jpeg)

target_link_options(av-imgdata-face-processor PRIVATE "-Wl,-rpath,$ORIGIN/../lib")

install(TARGETS av-imgdata-face-processor RUNTIME DESTINATION bin)
```

## SynoBuildConf Integration

### `SynoBuildConf/build`

Conceptual insertion:

```bash
#!/bin/bash
set -euo pipefail

# existing build steps remain

if [ "${AV_IMGDATA_NATIVE_FACE:-0}" = "1" ]; then
  ./tools/native/check-native-deps.sh
  ./tools/native/build-native-deps.sh
  ./tools/build-native-face-processor.sh
fi

# existing UI/package build continues
```

### `SynoBuildConf/install`

Package copy concept:

```bash
NATIVE_ROOT="build/native/${SYNO_PLATFORM}/face_processor-install/usr/local/AV_ImgData"
NOTICE_SRC="package/THIRD_PARTY_NOTICES/native-face-processor.md"

if [ -x "${NATIVE_ROOT}/bin/av-imgdata-face-processor" ]; then
  mkdir -p "${PKG_DEST}/bin"
  cp -av "${NATIVE_ROOT}/bin/av-imgdata-face-processor" "${PKG_DEST}/bin/"
fi

if [ -d "${NATIVE_ROOT}/lib" ]; then
  mkdir -p "${PKG_DEST}/lib"
  cp -av "${NATIVE_ROOT}/lib/"* "${PKG_DEST}/lib/" || true
fi

if [ -f "${NOTICE_SRC}" ]; then
  mkdir -p "${PKG_DEST}/THIRD_PARTY_NOTICES"
  cp -av "${NOTICE_SRC}" "${PKG_DEST}/THIRD_PARTY_NOTICES/native-face-processor.md"
fi
```

Use the existing package assembly variables from the real `SynoBuildConf/install`; do not invent a parallel package root.

## Link And Runtime Validation

Add build validation script:

```text
tools/native/validate-native-face-artifact.sh
```

Checks:

```text
- binary exists
- binary is executable
- file reports target ELF architecture
- readelf -d shows expected RPATH or RUNPATH
- no dependency resolves to unexpected host path
- package-local libs are copied if required
- third-party notice file exists
- binary size is within configured maximum
```

Toolkit-side validation cannot fully execute the target binary when cross-compiling. Runtime validation must happen on a matching DSM device or emulator-equivalent environment.

## Runtime Integration

The backend invokes:

```text
${SYNOPKG_PKGDEST}/bin/av-imgdata-face-processor version
${SYNOPKG_PKGDEST}/bin/av-imgdata-face-processor probe --model-root ... --model-name ...
${SYNOPKG_PKGDEST}/bin/av-imgdata-face-processor detect --input ... --output ... --workdir ...
```

Set runtime library path only for the subprocess:

```python
processor_env = os.environ.copy()
processor_env["LD_LIBRARY_PATH"] = f"{pkgdest}/lib:" + processor_env.get("LD_LIBRARY_PATH", "")
```

Prefer RPATH/RUNPATH over global `LD_LIBRARY_PATH` where possible.

## Platform Policy

The first native processor build is required only for the current platform.

Platform status values:

```text
native_face_supported
native_face_disabled
native_face_unavailable_for_platform
native_face_binary_missing
native_face_probe_failed
native_face_ready
```

For optional platforms without native artifacts:

```text
- package build may still succeed
- native face processor capability is disabled
- wheelhouse or external worker can remain optional fallback
```

## Build Acceptance Criteria

### Skeleton phase

```text
- build-package.sh works with AV_IMGDATA_NATIVE_FACE=1
- SPK contains bin/av-imgdata-face-processor
- version command works on target DSM
- self-test without model works on target DSM
- third-party notice file is included
```

### JPEG phase

```text
- JPEG fixture decodes
- preprocessing produces expected width/height/channels
- corrupt JPEG returns structured error
- no full OpenCV dependency is present
```

### Inference phase

```text
- ONNXRuntime C API links
- required shared libs are package-local or known system libs
- detector model loads
- embedding model loads if required
- output schema validates
```

### Replacement phase

```text
- Python InsightFace path and native path pass fixture parity tests
- native status replaces pip import status for supported platform
- package startup no longer performs InsightFace/OpenCV/ONNXRuntime pip install for supported platform
- UI shows native processor readiness and model status
```

## License Acceptance Criteria

```text
- every shipped third-party binary/library has a recorded license
- every statically linked third-party component is recorded
- package includes THIRD_PARTY_NOTICES/native-face-processor.md
- Apache-2.0 NOTICE obligations are handled if OpenCV is included
- libjpeg-turbo IJG/BSD notice requirements are included if libjpeg-turbo is shipped or statically linked
- model license is separate and visible
- no GPL/LGPL/patent-sensitive codec is included without explicit review
```

## Recommended First Implementation

```text
1. Add native processor skeleton with nlohmann/json only.
2. Build skeleton through tools/build-package.sh with AV_IMGDATA_NATIVE_FACE=1.
3. Package binary and notice file.
4. Add backend status probe.
5. Add libjpeg-turbo JPEG decode.
6. Add ONNXRuntime C API build only after skeleton and JPEG phase pass.
7. Keep OpenCV out unless parity fails without it.
8. Keep HEIF/HEIC and Exiv2 out of scope until separate review.
```

## Final Decision

Use this dependency plan for the first native replacement path:

```text
Required first:
  C++17
  nlohmann/json or equivalent small JSON parser
  libjpeg-turbo

Required for real model execution:
  ONNXRuntime C API

Optional later:
  libpng + zlib
  OpenCV C++ minimal modules

Avoid initially:
  full OpenCV
  HEIF/HEIC codec stack
  Exiv2
  custom ONNX inference implementation
```

This keeps the licensing permissive, the Toolkit build manageable, and the first supported platform aligned with the already platform-specific wheelhouse policy.
