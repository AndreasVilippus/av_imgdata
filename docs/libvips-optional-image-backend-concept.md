# Optional libvips Image Backend Concept

## Purpose

This document defines an optional `libvips` feature for image processing in `av_imgdata`.

The feature must not replace the current default native processing path. The existing image libraries and the current `av-imgdata-face-processor` behavior remain the standard when libvips is not built, not installed, not configured, or not runtime-probed successfully.

The intended use of libvips is:

```text
- image decoding
- EXIF-aware orientation handling where available
- resize / thumbnail / preview generation
- format normalization
- face-preprocessing input normalization
- memory-efficient handling of large images
```

The intended non-use of libvips is:

```text
- face detection inference
- face embedding inference
- replacement of ONNXRuntime
- DSM workflow ownership
- DSM file authorization
- result persistence
- final writes
```

## Decision Summary

Adopt libvips as an optional image backend:

```text
Default path:
  current C++/JPEG/HEIF/ONNXRuntime image path

Optional preferred path when available:
  libvips-backed image processor / image backend

Fallback:
  existing image path if libvips is missing, unsupported, misconfigured, or fails probe
```

The default package must remain buildable and runnable without libvips.

## Why libvips Is A Candidate

libvips is a fast image processing library with low memory needs. Its official documentation describes it as demand-driven and horizontally threaded. It also explicitly states that libvips runs quickly and uses little memory compared with similar libraries, and that it is licensed under LGPL-2.1-or-later.

Relevant technical properties:

```text
- demand-driven image evaluation
- threaded image I/O
- processing only currently required pixel regions where possible
- low memory use for large image pipelines
- broad image format support depending on build options
- C and C++ APIs
```

These properties fit NAS and worker processing where large images may need to be decoded, resized, normalized, or converted before face inference or preview generation.

## Scope

### In scope

```text
- optional native subproject for libvips integration
- optional build of libvips or use of a pinned libvips source/dependency bundle
- narrow interface to expose only needed operations
- optional preferred runtime path when libvips probe succeeds
- fallback to current image path when unavailable
- package-local shared libraries and notices
- external worker reuse of the same image backend where packaged
```

### Out of scope for first implementation

```text
- mandatory libvips dependency
- replacing ONNXRuntime
- full image format universe
- ImageMagick / GraphicsMagick fallback through libvips
- PDF, SVG, RAW, OpenSlide, DICOM, Matlab, FITS, DeepZoom
- mandatory HEIC/AVIF if decoder licensing/build is not proven
- replacing DSM backend logic
- replacing face inference logic
```

## Existing Default Path

The current native face processor already supports a direct image path using existing dependencies.

Current default line:

```text
av-imgdata-face-processor
  -> current image decode/preprocess implementation
  -> ONNXRuntime C API
  -> ProcessorResult JSON
```

That default remains authoritative for builds that do not enable libvips.

libvips must be additive:

```text
if libvips feature unavailable:
  continue with current image path
```

No workflow may require libvips unless a future release explicitly changes the default after measurement and parity tests.

## Proposed Architecture

Add a minimal libvips-backed image processor/backend.

Recommended layout:

```text
processors/native/image_backend_vips/
  README.md
  CMakeLists.txt or meson.build wrapper
  src/
    av_imgdata_vips_backend.cpp
    vips_probe.cpp
    vips_normalize.cpp
    vips_thumbnail.cpp
    vips_errors.cpp
  include/
    av_imgdata_vips_backend.h
  tests/
    fixtures/
```

Alternative if libvips is consumed only inside the existing face processor:

```text
processors/native/face_processor/
  src/
    image_backend_manual.cpp
    image_backend_vips.cpp
```

Recommended first structure:

```text
processors/native/image_backend_vips/
```

Reason:

```text
A separate subproject keeps libvips optional, testable, and removable.
It can serve both face preprocessing and preview/thumbnail processors without making the face processor depend on libvips directly.
```

## Minimal Interface

The integration must expose a very small command/API surface.

### CLI option

Preferred first binary:

```text
package/bin/av-imgdata-image-processor
```

Commands:

```text
av-imgdata-image-processor version
av-imgdata-image-processor probe
av-imgdata-image-processor normalize-for-face --input <image> --output <rgb-or-jpeg> --metadata <json>
av-imgdata-image-processor thumbnail --input <image> --output <image> --metadata <json>
av-imgdata-image-processor image-info --input <image> --output <json>
av-imgdata-image-processor self-test --fixtures <dir>
```

### C/C++ library option

Optional later:

```text
libavimgdata_vips_backend.so
```

Minimal C-style API:

```c
int avimgdata_vips_probe(char* error, size_t error_len);
int avimgdata_vips_image_info(const char* input_path, const char* output_json_path);
int avimgdata_vips_normalize_for_face(const char* input_path, const char* output_path, const char* output_json_path);
int avimgdata_vips_thumbnail(const char* input_path, const char* output_path, const char* output_json_path);
```

Recommended first implementation:

```text
Use CLI boundary first.
Only add shared library API if process startup becomes measurable overhead.
```

## Preferred Runtime Integration

The feature is preferred only when enabled and probed.

Runtime selection:

```text
1. If libvips feature disabled: use default image path.
2. If libvips binary missing: use default image path.
3. If libvips probe fails: use default image path and expose status.
4. If input format unsupported by configured libvips build: use default image path where possible.
5. If libvips succeeds: use libvips output for preprocessing/thumbnail/image-info.
```

Suggested configuration:

```json
{
  "native_processors": {
    "IMAGE_PROCESSOR_VIPS": {
      "ENABLED": false,
      "PREFERRED": true,
      "PATH": "bin/av-imgdata-image-processor",
      "TIMEOUT_SECONDS": 120,
      "MAX_IMAGE_BYTES": 268435456,
      "SUPPORTED_FORMATS": ["jpeg", "jpg", "png", "webp", "tiff", "heic", "heif"],
      "ALLOW_FALLBACK_TO_DEFAULT": true
    }
  }
}
```

Selection result values:

```text
vips_disabled
vips_binary_missing
vips_probe_failed
vips_format_unsupported
vips_ready
vips_failed_fallback_used
vips_failed_no_fallback
```

## Integration With Face Processing

The face processor should not directly require libvips.

Recommended flow:

```text
NativeFaceProcessorService
  -> ImagePreprocessSelector
     -> libvips image processor if enabled/probed/supported
     -> current default decode/preprocess otherwise
  -> av-imgdata-face-processor detect/embed
  -> ProcessorResult validation
```

For face preprocessing, libvips should produce either:

```text
Option A: normalized JPEG/intermediate image
Option B: raw RGB tensor-compatible buffer
Option C: normalized RGB file plus metadata JSON
```

Recommended first option:

```text
Option C: normalized RGB/JPEG file plus metadata JSON
```

Reason:

```text
- keeps existing face processor changes small
- easy to inspect and test
- avoids direct ABI coupling at first
- still allows later optimization to memory buffer or shared library
```

Example metadata:

```json
{
  "processor": {
    "name": "av-imgdata-image-processor",
    "backend": "libvips",
    "version": "0.1.0"
  },
  "input": {
    "path": "/volume1/photo/image.heic",
    "format": "heif",
    "width": 4032,
    "height": 3024
  },
  "output": {
    "path": "/tmp/av-imgdata-job-123/normalized.jpg",
    "format": "jpeg",
    "width": 1280,
    "height": 960,
    "orientation_applied": true,
    "colorspace": "srgb"
  },
  "timing_ms": {
    "load": 12.1,
    "autorotate": 1.5,
    "resize": 9.3,
    "write": 6.8,
    "total": 29.7
  }
}
```

## Integration With Preview / Thumbnail Processing

libvips is a strong candidate for preview generation.

Proposed job types:

```text
image_vips_info
image_vips_thumbnail
image_vips_normalize
```

Thumbnail command:

```bash
av-imgdata-image-processor thumbnail \
  --input /path/to/source.jpg \
  --output /tmp/job/thumb.jpg \
  --metadata /tmp/job/image-result.json \
  --width 512 \
  --height 512 \
  --format jpeg
```

Result shape:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "image_vips_thumbnail",
  "status": "completed",
  "processor": {
    "name": "av-imgdata-image-processor",
    "version": "0.1.0",
    "backend": "libvips"
  },
  "result": {
    "output_path": "/tmp/job/thumb.jpg",
    "width": 512,
    "height": 384,
    "format": "jpeg"
  },
  "timing_ms": {
    "total": 18.2
  }
}
```

## Format Scope

The libvips build must cover only expected formats.

### Required first format set

```text
JPEG/JPG
PNG
WebP
TIFF
```

### Optional format set after separate proof

```text
HEIC/HEIF
AVIF
```

### Explicitly excluded first

```text
RAW
PDF
SVG
DICOM
OpenSlide
Matlab
FITS
DeepZoom
JPEG XL
ImageMagick/GraphicsMagick delegate formats
```

Rationale:

```text
- JPEG/JPG is the primary photo baseline.
- PNG is common and useful for generated assets/screenshots.
- WebP is common in modern libraries and external images.
- TIFF may appear in scanned or exported image libraries.
- HEIC/HEIF is important but codec/licensing/runtime-decoder complexity must be isolated.
```

## Build Variants

Add build-time feature switch:

```text
AV_IMGDATA_WITH_VIPS=0|1
AV_IMGDATA_VIPS_FORMATS=minimal|photo|photo_heif
```

Recommended defaults:

```text
AV_IMGDATA_WITH_VIPS=0
AV_IMGDATA_VIPS_FORMATS=photo
```

Build variants:

```text
minimal:
  jpeg
  png

photo:
  jpeg
  png
  webp
  tiff

photo_heif:
  jpeg
  png
  webp
  tiff
  heif/heic
  avif if available through libheif stack
```

The DSM package must still build when `AV_IMGDATA_WITH_VIPS=0`.

## Git / Source Strategy

libvips may be integrated as a separately fetched subproject.

Preferred source strategy:

```text
native_deps/sources/libvips-<version>.tar.xz
native_deps/checksums/libvips-<version>.sha256
native_deps/licenses/libvips.LICENSE
```

Optional developer convenience strategy:

```text
tools/native/fetch-libvips.sh
```

Rules:

```text
- normal package build must not download from the network
- fetched source archives must be pinned by version and checksum
- license files must be copied into package notices
- source fetch/update must be explicit developer action
```

Alternative Git submodule strategy:

```text
third_party/libvips/       # git submodule, pinned commit
```

Submodule is allowed only if the build wrapper validates the pinned revision and does not implicitly update it.

Recommended first choice:

```text
Use pinned source archive, not submodule.
```

Reason:

```text
Synology Toolkit package builds should be deterministic and offline-capable.
```

## Toolkit Build Integration

The current package build command remains:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Add optional stages only when enabled:

```text
if AV_IMGDATA_WITH_VIPS=1:
  tools/native/check-libvips-deps.sh
  tools/native/build-libvips-deps.sh
  tools/native/build-libvips.sh
  tools/build-native-image-processor-vips.sh
```

Proposed scripts:

```text
tools/native/fetch-libvips.sh                 # explicit developer-only source fetch
tools/native/check-libvips-deps.sh            # archive/checksum/license/platform check
tools/native/build-libvips-deps.sh            # glib/expat/jpeg/png/webp/tiff as needed
tools/native/build-libvips.sh                 # Meson/Ninja build inside Toolkit env
tools/build-native-image-processor-vips.sh    # build av-imgdata-image-processor
tools/native/validate-vips-artifact.sh        # ldd/readelf/rpath/notice checks
```

`SynoBuildConf/build` concept:

```bash
if [ "${AV_IMGDATA_WITH_VIPS:-0}" = "1" ]; then
  ./tools/native/check-libvips-deps.sh
  ./tools/native/build-libvips-deps.sh
  ./tools/native/build-libvips.sh
  ./tools/build-native-image-processor-vips.sh
fi
```

`SynoBuildConf/install` concept:

```bash
VIPS_INSTALL="build/native/${SYNO_PLATFORM}/vips-image-processor-install/usr/local/AV_ImgData"

if [ -x "${VIPS_INSTALL}/bin/av-imgdata-image-processor" ]; then
  mkdir -p "$package_tgz_dir/bin"
  cp -av "${VIPS_INSTALL}/bin/av-imgdata-image-processor" "$package_tgz_dir/bin/"
fi

if [ -d "${VIPS_INSTALL}/lib" ]; then
  mkdir -p "$package_tgz_dir/lib"
  find "${VIPS_INSTALL}/lib" -maxdepth 1 -type f -name '*.so*' -exec cp -av {} "$package_tgz_dir/lib/" \;
fi

if [ -f "package/THIRD_PARTY_NOTICES/libvips-image-backend.md" ]; then
  mkdir -p "$package_tgz_dir/THIRD_PARTY_NOTICES"
  cp -av "package/THIRD_PARTY_NOTICES/libvips-image-backend.md" \
    "$package_tgz_dir/THIRD_PARTY_NOTICES/libvips-image-backend.md"
fi
```

## Minimal libvips Build Configuration

libvips uses Meson. The package should pass only required dependencies.

Conceptual Meson flags:

```bash
meson setup build \
  --prefix=/usr/local/AV_ImgData \
  --libdir=lib \
  --buildtype=release \
  -Dmagick=disabled \
  -Dopenslide=disabled \
  -Dpdfium=disabled \
  -Dpoppler=disabled \
  -Dmatio=disabled \
  -Dcfitsio=disabled \
  -Dopenexr=disabled \
  -Dheif=disabled \
  -Djpeg=enabled \
  -Dpng=enabled \
  -Dtiff=enabled \
  -Dwebp=enabled
```

For `photo_heif` variant:

```bash
-Dheif=enabled
```

Only enable `heif` after dependency and license review of:

```text
libheif
HEVC decoder library if used
AV1 decoder library if used
patent-sensitive codec implications
```

## Runtime Library Handling

Use package-local shared libraries.

Target layout:

```text
/var/packages/AV_ImgData/target/
  bin/
    av-imgdata-image-processor
    av-imgdata-face-processor
  lib/
    libvips.so*
    libglib-2.0.so*
    libgobject-2.0.so*
    libexpat.so*
    libjpeg.so*
    libpng.so*
    libwebp.so*
    libtiff.so*
    libheif.so*                  # only photo_heif
  THIRD_PARTY_NOTICES/
    libvips-image-backend.md
```

Link strategy:

```text
- prefer dynamic linking for LGPL components
- set RPATH/RUNPATH to $ORIGIN/../lib
- avoid global LD_LIBRARY_PATH except subprocess-local fallback
- validate with readelf/ldd in build checks
```

## License Policy

libvips is LGPL-2.1-or-later. This is acceptable only with explicit packaging rules.

Required obligations:

```text
- dynamically link libvips where possible
- include libvips license text
- include notices for all shipped libvips dependencies
- record versions and source URLs
- record static vs dynamic linkage
- provide source offer or source reference for LGPL components as required
- do not modify libvips without recording patches and license obligations
```

Add notice file:

```text
package/THIRD_PARTY_NOTICES/libvips-image-backend.md
```

Minimum contents:

```text
- libvips version
- libvips license: LGPL-2.1-or-later
- source URL
- build flags
- enabled format loaders
- shipped shared libraries
- transitive dependency list
- license for each dependency
- whether dependency is static or dynamic
- local patches, if any
```

License risk by dependency:

```text
Low / acceptable:
  libvips LGPL with dynamic linking
  glib LGPL with dynamic linking
  expat MIT-like
  libjpeg-turbo permissive
  zlib permissive
  libpng permissive
  libwebp BSD-style
  libtiff BSD-like

Requires separate review:
  libheif and codec plugins
  HEVC decoder stack
  AV1 decoder stack
  ImageMagick/GraphicsMagick delegates
  PDF/SVG/RAW loaders
```

## Status And UI

Expose a separate status block.

Example status:

```json
{
  "enabled": true,
  "preferred": true,
  "available": true,
  "reason": "vips_ready",
  "binary": "bin/av-imgdata-image-processor",
  "backend": "libvips",
  "version": "libvips 8.x",
  "formats": {
    "jpeg": true,
    "png": true,
    "webp": true,
    "tiff": true,
    "heif": false
  },
  "fallback": "default_image_backend"
}
```

UI labels:

```text
libvips disabled
libvips unavailable
libvips ready
libvips ready without HEIC/HEIF
libvips failed, default backend used
```

## External Worker Integration

External workers may also use libvips.

Worker package variants:

```text
worker-standard:
  av-imgdata-worker
  av-imgdata-face-processor
  default image backend

worker-vips:
  av-imgdata-worker
  av-imgdata-face-processor
  av-imgdata-image-processor
  libvips shared libraries
  notices
```

Worker startup probe:

```text
av-imgdata-image-processor version
av-imgdata-image-processor probe
```

Worker capability payload extension:

```json
{
  "capabilities": [
    "face_native_detect",
    "face_native_embed",
    "image_vips_info",
    "image_vips_thumbnail",
    "image_vips_normalize"
  ],
  "features": {
    "api_file_transfer": true,
    "native_face_processor": true,
    "libvips_image_backend": true,
    "libvips_preferred": true
  }
}
```

If worker has libvips and DSM does not, DSM can still assign image preprocessing or thumbnail jobs to that worker based on capabilities.

## Security Rules

```text
- no ImageMagick/GraphicsMagick delegates in first build
- no PDF/SVG/RAW/DICOM loaders in first build
- no network fetch from image processor
- no user-supplied arbitrary libvips operation names
- explicit allowlist of commands and formats
- file size limit before processing
- timeout per operation
- temp directory isolation
- structured errors only
```

Allowed operations:

```text
image-info
thumbnail
normalize-for-face
probe
version
self-test
```

Forbidden operations:

```text
arbitrary-vips-operation
shell-command
convert-any-format
load-url
run-delegate
```

## Contract Tests

Required tests:

```text
- libvips disabled -> default backend selected
- libvips binary missing -> default backend selected
- libvips probe fails -> default backend selected and status reason recorded
- JPEG thumbnail fixture produces expected dimensions
- PNG thumbnail fixture produces expected dimensions
- WebP fixture only runs when webp format enabled
- TIFF fixture only runs when tiff format enabled
- HEIC fixture only runs in photo_heif build
- corrupt image returns structured error
- large image does not exceed memory threshold
- face preprocessing output can be consumed by av-imgdata-face-processor
```

Comparison tests:

```text
manual backend output
vs.
libvips normalize-for-face output
```

Use tolerance:

```text
- dimensions must match exactly
- orientation result must match expected fixture
- face detector result may use bounding box tolerance
- thumbnail visual equivalence may use hash of normalized dimensions and approximate pixel checksum
```

## Implementation Phases

## Current Implementation Status

Implemented as first package step:

```text
- default config block native_processors.IMAGE_PROCESSOR_VIPS
- runtime config normalization for IMAGE_PROCESSOR_VIPS
- optional AV_IMGDATA_WITH_VIPS build and install gate
- standalone processors/native/image_backend_vips skeleton project
- av-imgdata-image-processor version/probe skeleton commands
- backend status adapter with disabled/missing/probe-failed/ready states
- status/config UI labels and readable status translations
- package sanitize rules for optional vips build artifacts
- unit/static/UI contract coverage for the optional feature
```

Not implemented yet:

```text
- pinned libvips dependency bundle
- package-local libvips shared libraries and license notices
- real image-info / thumbnail / normalize-for-face operations
- preview/thumbnail runtime selection
- face preprocessing integration through ImagePreprocessSelector
- HEIC/HEIF libvips proof
```

The current binary is intentionally a Phase 2 skeleton. Its `probe` command
returns `vips_probe_failed` with `libvips_not_linked`, so the default image
backend remains authoritative.

### Phase 1: Documentation and feature flag

```text
- add this concept
- add config entries
- add status placeholders
- add feature flag AV_IMGDATA_WITH_VIPS
```

Acceptance:

```text
- default build unchanged
- package works without libvips
```

### Phase 2: Standalone image processor skeleton

```text
- add processors/native/image_backend_vips
- implement version/probe with mocked/no-op backend first
- package only when AV_IMGDATA_WITH_VIPS=1
```

Acceptance:

```text
- av-imgdata-image-processor version works
- probe reports disabled/missing libvips cleanly
- fallback remains default backend
```

### Phase 3: Minimal libvips build

```text
- build libvips with JPEG/PNG only
- dynamic link package-local libs
- include notices
- implement image-info and thumbnail
```

Acceptance:

```text
- JPEG and PNG fixtures pass
- status reports formats accurately
- default backend still works when feature disabled
```

### Phase 4: Photo format build

```text
- add WebP and TIFF
- add memory/time measurements
- add preview/thumbnail integration
```

Acceptance:

```text
- JPEG/PNG/WebP/TIFF fixtures pass
- thumbnail pipeline can prefer libvips
- fallback works per format
```

### Phase 5: Face preprocessing integration

```text
- add normalize-for-face command
- integrate ImagePreprocessSelector
- produce normalized image/metadata for face processor
```

Acceptance:

```text
- face processor can consume libvips-normalized output
- results match default backend within tolerance
- fallback works on failure
```

### Phase 6: HEIC/HEIF optional proof

```text
- review libheif and codec stack licenses
- build photo_heif variant
- add HEIC/HEIF fixtures
```

Acceptance:

```text
- HEIC/HEIF probe reports true only when decoder is actually available
- no patent-sensitive codec is shipped without explicit review
- fallback remains available
```

### Phase 7: External worker packaging

```text
- create worker-vips package variant
- include libvips image processor and shared libraries
- report worker capabilities
```

Acceptance:

```text
- worker-vips starts on Linux
- worker reports libvips capabilities
- DSM can assign image_vips_thumbnail or preprocessing job to worker
```

## Final Recommendation

Adopt libvips as an optional feature, not as a required dependency.

Decision:

```text
libvips = optional preferred image backend when built, configured, and probed
current libraries = default fallback
ONNXRuntime = remains required for face inference
libvips subproject = separate native image backend first
minimal interface = CLI boundary first, shared library later only if measured
format scope = JPEG/PNG/WebP/TIFF first; HEIC/HEIF only after separate proof
license = acceptable with dynamic linking and notices, but more complex than current permissive stack
```

Successful target state:

```text
AV_IMGDATA_WITH_VIPS=0
  -> package builds as today
  -> current image backend used

AV_IMGDATA_WITH_VIPS=1
  -> libvips image processor is built and packaged
  -> status shows libvips availability and supported formats
  -> image preprocessing/thumbnail jobs prefer libvips when ready
  -> failures fall back to current backend when allowed
```
