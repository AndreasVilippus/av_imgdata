# Face Model Governance

AV ImgData must not ship face model files in the repository, SPK, or external worker bundles.

## Ownership

The DSM package is the authority for:

```text
- showing the model usage notice
- recording administrator acknowledgement
- importing or downloading model files
- storing the model manifest
- making model files available to workers
```

The external worker is an execution component only. It does not decide whether a model may be used. It only reports whether the configured model files and acknowledgement metadata are present.

## DSM-managed model store

Recommended package-local layout:

```text
var/models/face/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

`manifest.json` should describe the model pack, required files, source, hashes, and package compatibility.

`LICENSE_ACK.json` should record that the DSM package showed the usage notice and that an administrator accepted it before model use.

Example acknowledgement shape:

```json
{
  "model_pack": "buffalo_l",
  "source": "insightface",
  "usage_notice_shown": true,
  "accepted_by": "admin",
  "accepted_at": "2026-07-07T20:00:00Z",
  "package_version": "unknown"
}
```

## Worker-local model layout

Workers may receive or mount the DSM-managed model directory, or an administrator may place files manually for local tests:

```text
worker/models/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

The worker bundle still ships only `models/README.txt`; no ONNX model files are included.

## Probe contract

The worker `probe` reports model state separately from processor state:

```json
{
  "models": {
    "managed_by": "dsm_or_manual",
    "distributed_with_worker": false,
    "usage_ack_required": true,
    "models_present": false,
    "manifest_present": false,
    "license_ack_present": false
  }
}
```

Capabilities are advertised only when:

```text
- face processor binary exists
- face processor version command succeeds
- required model files exist
- native processor probe succeeds
```

`LICENSE_ACK.json` is reported but not enforced by the worker. Enforcement belongs to the DSM package because the DSM package owns user/admin consent and model lifecycle.
