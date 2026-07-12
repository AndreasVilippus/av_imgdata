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

The external worker is an execution component only. It does not decide whether a model may be used and does not keep a second local acknowledgement record. A worker may use models only after the DSM package has authorized their distribution.

## Single source of truth

All DSM-side consumers must resolve InsightFace paths through:

```text
src/services/face_model_path_service.py
```

This includes the local native processor, UI/status reporting, model distribution, and external-worker provisioning. Consumers must not introduce their own `.insightface`, `.models/face`, or `insightface_models` fallback logic.

Resolution order:

```text
1. native_processors.FACE_PROCESSOR.MODEL_ROOT, when explicitly configured
2. $SYNOPKG_PKGVAR/insightface_models
```

The model store is always `<MODEL_ROOT>/models`, and the active model directory is `<MODEL_ROOT>/models/<MODEL_NAME>`.

## DSM model store layout

Default DSM package runtime layout:

```text
$SYNOPKG_PKGVAR/insightface_models/models/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
  LICENSE_ACK.json
```

A configured `native_processors.FACE_PROCESSOR.MODEL_ROOT` takes precedence. For example, `MODEL_ROOT=/volume1/models/insightface` resolves to:

```text
/volume1/models/insightface/models/buffalo_l/
```

`manifest.json` describes the model pack, source, file presence, hashes, and package compatibility.

`LICENSE_ACK.json` exists only in the DSM-controlled model store. It records that the DSM package showed the usage notice and that an administrator accepted it before model use or distribution.

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
src/services/face_model_path_service.py
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

`acknowledge` writes the DSM-side `LICENSE_ACK.json` and also sets the legacy config flag `native_processors.FACE_PROCESSOR.INSIGHTFACE_LICENSE_ACKNOWLEDGED=true` for compatibility with the current native processor status gate.

A manual import helper still exists for ad-hoc copies, but the preferred flow is to place model files directly in the resolved model directory and use `status`/`acknowledge`/manifest generation around that fixed path.

## Worker-local model layout

Workers use a hidden model directory after authorized synchronization:

```text
worker-runtime/.models/face/buffalo_l/
  det_10g.onnx
  w600k_r50.onnx
  manifest.json
```

Workers do not create or require a local `LICENSE_ACK.json`. The DSM package validates acknowledgement before it serves the manifest or model files.

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

The worker `probe` reports executable model state only:

```json
{
  "models": {
    "managed_by": "dsm",
    "distributed_with_worker": false,
    "license_authority": "dsm",
    "models_present": true,
    "manifest_present": true
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

Worker readiness never depends on a worker-local acknowledgement file. License enforcement belongs exclusively to the DSM package because it owns administrator consent and the model distribution endpoint.
