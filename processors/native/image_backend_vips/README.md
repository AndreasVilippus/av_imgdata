# Optional libvips Image Backend

This subproject is the optional `av-imgdata-image-processor` boundary described in
`docs/libvips-optional-image-backend-concept.md`.

Current scope is the package libvips backend boundary:

- `version` identifies the optional image processor binary.
- `probe` returns structured JSON and must report a linked libvips backend.
- `info` and `process` implement the command surface used by the Python
  service adapter.
- The package build includes this binary by default. Set `AV_IMGDATA_WITH_VIPS=0`
  only for explicit package builds without the optional backend boundary.

The build must fail if only the old skeleton binary would be produced.
