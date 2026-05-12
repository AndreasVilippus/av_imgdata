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

## Supported Environment

- DSM `7.3` or newer
- Package architecture: `noarch`
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

Use the package build wrapper from the toolkit root:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The wrapper performs the required preflight steps before invoking the Synology
toolkit package build:

1. run the Python test suite
2. install UI dependencies with `pnpm`
3. build the UI
4. invoke `pkgscripts-ng/PkgCreate.py` for the `av_imgdata` package with the provided options

If any Python test or the UI build fails, the package build is not started.

Arguments passed to `build-package.sh` are forwarded to `PkgCreate.py` as options.
The package name is always appended by the wrapper as `av_imgdata`, so do not pass
`-c av_imgdata` yourself. For example:

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

The wrapper runs the Python tests and UI build before invoking the Synology
toolkit. This keeps local package builds aligned with the expected release
preflight checks.

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
- `files.PATHEXIFTOOL`
- `metadata.SCHEMAS.ACD`
- `metadata.SCHEMAS.MICROSOFT`
- `metadata.SCHEMAS.MWG_REGIONS`
- `photos.MAX_PHOTOS_PERSONS`

Name mappings are stored separately in:

```text
/var/packages/AV_ImgData/var/name_mappings.json
```

## Package Layout

- [`src/`](./src): backend code
- [`ui/`](./ui): DSM desktop UI
- [`scripts/`](./scripts): Synology package lifecycle scripts
- [`SynoBuildConf/`](./SynoBuildConf): Synology build instructions
- [`conf/`](./conf): package privilege/resource config

## Localization

The primary project language for documentation and defaults is English.

Current UI locales:

- `enu`
- `ger`

## Support

If you like this work, or if it inspires you or your AI to build something new, please support the project.

- Buy me a coffee: https://ko-fi.com/andreasvilippus
- Donate via PayPal: https://www.paypal.com/donate/?hosted_button_id=QNGJ8D92V99GN
- Support development

## License

This project is licensed under the MIT License. See [`LICENSE`](./LICENSE).
