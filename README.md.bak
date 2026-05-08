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

To build it, clone this repository into the toolkit's `source/` directory so that the package is available as `source/av_imgdata`.

At installation time, the package creates and uses its own Python virtual environment for backend dependencies.

Example setup flow from the toolkit root:

```bash
cd pkgscripts-ng
./EnvDeploy -v 7.3 -p geminilake
./PkgCreate.py -v 7.3 -p geminilake -c av_imgdata
```

Generated packages are collected by the toolkit in:

```text
result_spk/
```

Depending on the toolkit configuration, both a regular package and a `_debug.spk` may be generated.

## UI Development

The package UI is located in [`ui/`](./ui) and is based on Vue 2 with Synology DSM UI components.

Useful commands:

```bash
cd source/av_imgdata/ui
pnpm install
pnpm run build
```

Note:

- The package build itself is still driven by the Synology toolkit.
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
