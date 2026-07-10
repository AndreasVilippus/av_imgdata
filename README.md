# ImgData

`AV_ImgData` is a Synology DSM package intended to support the transfer of metadata stored in image files. Its current focus is on person-related metadata, especially workflows where face names embedded in images are reviewed, matched against Synology Photos people, mapped to known names, and assigned into Synology Photos.

## Features

- Show person statistics from Synology Photos.
- Match unknown Synology Photos faces against face names stored in image metadata.
- Assign a matched face to an existing Photos person.
- Create a new Photos person from a matched file face.
- Delete a metadata face from image XMP via ExifTool from the checks view.
- Maintain persistent name mappings for recurring metadata name variants.
- Edit runtime configuration from the package UI.
- Use a package-shipped native C++ face processor for InsightFace-compatible
  ONNX detection and embedding.
- Optionally use the package-shipped native libvips image processor for image
  information, thumbnail/normalization work, and HEIC/HEIF decoding through the
  packaged libheif/libde265 stack.
- Build optional external worker bundles for Windows and Linux hosts as the
  0.10.0 development focus for offloading selected processor jobs.

## Supported Environment

- DSM `7.3` or newer
- Package architecture: target-platform specific, as returned by the Synology
  toolkit for the selected platform
- Synology toolkit / `pkgscripts-ng`
- A prepared build environment for the target platform, for example `geminilake`
- The latest available Synology Photos package on the target system

The current package metadata is defined in [`INFO.sh`](./INFO.sh).

## Download

Prebuilt packages are available under [GitHub Releases](https://github.com/<owner>/<repo>/releases).

## Installation

1. Download the desired `.spk` from the GitHub Releases page.
2. Open DSM `Package Center`.
3. Choose manual installation.
4. Select the downloaded package file.
5. Complete the DSM installation flow.

After installation, DSM exposes the desktop UI defined under [`ui/`](./ui).

ExifTool can also be installed from within the package UI, but this is optional. If ExifTool is already available on the system or not required for your workflow, no additional ExifTool installation is needed.

## Build From Source

The package is built with the Synology toolkit and `pkgscripts-ng`.

The expected toolkit workspace layout is:

```text
toolkit/
├── pkgscripts-ng/
└── source/
    └── av_imgdata/
```

Use the package build wrapper from the toolkit root. It now enables package
collection by default, so generated SPKs are copied into `result_spk/`.

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The wrapper performs the required preflight steps before invoking the Synology
toolkit package build:

1. run structure checks
2. run the Python test suite
3. invoke `pkgscripts-ng/PkgCreate.py` for the `av_imgdata` package with the provided options

During the toolkit build, the package build script also builds and verifies the
native C++ components:

1. `av-imgdata-face-processor`
2. native face processor smoke checks
3. native face processor functional checks when model files are available
4. `av-imgdata-image-processor` with libvips when `AV_IMGDATA_WITH_VIPS` is not
   set to `0`

The native face processor is required for the current package. It needs an
ONNXRuntime C API distribution for the active toolkit target. The build helper
looks for it in the configured/default native dependency locations, or in
`ONNXRUNTIME_ROOT`:

```text
include/onnxruntime_c_api.h
lib/libonnxruntime.so
```

The native libvips image processor is built by default and can be disabled for a
package build with:

```bash
AV_IMGDATA_WITH_VIPS=0 source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

When enabled, the libvips build includes packaged shared libraries and license
material for libvips, libheif, and libde265. The package install step fails fast
if required native binaries or runtime libraries are missing.

The UI build is intentionally executed by the Synology toolkit build chain via
the package Makefiles. This keeps the tested package build path identical to the
actual DSM package build path.

If any structure check, Python test, UI build, or toolkit package build step fails,
the package build fails.

Arguments passed to `build-package.sh` are forwarded to `PkgCreate.py` as options.
The package name is always appended by the wrapper as `av_imgdata`, so do not pass
`-c av_imgdata` yourself. The wrapper also adds `-c` by default when no options are
passed, to collect generated SPKs into `result_spk/`.

For example:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p apollolake
```

Before the first build, prepare the Synology toolkit environment, for example:

```bash
cd pkgscripts-ng
./EnvDeploy -v 7.3 -p geminilake
cd ..
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Generated packages are collected by the toolkit in:

```text
result_spk/
```

Depending on the toolkit configuration, both a regular package and a
`_debug.spk` may be generated.

Native build artifacts are created under:

```text
build/native/<platform>/
```

The package wrapper temporarily moves local development artifacts such as
`.test-venv`, `ui/node_modules`, Python caches, and native build directories out
of the way before it links the source tree into the Synology toolkit build
environment, then restores them after the build.

## Runtime Database

All mutable package state is stored in the package-local SQLite database. This
includes name mappings, suppressions, check findings, face-match findings,
internal candidate snapshots, runtime progress, and the latest analysis result:

```text
${SYNOPKG_PKGVAR}/imgdata.sqlite3
```

Existing `name_mappings.json`, findings JSON files, runtime-state JSON files,
`file_analysis.json`, and check-ignore text files are imported exactly once
during the SQLite upgrade migration. Operational reads and writes then use
SQLite exclusively.
The legacy source files are retained, while subsequent changes are written only
to SQLite. Backups should include `imgdata.sqlite3` and, when present,
`imgdata.sqlite3-wal` and `imgdata.sqlite3-shm`.

The active face-match findings can be queried over DSM SSH with:

```bash
sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT position, action, image_path, source_name FROM face_match_finding_entries ORDER BY position;"
```

Check findings and persisted runtime state can be queried with:

```bash
sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT finding_type, entry_count, status FROM persisted_findings ORDER BY finding_type;"

sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT key, updated_at FROM app_state ORDER BY key;"
```

The package does not keep a continuously growing `server.log`. Uvicorn access
logging and routine shell logging are disabled. Existing legacy `server.log`
files are removed when the package starts. Optional backend diagnostics remain
available through the separately bounded `backend-debug.log`.

## UI Development

The package UI is located in [`ui/`](./ui) and is based on Vue 2 with Synology
DSM UI components.

Useful commands for UI-only development:

```bash
cd ui
pnpm install
pnpm run build
```

For package builds, use the package build wrapper instead:

```bash
cd ../..
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The wrapper runs structure checks and Python tests before invoking the Synology
toolkit. The UI is then built by the toolkit through the same Makefile path used
for the final package.

Notes:

- The package build itself is driven by the Synology toolkit.
- The DSM desktop app configuration is defined in [`ui/app.config`](./ui/app.config).
- UI texts follow Synology's `texts/<locale>/strings` structure.

## Runtime Configuration

The default package configuration is shipped in [`var/config.json`](./var/config.json).

At runtime, DSM uses a writable package-var directory. The active configuration is typically stored at:

```text
/var/packages/AV_ImgData/var/config.json
```

Depending on the DSM environment, `SYNOPKG_PKGVAR` may point to another package-var location such as `/volume1/@appdata/AV_ImgData/`.

The currently supported configuration areas include:

- `files.USE_EXIFTOOL`
- `files.IMAGE_DECODER_ENABLED`
- `files.IMAGE_DECODER_EXTENSIONS`
- `files.IMAGE_DECODER_ORDER`
- `files.IMAGE_DECODER_MAX_EDGE`
- `files.RECOGNITION_IMAGE_MAX_EDGE`
- `files.IMAGE_DECODER_TIMEOUT_SECONDS`
- `files.PATHEXIFTOOL`
- `metadata.SCHEMAS.ACD`
- `metadata.SCHEMAS.MICROSOFT`
- `metadata.SCHEMAS.MWG_REGIONS`
- `photos.MAX_PHOTOS_PERSONS`
- `native_processors.FACE_PROCESSOR`
- `native_processors.IMAGE_PROCESSOR_VIPS`

`native_processors.FACE_PROCESSOR` controls the package-shipped C++ face
processor, including the InsightFace-compatible ONNX model root/name and status
cache/timeout settings.

`native_processors.IMAGE_PROCESSOR_VIPS` controls the optional libvips backend.
It is packaged by default, but the runtime default is `ENABLED: false`. When
enabled and available, it can be preferred over the default image backend and can
fall back to the default backend when configured to do so.

Name mappings are stored in the package-local SQLite database:

```text
/var/packages/AV_ImgData/var/imgdata.sqlite3
```

An existing `name_mappings.json` is retained as a migration source and imported
exactly once.

## Package Layout

- [`src/`](./src): backend code
- [`ui/`](./ui): DSM desktop UI
- [`processors/native/`](./processors/native): package-shipped C++ processors
- [`processor_contract/`](./processor_contract): JSON contracts for native jobs/results
- [`scripts/`](./scripts): Synology package lifecycle scripts
- [`SynoBuildConf/`](./SynoBuildConf): Synology build instructions
- [`tools/`](./tools): build, smoke-test, and package helper scripts
- [`conf/`](./conf): package privilege/resource config

## Localization

The primary project language for documentation and defaults is English.

Current UI locales:

- `enu`
- `ger`

## Support

If you like this work, or if it inspires you or your AI to build something new, please support the project.

- Buy me a coffee: <https://ko-fi.com/andreasvilippus>
- Donate via PayPal: <https://www.paypal.com/donate/?hosted_button_id=QNGJ8D92V99GN>
- Support development

## License

This project is licensed under the MIT License. See [`LICENSE`](./LICENSE).
