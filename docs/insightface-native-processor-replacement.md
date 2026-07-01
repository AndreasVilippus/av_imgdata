# Native Replacement Concept For InsightFace / OpenCV / ONNXRuntime

## Purpose

This document defines a concrete replacement concept for the optional Python-based `InsightFace` / `OpenCV` / `ONNXRuntime` block.

The target is to replace the runtime `pip`/wheelhouse installation path with small package-shipped native C/C++ processor binaries built inside the Synology DSM Toolkit build process.

The replacement must preserve at least the same package-level functionality. It must not require a compiler, Python wheel installation, model download, or manual runtime setup on the NAS.

## Current State

The optional InsightFace block is currently represented as Python package dependencies:

```text
insightface
onnxruntime==1.16.3
opencv-python-headless==4.10.0.84
urllib3<2
```

The package start script currently supports:

```text
- optional wheelhouse manifest download
- wheel hash verification
- pip installation from wheelhouse
- OpenCV conflict cleanup
- forced reinstall of opencv-python-headless
- runtime import validation for cv2, onnxruntime, and insightface.app
- visible pip package status
```

This proves that the optional block is not just OpenCV. The functional unit is:

```text
image loading / preprocessing
+ face detection / recognition model execution
+ result normalization
+ package-visible status and diagnostics
```

A valid replacement must therefore replace the whole execution block, not only the `cv2` import.

## Decision Summary

Adopt this direction:

```text
Replace Python InsightFace/OpenCV/ONNXRuntime on DSM
with a native C/C++ processor suite built by Synology Toolkit.
```

The DSM backend remains the workflow and status owner.

The native processor does not write to DSM metadata, Synology Photos, config, runtime state, or findings storage directly. It only returns structured `ProcessorResult` JSON and optional artifacts.

## Feasibility Summary

| Area | Feasibility | Assessment |
|---|---:|---|
| Replacing runtime pip/wheelhouse install | High | Very sensible. Removes startup fragility and dynamic dependency installation. |
| Replacing `cv2` import with native image/preprocess binary | High | Feasible if image codec scope is controlled and tested. |
| Replacing InsightFace Python orchestration | Medium | Feasible if exact model inputs/outputs and normalization are defined. |
| Replacing ONNXRuntime with custom inference code | Low | Not sensible. A real inference runtime is still required. |
| Building ONNXRuntime C/C++ for all DSM platforms inside Toolkit | Medium to Low | Feasible for selected platforms, but high effort and must be proven per architecture. |
| Guaranteeing identical numeric output across all architectures | Medium to Low | Must allow tolerances for floating-point differences. |
| Supporting all current package-level behavior | Medium | Feasible if the processor contract is defined first and optional status behavior is preserved. |

Conclusion:

```text
The replacement is sensible if implemented as a native processor suite with a strict contract.
It is not sensible as a manual rewrite of ONNXRuntime or as a broad native rewrite of DSM workflows.
```

## Minimum Same-Functionality Requirement

The replacement must support the same package-level capabilities currently expected from the optional InsightFace block.

Required capabilities:

```text
- report whether native face processor is available
- report processor version
- report model availability
- validate configured model path/name
- load image input from a DSM-staged local file
- perform required image decoding and preprocessing
- run face detection model
- run face embedding/recognition model if current workflow requires embeddings
- return bounding boxes, landmarks where needed, confidence scores, and embeddings where needed
- return deterministic structured errors
- return output in ProcessorResult JSON
- allow DSM backend to continue owning final matching, findings, status, and writes unless explicitly moved behind contract later
```

Not required from the native processor:

```text
- DSM authentication
- Photos API access
- person creation
- face assignment
- metadata writes
- findings persistence
- runtime status aggregation
- worker registration
- UI state decisions
```

## Proposed Native Processor Suite

Build one binary first, split later only if needed:

```text
package/bin/av-imgdata-face-processor
```

Supported commands:

```text
av-imgdata-face-processor version
av-imgdata-face-processor probe --model-root <path> --model-name <name>
av-imgdata-face-processor detect --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor embed --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor self-test --fixtures <dir>
```

Optional later split:

```text
package/bin/av-imgdata-image-probe
package/bin/av-imgdata-face-detect
package/bin/av-imgdata-face-embed
```

Start with one binary to keep packaging and diagnostics simple.

## Processor Contract

The native processor must use the shared `processor_contract/` directory.

Input example:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "face_native_detect",
  "input": {
    "image_path": "/tmp/av-imgdata-job-123/input.jpg",
    "source_id": "dsm-item-456"
  },
  "options": {
    "model_root": "/var/packages/AV_ImgData/var/models",
    "model_name": "buffalo_l",
    "min_confidence": 0.5,
    "max_faces": 0,
    "normalize_coordinates": true
  }
}
```

Result example:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "face_native_detect",
  "status": "completed",
  "processor": {
    "name": "av-imgdata-face-processor",
    "version": "0.1.0",
    "backend": "onnxruntime-capi"
  },
  "result": {
    "faces": [
      {
        "face_id": "local-1",
        "confidence": 0.9821,
        "box": {
          "x": 0.1234,
          "y": 0.2345,
          "width": 0.1111,
          "height": 0.2222,
          "unit": "normalized"
        },
        "landmarks": [
          {"x": 0.14, "y": 0.26},
          {"x": 0.18, "y": 0.26},
          {"x": 0.16, "y": 0.29},
          {"x": 0.145, "y": 0.32},
          {"x": 0.18, "y": 0.32}
        ],
        "embedding": {
          "model": "buffalo_l",
          "dimension": 512,
          "encoding": "float32-le-base64",
          "value": "..."
        }
      }
    ]
  },
  "warnings": []
}
```

Error example:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "face_native_detect",
  "status": "failed",
  "error": {
    "code": "MODEL_NOT_FOUND",
    "message": "configured model file is missing",
    "retryable": false,
    "phase": "model_load"
  }
}
```

## Native Implementation Design

### Binary layer

```text
processors/native/face_processor/
  CMakeLists.txt
  src/
    main.cpp
    cli.cpp
    json_io.cpp
    image_loader.cpp
    image_preprocess.cpp
    onnx_session.cpp
    face_detect.cpp
    face_embed.cpp
    result_writer.cpp
    errors.cpp
  include/
  tests/
  fixtures/
  third_party/
```

### Runtime dependencies

Preferred dependency model:

```text
- C++17 or C++20
- small JSON library vendored or built as source
- ONNXRuntime C API if inference is required
- minimal image decoding/preprocessing dependency set
- no Python dependency
- no pip dependency
- no runtime model download
```

### Image decoding strategy

Full OpenCV is expensive. The native replacement should not automatically rebuild all of OpenCV unless required.

Preferred path:

```text
1. Implement a narrow image loading/preprocessing layer.
2. Use small codec libraries where possible.
3. Only build/link OpenCV if fixtures prove the package needs image formats or transforms that the narrow layer cannot provide.
```

Candidate codec handling:

| Format | Preferred path | Notes |
|---|---|---|
| JPEG/JPG | libjpeg-turbo or toolkit-provided jpeg library | High priority. |
| PNG | libpng or toolkit-provided png library | Medium priority. |
| TIFF | libtiff if currently required for native face processing | Verify before including. |
| HEIC/HEIF | external tool or optional codec only if proven required | Often high dependency burden. |
| RAW formats | not first target for face inference | Usually metadata path, not face inference input. |

### Inference strategy

Do not implement ONNX inference manually.

Candidate options:

| Option | Feasibility | Notes |
|---|---:|---|
| ONNXRuntime C API | Medium | Best functional match to current ONNXRuntime block, but cross-platform build must be proven. |
| OpenCV DNN | Medium | May reduce one dependency if OpenCV is already needed; model compatibility must be tested. |
| ncnn/MNN-like lightweight runtime | Medium | Potentially smaller, but requires model conversion and equivalence tests. |
| custom inference code | Low | Not sensible. Too much risk and maintenance. |

Recommended first proof:

```text
Build ONNXRuntime C API based processor for one x86_64 DSM target.
Run fixture equivalence against Python InsightFace output.
Only then expand platforms.
```

## Synology Toolkit Build Integration

The build must happen inside the DSM Toolkit build process.

Synology Toolkit model:

```text
/toolkit/source/av_imgdata/
  SynoBuildConf/
    depends
    build
    install
```

`PkgCreate.py` executes `SynoBuildConf/build` inside the platform chroot. Build variables such as `CC`, `CXX`, `CFLAGS`, `LDFLAGS`, `STRIP`, `SYNO_PLATFORM`, `ARCH`, and sysroot paths are provided by the Toolkit environment.

### `SynoBuildConf/depends`

Example:

```ini
[BuildDependent]
# optional native dependency projects can be listed here later
# av-imgdata-onnxruntime
# av-imgdata-libjpeg-turbo

[ReferenceOnly]

[default]
all="7.2.2"
```

### `SynoBuildConf/build`

Example:

```bash
#!/bin/bash
set -euo pipefail

PROJECT_DIR="/source/av_imgdata"
BUILD_DIR="${PROJECT_DIR}/processors/native/face_processor/build-${SYNO_PLATFORM}"
INSTALL_DIR="${PROJECT_DIR}/build/native/${SYNO_PLATFORM}"

rm -rf "${BUILD_DIR}" "${INSTALL_DIR}"
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

cd "${BUILD_DIR}"

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="${CC}" \
  -DCMAKE_CXX_COMPILER="${CXX}" \
  -DCMAKE_C_FLAGS="${CFLAGS}" \
  -DCMAKE_CXX_FLAGS="${CFLAGS}" \
  -DCMAKE_EXE_LINKER_FLAGS="${LDFLAGS}" \
  -DCMAKE_INSTALL_PREFIX="/usr/local/AV_ImgData" \
  -DAV_IMGDATA_BUILD_FACE_PROCESSOR=ON \
  -DAV_IMGDATA_ENABLE_ONNXRUNTIME=ON

make -j"$(nproc || echo 2)"
make install DESTDIR="${INSTALL_DIR}"

if [ -n "${STRIP:-}" ]; then
  "${STRIP}" "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" || true
fi
```

### `SynoBuildConf/install`

Example packaging step:

```bash
#!/bin/bash
set -euo pipefail

PKG_DIR=/tmp/_av_imgdata_spk
INNER_DIR=/tmp/_av_imgdata_inner
rm -rf "${PKG_DIR}" "${INNER_DIR}"
mkdir -p "${PKG_DIR}" "${INNER_DIR}"

source /pkgscripts-ng/include/pkg_util.sh

mkdir -p "${INNER_DIR}/bin"
mkdir -p "${INNER_DIR}/lib"
mkdir -p "${INNER_DIR}/src"
mkdir -p "${INNER_DIR}/ui"

cp -av build/native/${SYNO_PLATFORM}/usr/local/AV_ImgData/bin/* "${INNER_DIR}/bin/"
# Copy native shared libs only if they are not guaranteed by DSM/toolkit runtime.
# cp -av build/native/${SYNO_PLATFORM}/usr/local/AV_ImgData/lib/* "${INNER_DIR}/lib/"

cp -av src/* "${INNER_DIR}/src/"
cp -av ui/* "${INNER_DIR}/ui/"

pkg_make_package "${INNER_DIR}" "${PKG_DIR}"

mkdir -p "${PKG_DIR}/scripts"
cp -av scripts/* "${PKG_DIR}/scripts/"
./INFO.sh > INFO
cp INFO "${PKG_DIR}/INFO"

mkdir -p /image/packages
pkg_make_spk "${PKG_DIR}" "/image/packages" "$(pkg_get_spk_family_name)"
```

## Package Layout After Build

Target package layout inside `package.tgz`:

```text
/var/packages/AV_ImgData/target/
  bin/
    av-imgdata-face-processor
  lib/
    libonnxruntime.so            # only if shipped
    libavimgdata_image.so        # optional internal library
  src/
  ui/
  models/                        # optional empty/default; models remain explicit and license-aware
```

The lifecycle script should validate native processor availability:

```text
${SYNOPKG_PKGDEST}/bin/av-imgdata-face-processor version
${SYNOPKG_PKGDEST}/bin/av-imgdata-face-processor probe --model-root ... --model-name ...
```

## Backend Integration

Add service boundary:

```text
src/services/native_face_processor_service.py
```

Responsibilities:

```text
- build ProcessorInput JSON
- invoke package/bin/av-imgdata-face-processor
- enforce timeout
- parse ProcessorResult JSON
- validate schema
- normalize errors
- expose native processor status
- fall back only when explicitly configured and safe
```

Do not call the binary directly from API routes.

Add config section:

```json
{
  "native_processors": {
    "FACE_PROCESSOR": {
      "ENABLED": false,
      "PATH": "bin/av-imgdata-face-processor",
      "MODEL_ROOT": "",
      "MODEL_NAME": "",
      "TIMEOUT_SECONDS": 120,
      "MAX_IMAGE_BYTES": 67108864
    }
  }
}
```

Deprecate but do not immediately remove:

```json
{
  "pip_packages": {
    "INSIGHTFACE": {
      "ENABLED": false
    }
  }
}
```

## Status And UI Replacement

Replace the old optional package status with capability status.

Old status concept:

```text
pip package installed/importable:
  - insightface.app
  - onnxruntime
  - cv2
```

New status concept:

```text
native face processor:
  - binary present
  - executable bit set
  - version command works
  - linked libraries load
  - model root exists
  - model files exist
  - probe command succeeds
  - self-test fixture succeeds where available
```

UI should show:

```text
- disabled
- binary missing
- binary incompatible
- model missing
- model invalid
- ready
- last probe error
- processor version
- backend type
```

## Model Handling

Models remain external or package-managed explicitly. Do not silently bundle or auto-download models.

Rules:

```text
- model source must be explicit
- license notice must be visible
- model root must be configurable
- model name must be configurable
- processor probe must verify required model files
- missing model must not block package startup
```

If a model is bundled later, the license and redistribution permission must be verified before inclusion.

## Functional Equivalence Plan

Before replacement is enabled by default, define fixture-based equivalence tests.

Required fixture set:

```text
- no face image
- one face frontal image
- multiple face image
- rotated image if supported
- low confidence face image
- large image requiring resize
- unsupported/corrupt file
- image with EXIF orientation
```

Comparison strategy:

```text
- face count must match within configured threshold
- bounding boxes may use numeric tolerance
- landmarks may use numeric tolerance
- embeddings compare by cosine similarity tolerance, not byte equality
- error categories must match exactly
- unsupported formats must fail with stable error code
```

Example thresholds:

```text
box coordinate tolerance: <= 0.01 normalized units
landmark tolerance: <= 0.01 normalized units
embedding cosine similarity: >= 0.995 against reference output
confidence tolerance: documented per model/backend
```

## Build Feasibility Gates

The project must pass these gates before committing to full replacement.

### Gate 1: Toolkit proof on one platform

Target:

```text
dsm7-x86_64 / x86_64 platform family
```

Acceptance:

```text
- processor builds inside Synology Toolkit chroot
- package.tgz contains binary
- binary runs on test DSM system
- version command works
- self-test command works without model download
```

### Gate 2: Inference proof

Acceptance:

```text
- ONNX model loads
- detector produces expected face count on fixtures
- embedding model produces stable dimension and normalized output
- errors are structured
```

### Gate 3: Python parity proof

Acceptance:

```text
- same fixtures run through current Python InsightFace path and native processor path
- outputs match within defined tolerances
- existing FaceMatch/Checks workflow receives equivalent ProcessorResult
```

### Gate 4: Multi-platform build proof

Target platform groups:

```text
x86_64 family first
arm64 family second
older armv7 only if package support requires it
```

Acceptance:

```text
- SPK builds for each target platform through Toolkit
- binary links only against available or shipped libraries
- model probe works on real or equivalent DSM test environment
```

## Risk Assessment

| Risk | Severity | Mitigation |
|---|---:|---|
| ONNXRuntime is difficult to cross-compile for all DSM platforms | High | Start x86_64 only; isolate ONNXRuntime as BuildDependent or vendored prebuilt source artifact. |
| Full OpenCV build is too heavy | High | Avoid full OpenCV first; build narrow image loader/preprocessor. |
| Numeric output differs from InsightFace Python path | Medium | Use tolerance-based contract tests and preserve model/version metadata. |
| Model licensing blocks bundling | High | Keep models external and explicit unless license review passes. |
| Package size grows significantly | Medium | Strip binaries, avoid full OpenCV, ship only required shared libs. |
| Runtime missing shared libraries | High | Use `ldd`/readelf checks in build and package validation; ship required libs when allowed. |
| Older NAS CPU lacks required SIMD/instructions | High | Build conservative CPU targets; avoid AVX-only builds; provide platform-specific SPKs. |
| Same functionality cannot be reached on all platforms | Medium | Keep optional Python wheelhouse or external worker as fallback for unsupported platforms during migration. |

## What Should Be Replaced

Replace this runtime behavior:

```text
- download wheelhouse during package start
- pip install insightface/onnxruntime/opencv on NAS startup
- uninstall/reinstall OpenCV packages during startup
- validate Python imports as the primary readiness check
```

With this package behavior:

```text
- build native processor during DSM Toolkit build
- ship binary in SPK
- run `version` and `probe` commands for status
- execute processor through ProcessorContract
- keep package startup independent of optional model availability
```

## What Should Not Be Replaced

Do not move these into native code:

```text
- DSM routes
- runtime status aggregation
- worker token handling
- Synology Photos API sessions
- final writes
- findings persistence
- conflict detection
- UI state decisions
```

## Recommended Implementation Order

```text
1. Add processor_contract schemas for face_native_detect and face_native_embed.
2. Add Python-side adapter that can call an external processor executable.
3. Add fake test processor binary/script for contract tests.
4. Add C++ face processor skeleton with version/probe/self-test only.
5. Integrate C++ skeleton into Synology Toolkit build and package/bin.
6. Add image decode/preprocess support for JPEG first.
7. Add model probe and ONNXRuntime C API integration for one x86_64 platform.
8. Add detector inference and fixture result tests.
9. Add embedding inference and parity tests against current Python path.
10. Add UI status for native processor readiness.
11. Disable runtime wheelhouse install by default permanently.
12. Remove Python InsightFace path only after feature parity across supported platforms is proven.
```

## Final Recommendation

The replacement is technically sensible, but only as a staged native processor project.

Recommended decision:

```text
Proceed with a proof-of-concept native C/C++ face processor built by Synology Toolkit.
Do not remove Python InsightFace/Wheelhouse path until parity is proven.
Avoid full OpenCV unless required by fixtures.
Do not attempt to reimplement ONNXRuntime.
Use ONNXRuntime C API or another proven inference runtime behind the processor contract.
Start with x86_64 DSM 7 target, then expand platform coverage.
```

A successful final state is:

```text
SPK built per DSM platform
  -> contains package/bin/av-imgdata-face-processor
  -> contains required native libraries if allowed
  -> no startup pip install for InsightFace/OpenCV/ONNXRuntime
  -> same package-level face processing capability through ProcessorContract
  -> DSM backend remains workflow/status/write authority
```
