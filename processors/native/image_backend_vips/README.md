# Optional libvips Image Backend

This subproject is the optional `av-imgdata-image-processor` boundary described in
`docs/libvips-optional-image-backend-concept.md`.

Current scope is the Phase 2 skeleton:

- `version` identifies the optional image processor binary.
- `probe` returns structured JSON and reports that libvips is not linked yet.
- The package build includes this binary only when `AV_IMGDATA_WITH_VIPS=1`.

It intentionally does not process images until the pinned libvips dependency
bundle and license notices are added.
