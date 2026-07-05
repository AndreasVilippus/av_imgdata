# Native Face Processor Status Concept

## Purpose

This document reviews and defines the status model for the native C++ face processor on the `C/C++-component-test` branch.

The branch has moved away from runtime Python `InsightFace` / `OpenCV` / `ONNXRuntime` package status. The relevant production component is now the native C++ `av-imgdata-face-processor` binary with ONNXRuntime C API and package-local libraries.

The status model must therefore report native processor readiness, not pip package readiness.

## Current Implementation Review

### Backend status endpoint

Current endpoint:

```text
POST /api/insightface_status
```

Current backend return shape:

```json
{
  "insightface": {
    "label": "InsightFace",
    "enabled": true,
    "model_root_configured": "",
    "model_name_configured": "",
    "model_status": {},
    "active_model_name": "buffalo_l",
    "processor_backend": "native",
    "native_processor_status": {},
    "status_blocks": []
  },
  "native_processors": {
    "FACE_PROCESSOR": {}
  }
}
```

This is structurally useful because it already exposes both the model layer and the native processor layer.

However, the public naming still emphasizes `InsightFace` and older package status semantics.

### Native processor status service

Current status logic in `NativeFaceProcessorService.status()` handles:

```text
disabled
insightface_license_not_acknowledged
binary_missing
binary_not_executable
version_failed
skeleton_no_inference
onnxruntime_smoke_only
probe_failed
ready
```

The service also exposes:

```text
enabled
path
present
executable
available
reason
version_result
version
backend
model_root
model_name
probe_result
heif_decoder_available
inference_available
hot_path_available
last_error
```

This is mostly correct for the new C++ direction.

### Current production gate

The backend correctly uses a strict production gate:

```text
hot_path_available == true
and
backend == native
```

Only that state may be used for InsightFace-compatible face processing.

This is correct and should remain the hard runtime gate.

## Main Gap

The implementation is functionally close, but the status concept needs cleanup in three areas:

```text
1. Naming
2. Status detail completeness
3. UI grouping
```

## Naming Problem

The status endpoint and UI still use `InsightFace` as the top-level label.

That is partially correct for:

```text
- model compatibility
- model root
- model name
- model license acknowledgement
- InsightFace-compatible model archive handling
```

It is no longer correct for:

```text
- runtime package status
- inference backend availability
- OpenCV/onnxruntime Python import checks
- pip package status
```

Recommended naming split:

```text
InsightFace-compatible models
  = model storage and license context

Native face processor
  = runtime C++ processor status

Python packages
  = removed from production status
```

## Recommended Status Shape

The endpoint may remain `/api/insightface_status` short-term for compatibility, but the payload should become clearer.

Recommended shape:

```json
{
  "insightface": {
    "label": "InsightFace-compatible models",
    "enabled": true,
    "model_root_configured": "",
    "model_name_configured": "",
    "model_status": {
      "root": "...",
      "model_store": "...",
      "models": []
    },
    "active_model_name": "buffalo_l",
    "license_acknowledged": true
  },
  "native_processors": {
    "FACE_PROCESSOR": {
      "label": "Native face processor",
      "enabled": true,
      "available": true,
      "hot_path_available": true,
      "inference_available": true,
      "reason": "ready",
      "backend": "native",
      "path": "/var/packages/AV_ImgData/target/bin/av-imgdata-face-processor",
      "present": true,
      "executable": true,
      "version": "av-imgdata-face-processor 0.5.0-onnxruntime-native-heif",
      "model_root": "...",
      "model_name": "buffalo_l",
      "heif_decoder_available": false,
      "probe_result": {
        "ok": true,
        "returncode": 0,
        "output": "..."
      },
      "ort": {
        "intra_threads": 0,
        "graph_opt_level": "all"
      },
      "runtime": {
        "persistent_worker_supported": true,
        "persistent_worker_last_state": "unknown"
      },
      "diagnostics": {
        "last_error": "",
        "version_result": {}
      }
    }
  },
  "status_blocks": [
    {
      "key": "native_face_processor",
      "label_key": "status:native_face_processor",
      "fallback_label": "Native face processor",
      "value": "ready"
    }
  ]
}
```

## Required Status Reasons

The following reason values should be stable and tested:

```text
disabled
insightface_license_not_acknowledged
binary_missing
binary_not_executable
version_failed
skeleton_no_inference
onnxruntime_smoke_only
probe_failed
ready
```

Add future-compatible values:

```text
platform_unsupported
library_missing
model_missing
model_invalid
timeout
unexpected_result
worker_unavailable
```

Mapping guidance:

| Reason | Available | Hot path | User action |
|---|---:|---:|---|
| disabled | false | false | enable processor |
| insightface_license_not_acknowledged | false | false | acknowledge model license |
| binary_missing | false | false | reinstall/rebuild package |
| binary_not_executable | false | false | package permission/build fix |
| version_failed | false | false | inspect binary/library linkage |
| skeleton_no_inference | false | false | rebuild native backend |
| onnxruntime_smoke_only | false | false | complete native implementation |
| probe_failed | false | false | install/configure model files |
| ready | true | true | none |
| library_missing | false | false | package libonnxruntime/libjpeg correctly |
| model_missing | false | false | install model |
| model_invalid | false | false | replace model archive |
| timeout | false | false | tune timeout/check runtime |
| unexpected_result | false | false | inspect processor output/schema |

## Status Blocks For UI

Current UI renders `status_blocks` generically. That is useful and should continue.

Required blocks:

```text
native_face_processor
native_face_processor_version
native_face_processor_backend
native_face_processor_hot_path
native_face_processor_model
native_face_processor_heif_decoder
native_face_processor_ort_threads
native_face_processor_ort_graph_opt
native_face_profiles
```

Example:

```json
[
  {
    "key": "native_face_processor",
    "label_key": "status:native_face_processor",
    "fallback_label": "Native face processor",
    "value": "ready"
  },
  {
    "key": "native_face_processor_backend",
    "label_key": "status:native_face_processor_backend",
    "fallback_label": "Backend",
    "value": "native"
  },
  {
    "key": "native_face_processor_hot_path",
    "label_key": "status:native_face_processor_hot_path",
    "fallback_label": "Production hot path",
    "value": "yes"
  },
  {
    "key": "native_face_processor_model",
    "label_key": "status:native_face_processor_model",
    "fallback_label": "Active model",
    "value": "buffalo_l"
  }
]
```

## Runtime Progress Versus Component Status

Separate these concerns:

```text
Component readiness status:
  /api/insightface_status
  reports binary/model/backend readiness

Operation progress status:
  face_match_progress
  cleanup_progress
  checks_progress
  reports current running jobs

Debug/performance timing:
  backend-debug.log
  reports per-run native_timing_ms fields
```

Do not mix phase timing into readiness status except for the most recent diagnostic summary, if explicitly added later.

## Current Correct Implementation Points

Correct in current code:

```text
- NativeFaceProcessorService owns native binary probing.
- NativeFaceProcessorService rejects disabled, missing binary, non-executable binary, skeleton and smoke-only states.
- ImgDataService gates use through hot_path_available and backend=native.
- /api/insightface_status exists and returns native_processors.FACE_PROCESSOR.
- UI renders generic status_blocks.
- generated profile count remains visible.
```

## Current Extension Needs

Backend extension needs:

```text
1. Add `license_acknowledged` to the model/InsightFace part of the payload.
2. Add `label` to native_processors.FACE_PROCESSOR.
3. Add `ort` subobject with intra_threads and graph_opt_level.
4. Add stable status blocks for backend, version, hot_path, model, HEIF decoder and ORT settings.
5. Normalize `last_error` into `diagnostics.last_error` while keeping old field for compatibility if needed.
6. Add future placeholder for IMAGE_PROCESSOR_VIPS status when libvips feature lands.
```

UI extension needs:

```text
1. Rename status page section from `InsightFace` to `Face recognition` or `Native face recognition`.
2. Keep a sublabel for `InsightFace-compatible models`.
3. Show Native face processor status as the primary runtime status.
4. Show `hot_path_available` explicitly.
5. Show active model and model root separately.
6. Show backend and processor version.
7. Show HEIF decoder status.
8. Show ORT tuning values.
9. Remove any remaining pip/package wording from native processor status.
```

Test extension needs:

```text
1. Unit tests for every NativeFaceProcessorService.status reason.
2. API contract test for /api/insightface_status payload shape.
3. UI contract test that status_blocks are rendered generically.
4. Test that backend=native + hot_path_available=true is required for _useNativeFaceProcessor.
5. Test that python/pip status is not required for native readiness.
6. Future test for IMAGE_PROCESSOR_VIPS block staying optional.
```

## Suggested API Compatibility Plan

Keep this endpoint for now:

```text
POST /api/insightface_status
```

Add a future alias:

```text
POST /api/native_processors_status
```

Future alias response:

```json
{
  "native_processors": {
    "FACE_PROCESSOR": {},
    "IMAGE_PROCESSOR_VIPS": {}
  },
  "models": {
    "INSIGHTFACE_COMPATIBLE": {}
  }
}
```

Do not remove `/api/insightface_status` until UI and tests have moved.

## libvips Status Extension

When optional libvips support is added, it should appear as a separate block:

```json
{
  "native_processors": {
    "IMAGE_PROCESSOR_VIPS": {
      "label": "libvips image backend",
      "enabled": false,
      "preferred": true,
      "available": false,
      "reason": "disabled",
      "backend": "libvips",
      "path": "bin/av-imgdata-image-processor",
      "formats": {
        "jpeg": false,
        "png": false,
        "webp": false,
        "tiff": false,
        "heif": false
      },
      "fallback": "default_image_backend"
    }
  }
}
```

libvips status must not influence face inference readiness unless it is explicitly used as the selected preprocessing backend.

## Acceptance Criteria

The status model is correct when:

```text
- native processor readiness is visible without referring to pip package status
- disabled/license/binary/model/probe failures produce stable reason values
- production readiness requires backend=native and hot_path_available=true
- UI shows active model, native backend, processor version and readiness reason
- model status and runtime processor status are separate but visible together
- libvips can be added as separate optional image backend status later
```

## Final Decision

```text
Status source of truth = backend NativeFaceProcessorService + ImgDataService status assembly
Production gate = backend=native and hot_path_available=true
InsightFace wording = model compatibility/licensing only
Native face processor wording = runtime/inference readiness
Pip package status = removed from production status concept
libvips = future optional IMAGE_PROCESSOR_VIPS status block, not part of face inference readiness by default
```
