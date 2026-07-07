# Face Model Governance

AV ImgData must not ship face model files in the repository, SPK, or external worker bundles.

## Ownership

The DSM package is the authority for:

```text
- showing the model usage notice
- recording administrator acknowledgement
- managing the configured model path
- storing the model manifest
- making model files available to workers
```

The external worker is an execution component only. It does not decide whether a model may be used. It only reports whether the configured model files and acknowledgement metadata are present.

## Model store layout

Default source-tree development layout when `SYNOPKG_PKGVAR` is not set:

```text
.models/face/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

Default DSM package runtime layout when `SYNOPKG_PKGVAR` is set:

```text
$SYNOPKG_PKGVAR/.models/face/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

A configured `native_processors.FACE_PROCESSOR.MODEL_ROOT` takes precedence over both defaults. The expected model pack directory is always `<MODEL_ROOT>/buffalo_l/` unless a different model pack is configured.

`manifest.json` describes the model pack, source, file presence, hashes, and package compatibility.

`LICENSE_ACK.json` records that the DSM package showed the usage notice and that an administrator accepted it before model use.

Example acknowledgement shape:

```json
{
  "model_pack": "buffalo_l",
  "source": "manual",
  "usage_notice_shown": true,
  "accepted_by": "admin",
  "accepted_at": "2026-07-07T20:00:00Z",
  "package_version": "unknown"
}
```

## Service and CLI

DSM-side implementation entry points:

```text
src/services/face_model_store_service.py
tools/face-model-store.py
```

Status:

```bash
python3 tools/face-model-store.py status
```

Acknowledge usage terms after showing the notice to the administrator:

```bash
python3 tools/face-model-store.py acknowledge --accepted-by admin --package-version "$SYNOPKG_PKGVER"
```

`acknowledge` writes `LICENSE_ACK.json` and also sets the legacy config flag `native_processors.FACE_PROCESSOR.INSIGHTFACE_LICENSE_ACKNOWLEDGED=true` for compatibility with the current native processor status gate.

A manual import helper still exists for ad-hoc copies, but the preferred flow is to place model files directly in the configured model path and use `status`/`acknowledge`/manifest generation around that fixed path.

## Worker-local model layout

Workers use a hidden model directory as well:

```text
worker-runtime/.models/face/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

The worker config default is:

```json
{
  "processors": {
    "face": {
      "model_root": "../.models/face",
      "model_name": "buffalo_l"
    }
  }
}
```

The worker bundle ships only `.models/face/README.txt`; no ONNX model files are included.

## Worker sync helper

For local development and later DSM-controlled sync, the source tree contains:

```text
tools/sync-worker-face-models.py
```

Example, sync from source-tree `.models/face` into a Linux worker dist:

```bash
python3 tools/sync-worker-face-models.py --target linux-x86_64
```

Example, sync into a Windows worker dist:

```bash
python3 tools/sync-worker-face-models.py --target windows-x86_64
```

Example, explicit worker runtime directory:

```bash
python3 tools/sync-worker-face-models.py --worker-dir /path/to/av-imgdata-worker
```

The sync helper copies only to the requested worker runtime directory. It does not add model files to Git and does not change release packaging policy.

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
