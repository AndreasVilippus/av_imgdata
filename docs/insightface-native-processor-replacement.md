# Native Replacement Concept For InsightFace / OpenCV / ONNXRuntime

## Purpose

This document defines a concrete replacement concept for the optional Python-based `InsightFace` / `OpenCV` / `ONNXRuntime` block.

The target is to replace the runtime `pip`/wheelhouse installation path with package-shipped native C/C++ processor binaries built inside the existing Synology DSM Toolkit build process.

The current project already has a prepared Linux-based Synology Toolkit environment. The project is expected to live under the Toolkit `source/` directory and the package build is invoked from the Toolkit root through:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Arguments are forwarded to `pkgscripts-ng/PkgCreate.py`; the wrapper performs structure checks and Python tests before the Toolkit build. The UI build remains part of the Toolkit build chain.

The replacement must preserve at least the same package-level functionality for the currently supported DSM platform. Additional DSM platforms must stay optional build targets and must not block the first implementation.

## Scope Correction

The existing wheelhouse is already platform-specific. The current configuration targets one DSM platform family:

```text
dsm7-x86_64-python38
```

Therefore the native replacement does not need to solve every Synology platform at once.

Required first target:

```text
DSM 7.3
current Toolkit build target, e.g. geminilake
current package platform support path
```

Optional later targets:

```text
other x86_64 platform families
arm64 platform families
older ARM platforms only if package support explicitly requires them
```

The design must allow additional platform builds later, but they are not required for the first accepted implementation.

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
Replace DSM runtime pip/wheelhouse installation for InsightFace/OpenCV/ONNXRuntime
with Toolkit-built C/C++ native processor binaries shipped inside the SPK.
```

The DSM backend remains the workflow and status owner.

The native processor does not write to DSM metadata, Synology Photos, config, runtime state, or findings storage directly. It only returns structured `ProcessorResult` JSON and optional artifacts.

## Feasibility Summary

| Area | Feasibility | Assessment |
|---|---:|---|
| Replacing runtime pip/wheelhouse install | High | Sensible. Removes startup fragility and dynamic dependency installation. |
| Replacing `cv2` import with native image/preprocess binary | High | Feasible if image codec scope is controlled and tested. |
| Replacing InsightFace Python orchestration | Medium | Feasible if exact model inputs/outputs and normalization are defined. |
| Replacing ONNXRuntime with custom inference code | Low | Not sensible. A real inference runtime is still required. |
| Building ONNXRuntime C/C++ for the current Toolkit target | Medium | Feasible enough for proof-of-concept; must be verified in the existing Toolkit environment. |
| Building ONNXRuntime C/C++ for all DSM platforms | Medium to Low | Optional later. High effort and must be proven per platform. |
| Guaranteeing identical numeric output across architectures | Medium to Low | Must allow tolerances for floating-point differences. |
| Supporting current package-level behavior on the current target | Medium | Feasible if the processor contract is defined first and optional status behavior is preserved. |

Conclusion:

```text
The replacement is sensible if implemented first for the already supported Toolkit target.
Multi-platform support must remain optional and additive.
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

## Repository Layout

Add native processor sources to the existing repository under `processors/native/`:

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

Add packaging target path:

```text
package/bin/av-imgdata-face-processor
```

The source tree remains under the current Toolkit workspace:

```text
toolkit/
  pkgscripts-ng/
  source/
    av_imgdata/
      tools/build-package.sh
      SynoBuildConf/
      processors/native/face_processor/
```

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
| JPEG/JPG | libjpeg-turbo or Toolkit-provided jpeg library | First target. |
| PNG | libpng or Toolkit-provided png library | Add if required by supported workflows. |
| TIFF | libtiff only if current face processing requires it | Verify before including. |
| HEIC/HEIF | optional only if proven required | High dependency burden. |
| RAW formats | not first target for face inference | Usually metadata path, not face inference input. |

### Inference strategy

Do not implement ONNX inference manually.

Candidate options:

| Option | Feasibility | Notes |
|---|---:|---|
| ONNXRuntime C API | Medium | Best functional match to current ONNXRuntime block, but Toolkit build must be proven. |
| OpenCV DNN | Medium | May reduce one dependency if OpenCV is already needed; model compatibility must be tested. |
| ncnn/MNN-like lightweight runtime | Medium | Potentially smaller, but requires model conversion and equivalence tests. |
| custom inference code | Low | Not sensible. Too much risk and maintenance. |

Recommended first proof:

```text
Build an ONNXRuntime C API based processor for the current Toolkit target.
Run fixture equivalence against Python InsightFace output.
Only then expand platform targets.
```

## Existing Build Flow Integration

The existing build entrypoint remains:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The native processor build must be integrated behind this wrapper. The user should not run a separate native build command for normal package creation.

Expected wrapper behavior after integration:

```text
1. run existing structure checks
2. run existing Python tests
3. run native processor preflight if sources are enabled
4. invoke pkgscripts-ng/PkgCreate.py with forwarded arguments
5. Toolkit build compiles native processor inside the platform build environment
6. Toolkit packaging includes the processor binary in package/bin/
7. result_spk/ contains the final SPK for the requested platform
```

The wrapper may optionally expose flags later:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake --native-face=on
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake --native-face=off
```

Default for first implementation:

```text
native face processor build = off or experimental
```

After proof:

```text
native face processor build = on for the currently supported platform
additional platforms = opt-in only
```

## Synology Toolkit Build Integration

The build must happen inside the DSM Toolkit package build path.

Current repository path assumption:

```text
toolkit/source/av_imgdata
```

`build-package.sh` forwards options to `PkgCreate.py`. `PkgCreate.py` runs package build instructions from `SynoBuildConf/` for the requested platform.

### Native build script placement

Keep native processor build logic focused and callable from `SynoBuildConf/build`:

```text
tools/build-native-face-processor.sh
processors/native/face_processor/CMakeLists.txt
```

### `tools/build-native-face-processor.sh`

Example:

```bash
#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_ROOT="${PROJECT_DIR}/build/native"
PLATFORM="${SYNO_PLATFORM:-unknown}"
BUILD_DIR="${BUILD_ROOT}/${PLATFORM}/face_processor-build"
INSTALL_DIR="${BUILD_ROOT}/${PLATFORM}/face_processor-install"

rm -rf "${BUILD_DIR}" "${INSTALL_DIR}"
mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

cd "${BUILD_DIR}"

cmake "${PROJECT_DIR}/processors/native/face_processor" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="${CC}" \
  -DCMAKE_CXX_COMPILER="${CXX}" \
  -DCMAKE_C_FLAGS="${CFLAGS:-}" \
  -DCMAKE_CXX_FLAGS="${CXXFLAGS:-${CFLAGS:-}}" \
  -DCMAKE_EXE_LINKER_FLAGS="${LDFLAGS:-}" \
  -DCMAKE_INSTALL_PREFIX="/usr/local/AV_ImgData" \
  -DAV_IMGDATA_ENABLE_ONNXRUNTIME=ON

make -j"$(nproc 2>/dev/null || echo 2)"
make install DESTDIR="${INSTALL_DIR}"

if [ -n "${STRIP:-}" ]; then
  "${STRIP}" "${INSTALL_DIR}/usr/local/AV_ImgData/bin/av-imgdata-face-processor" || true
fi
```

### `SynoBuildConf/build`

Example integration:

```bash
#!/bin/bash
set -euo pipefail

# existing backend/UI/package build steps stay in place

if [ "${AV_IMGDATA_NATIVE_FACE:-0}" = "1" ]; then
  ./tools/build-native-face-processor.sh
fi

# existing Makefile/UI/toolkit build path continues here
```

### Packaging copy step

Where package content is assembled, copy native artifacts only if present:

```bash
NATIVE_INSTALL="build/native/${SYNO_PLATFORM}/face_processor-install/usr/local/AV_ImgData"

if [ -x "${NATIVE_INSTALL}/bin/av-imgdata-face-processor" ]; then
  mkdir -p "${PKG_DEST}/bin"
  cp -av "${NATIVE_INSTALL}/bin/av-imgdata-face-processor" "${PKG_DEST}/bin/"
fi

if [ -d "${NATIVE_INSTALL}/lib" ]; then
  mkdir -p "${PKG_DEST}/lib"
  cp -av "${NATIVE_INSTALL}/lib/"* "${PKG_DEST}/lib/" || true
fi
```

The exact variable names must match the existing `SynoBuildConf/` implementation. This concept defines the placement and behavior, not the final shell patch.

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

## Platform Policy

The current wheelhouse is platform-specific, and the current native replacement should follow the same policy.

### Required first platform

```text
Build and package the native processor for the currently supported Toolkit target only.
```

Example current build target:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

### Optional additional platforms

Additional platforms are supported only when explicitly built and tested:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p apollolake
source/av_imgdata/tools/build-package.sh -v 7.3 -p broadwell
source/av_imgdata/tools/build-package.sh -v 7.3 -p v1000
```

Do not fail the main supported platform because an optional platform has no native processor yet.

Recommended platform metadata:

```json
{
  "native_face_processor": {
    "supported_platforms": ["geminilake"],
    "optional_platforms": ["apollolake", "broadwell", "v1000"],
    "unsupported_behavior": "capability_disabled"
  }
}
```

Runtime behavior for unsupported platform:

```text
- package starts normally
- native face processor status = unavailable_platform
- Python wheelhouse or external worker may remain available if configured
- UI shows that native processor is not shipped for this platform
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
  - build platform supported
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
- unavailable for platform
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

### Gate 1: Current Toolkit target proof

Target:

```text
Current required build target, e.g. DSM 7.3 / geminilake
```

Command:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Acceptance:

```text
- wrapper runs existing checks and tests
- Toolkit build compiles native processor inside platform build path
- result_spk/ contains SPK
- package.tgz contains bin/av-imgdata-face-processor
- binary runs on matching test DSM system
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

### Gate 4: Optional platform proof

Optional only.

Acceptance per additional platform:

```text
- Toolkit environment deployed for platform
- SPK builds with same build wrapper and different -p option
- binary links only against available or shipped libraries
- model probe works on real or equivalent DSM test environment
```

## Risk Assessment

| Risk | Severity | Mitigation |
|---|---:|---|
| ONNXRuntime is difficult to cross-compile for current Toolkit target | High | Start with skeleton and image loader; isolate ONNXRuntime as separate gate. |
| Full OpenCV build is too heavy | High | Avoid full OpenCV first; build narrow image loader/preprocessor. |
| Native processor works only on one DSM platform | Acceptable initially | Match current wheelhouse policy; additional platforms optional. |
| Numeric output differs from InsightFace Python path | Medium | Use tolerance-based contract tests and preserve model/version metadata. |
| Model licensing blocks bundling | High | Keep models external and explicit unless license review passes. |
| Package size grows significantly | Medium | Strip binaries, avoid full OpenCV, ship only required shared libs. |
| Runtime missing shared libraries | High | Use `ldd`/readelf checks in build and package validation; ship required libs when allowed. |
| Older NAS CPU lacks required SIMD/instructions | High | Build conservative CPU targets; avoid AVX-only builds; provide platform-specific SPKs. |
| Same functionality cannot be reached on optional platforms | Acceptable initially | Report native capability unavailable; keep wheelhouse or worker path as optional fallback. |

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
- ship binary in SPK for the selected platform
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
5. Integrate skeleton into existing tools/build-package.sh -> PkgCreate.py Toolkit path.
6. Package skeleton into package/bin for the current -p target.
7. Add image decode/preprocess support for JPEG first.
8. Add model probe and ONNXRuntime C API integration for the current platform.
9. Add detector inference and fixture result tests.
10. Add embedding inference and parity tests against current Python path.
11. Add UI status for native processor readiness.
12. Disable runtime wheelhouse install by default permanently for supported native platform.
13. Keep wheelhouse or worker path optional for unsupported platforms until parity is proven there.
```

## Final Recommendation

The replacement is technically sensible, but only as a staged native processor project aligned with the current Toolkit build workflow.

Recommended decision:

```text
Proceed with a proof-of-concept native C/C++ face processor built by the existing tools/build-package.sh path.
Target the currently supported DSM platform first.
Do not require additional DSM platforms for the first implementation.
Keep additional platform builds optional and additive.
Do not remove Python InsightFace/Wheelhouse path until parity is proven for the supported target.
Avoid full OpenCV unless required by fixtures.
Do not attempt to reimplement ONNXRuntime.
Use ONNXRuntime C API or another proven inference runtime behind the processor contract.
```

A successful first final state is:

```text
toolkit/source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
  -> runs existing checks/tests
  -> invokes PkgCreate.py
  -> builds C/C++ processor inside Toolkit path
  -> produces SPK in result_spk/
  -> SPK contains bin/av-imgdata-face-processor
  -> no startup pip install for InsightFace/OpenCV/ONNXRuntime on the supported platform
  -> same package-level face processing capability through ProcessorContract
  -> DSM backend remains workflow/status/write authority
```
