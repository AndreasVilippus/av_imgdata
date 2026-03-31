# Function Matrix

This file is the current development-oriented overview of functions related to image files and metadata in `AV_ImgData`.

Purpose:
- show which image and metadata functions exist
- make visible which paths are native and which use ExifTool
- support development of open metadata-related topics
- reduce hidden overlap between native and ExifTool-backed behavior

## Recommended Format

Markdown is the best current format:
- readable in the repository and on GitHub
- easy to maintain in diffs
- good as a later source for UI help text or GitHub documentation

## Legend

- `yes`: supported in the current implementation
- `no`: not supported in that path
- `partial`: partially supported or supported only indirectly

## Scope

This matrix only lists functions that access files directly or call ExifTool directly.

It intentionally excludes downstream functions that merely consume already discovered or loaded metadata, for example:
- XMP parsing
- face metadata parsing
- metadata analysis and review logic

## Matrix

| Area | Function Name | Description | Native | ExifTool | Notes |
| --- | --- | --- | --- | --- | --- |
| Metadata discovery | Find matching XMP sidecar | Locate an `.xmp` file that belongs to an image file | yes | no | Sidecar matching is handled by our own filename logic, not by ExifTool |
| Metadata loading | Read XMP sidecar content | Load raw XMP text from sidecar file | yes | yes | Native is the default path; ExifTool is an optional fallback for sidecar problems |
| Metadata loading | Read embedded XMP from image | Read embedded XMP from image files | yes | yes | Native and ExifTool-backed paths both exist; ExifTool is the optional preferred helper when enabled |
| Metadata writing | Replace metadata face name | Replace one face name in XMP metadata | no | yes | Implemented only through the ExifTool-backed write path used by checks |
| Image context | Read image dimensions | Read width and height from image file | yes | yes | Native is the default path; ExifTool can be preferred by config or used as fallback |
| Image context | Read image orientation | Read image rotation/orientation metadata from image files | yes | yes | Native JPEG EXIF reader exists; ExifTool can be preferred by config or used as fallback |

## Development Notes

The most relevant overlapping areas are:
- embedded XMP loading: native parsing vs. ExifTool extraction
- sidecar XMP loading: native file read vs. ExifTool-backed read
- image context loading: native dimensions/orientation readers vs. ExifTool-backed readers

This matrix should be updated whenever:
- a new direct file-access or ExifTool-access path is added
- a parser starts calling ExifTool directly instead of consuming already loaded XMP
- native and ExifTool-backed file/context loading behavior diverge
