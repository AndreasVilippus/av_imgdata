# Optional Worker Concept

## Purpose

This document describes the optional worker architecture for `av_imgdata` on the current `main` branch.

The DSM package remains the authority for:

```text
- configuration
- authentication/session handling
- DSM and Synology Photos integration
- job ownership
- status ownership
- progress ordering
- conflict handling
- final writes
- persistence
```

Expensive processing may run through:

```text
- local package-shipped native C++ face processor
- local package-shipped optional native libvips image processor
- local persistent C++ face processor subprocess mode
- future external worker runtime executing compatible processor binaries/modules
```

The first external-worker step should be a UI-free C++ based worker runtime. It should run as a console/service/daemon process, read a local config file or environment variables, connect to the DSM package through a Worker API, poll work, execute local processor binaries, and upload structured results. A worker UI is not required for the first implementation.

The external worker remains optional. The native C++ face processor is the required production path for InsightFace-compatible face processing in this branch.

## Current Branch Facts

Implemented branch facts:

```text
- package build invokes tools/build-native-face-processor.sh unconditionally
- package build runs native smoke checks and functional checks
- package install fails if av-imgdata-face-processor is missing
- package install fails if the native processor does not report onnxruntime-native
- package install requires package-local libonnxruntime.so*
- CMake requires ONNXRUNTIME_ROOT
- CMake requires libjpeg through JPEG_ROOT or the Toolkit/sysroot
- HEIF support is optional at build time and loaded dynamically at runtime
- python_bridge is not a selectable CMake backend
- src/services/native_face_processor_worker.py is not present
- the backend calls the binary through NativeFaceProcessorService
- only a native backend with hot_path_available=true is accepted for production face processing
```

Current native face processor command surface:

```text
av-imgdata-face-processor version
av-imgdata-face-processor probe --model-root <path> --model-name <name>
av-imgdata-face-processor self-test --model-root <path> --model-name <name>
av-imgdata-face-processor detect --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor embed --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor detect_batch --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor embed_batch --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor rank_embeddings --input <job-input.json> --output <processor-result.json>
av-imgdata-face-processor profile_math --input <job-input.json> --output <processor-result.json>
av-imgdata-face-processor worker
```

Current optional native image processor status:

```text
- SynoBuildConf/build builds av-imgdata-image-processor when AV_IMGDATA_WITH_VIPS=1
- SynoBuildConf/install packages av-imgdata-image-processor and libvips libraries when enabled
- NativeImageProcessorVipsService exposes status/probe/version/process/process-batch behavior
- ImageDecodeService can prefer libvips for configured formats and can batch-decode through the native vips processor
- libvips is an image preprocessing/format backend, not a face inference backend
```

Observed and documented performance direction:

```text
- process-per-image Python/InsightFace execution was measured as too slow
- C++ native ONNXRuntime execution is now the replacement path
- persistent local worker mode exists for model/session reuse
- external worker runtime is still future work
```

## Architecture Summary

```text
DSM package
  = controller, config owner, status owner, job owner, final write owner

Web UI
  = browser UI for configuration, status, progress and logs
  = not part of the first external worker runtime

Local native C++ face processor
  = package-shipped av-imgdata-face-processor
  = built by Synology Toolkit for the selected DSM platform
  = executes bounded ProcessorContract jobs
  = supports single-image, batch, ranking, profile math and persistent stdin/stdout mode

Optional local native image processor
  = package-shipped av-imgdata-image-processor when AV_IMGDATA_WITH_VIPS=1
  = executes libvips-based image operations and batch operations
  = feeds decoded/preprocessed JPEG data back into face processing when configured

Local native persistent face processor mode
  = av-imgdata-face-processor worker
  = stdin/stdout JSON request loop
  = local-only optimization for model/session reuse
  = not an external DSM worker

Optional external worker runtime
  = separate runtime outside the DSM backend process
  = first implementation should be UI-free C++
  = registers with DSM
  = heartbeats and polls jobs
  = downloads inputs through DSM API
  = executes compatible local processor binaries/modules
  = validates and uploads ProcessorResult

ProcessorContract
  = language-neutral anti-duplication boundary
```

## Current Implementation Status

Already present:

```text
processors/native/face_processor/
  CMakeLists.txt
  src/main.cpp

tools/build-native-face-processor.sh
tools/smoke-native-face-processor.sh
tools/functional-native-face-processor.sh

src/services/native_face_processor_service.py

processor_contract/
  README.md
  schemas/face-native-job-input.schema.json
  schemas/face-native-result.schema.json

processors/native/image_processor_vips/          # if present in build tree
src/services/native_image_processor_vips_service.py
src/services/image_decode_service.py

tools/build-native-image-processor-vips.sh       # optional vips path
```

No longer present / no longer production path:

```text
src/services/native_face_processor_worker.py
python_bridge CMake backend
runtime pip/wheelhouse installation path for InsightFace/OpenCV/ONNXRuntime as production backend
```

Not present yet for external workers:

```text
worker/ runtime project
UI-free C++ worker executable
DSM Worker API routes
worker registration endpoint
worker heartbeat endpoint
job polling endpoint
job status endpoint
worker log endpoint
Variant B file download endpoint
result upload endpoint
optional artifact upload endpoint
worker token/capability persistence
worker assignment scheduler
external worker config format
external worker packaging for Windows/Linux/Docker
remote JobInput translation from DSM asset references to local worker files
worker-side ProcessorResult schema validation
worker-side backoff/retry/dead-letter handling
worker-side local workspace cleanup policy
```

## Local Persistent Processor Versus External Worker

### Local persistent processor

```text
DSM Backend
  -> NativeFaceProcessorService
  -> av-imgdata-face-processor worker
  -> stdin/stdout JSON
  -> local temp file paths
  -> local ProcessorResult JSON
```

Properties:

```text
- runs on the same DSM/NAS system as the backend
- receives local temp paths
- does not register with DSM
- does not call DSM APIs
- does not download or upload files
- may reuse loaded ONNXRuntime sessions and models
- is an optimization inside NativeFaceProcessorService
- supports model reuse only while model_root/model_name stay unchanged in one process
```

### External worker

```text
External Worker Runtime
  -> DSM Worker API client
  -> registration
  -> heartbeat
  -> job polling
  -> Variant B file download
  -> local temp workspace
  -> local processor execution
       -> av-imgdata-face-processor
       -> optionally av-imgdata-image-processor
  -> ProcessorResult validation
  -> result upload
```

Properties:

```text
- runs outside the DSM backend process, e.g. Linux host, Windows host, Docker, cloud host, or a second local machine
- first implementation should be UI-free C++
- must authenticate to DSM
- must download input files through DSM API
- must create worker-local job-input.json with worker-local file paths
- may use the same av-imgdata-face-processor command surface
- may use av-imgdata-image-processor when image preprocessing is delegated to the worker
- must upload results to DSM
- must not own final DSM writes
```

Rule:

```text
av-imgdata-face-processor is reusable by an external worker as ProcessorCore.
It is not itself the external worker runtime.
```

## External Worker Execution Targets

Supported target model after worker support exists:

```text
JobDispatcher
  -> LocalNativeProcessorAdapter
  -> RemoteWorkerProcessorAdapter
  -> LocalBackendProcessorAdapter only where a non-face fallback still exists
```

For InsightFace-compatible face processing on this branch:

```text
local native C++ = required production path
python_bridge = not production path
local backend fallback = not available for InsightFace-compatible face processing
external worker = optional future execution target
```

Target selection rules:

```text
1. DSM creates and owns the job.
2. DSM checks configured target preference.
3. DSM checks local native processor status.
4. DSM checks registered worker capabilities if remote execution is enabled.
5. DSM assigns one compatible execution target.
6. DSM validates ProcessorResult before committing any result.
```

Recommended target order for face jobs after worker support exists:

```text
1. remote_worker if configured as preferred and compatible
2. local_native if ready and hot_path_available=true
3. fail with actionable native processor status if no compatible target exists
```

For normal default behavior:

```text
1. local_native
2. remote_worker if configured and compatible
3. fail with status reason
```

## UI-Free C++ Worker Bootstrap

The first external worker implementation should be a small C++ runtime with no UI and no DSM write ownership.

Minimum executable shape:

```text
av-imgdata-worker run --config <worker-config.json>
av-imgdata-worker once --config <worker-config.json>
av-imgdata-worker probe --config <worker-config.json>
av-imgdata-worker version
```

Minimum config:

```json
{
  "worker_id": "worker-01",
  "dsm_base_url": "https://nas.example:5001",
  "auth": {
    "type": "worker_token",
    "token_file": "./worker.token"
  },
  "workspace_root": "./work",
  "processors": {
    "face": {
      "path": "./bin/av-imgdata-face-processor",
      "model_root": "./models",
      "model_name": "buffalo_l"
    },
    "image_vips": {
      "enabled": false,
      "path": "./bin/av-imgdata-image-processor"
    }
  },
  "poll_interval_seconds": 2,
  "max_parallel_jobs": 1,
  "log_level": "info"
}
```

Bootstrap behavior:

```text
1. read config
2. probe local processor binaries
3. build capability payload
4. register with DSM
5. heartbeat periodically
6. poll next job
7. download referenced asset to a local workspace
8. translate DSM worker job payload to ProcessorContract input
9. execute local processor binary or persistent local processor session
10. validate result JSON
11. upload result/status/logs
12. clean workspace according to retention policy
```

The first version should keep `max_parallel_jobs=1` unless the DSM assignment model, model memory use, and processor process model are explicitly made concurrency-safe.

## Functions That Must Be Available Locally In An External Worker

This section is the functional checklist for a local external worker. "Local" means local to the worker host, not local to DSM.

### 1. Worker runtime control functions

Must exist in the worker executable:

| Function | Required for first C++ worker | Already available in repo | Notes |
|---|---:|---:|---|
| Read worker config | Yes | No | New worker runtime responsibility. |
| Validate config | Yes | No | Validate DSM URL, token source, workspace, processor paths, model config. |
| Probe local face processor | Yes | Partly | Processor has `version` and `probe`; worker wrapper does not exist yet. |
| Probe optional image processor | Optional | Partly | Vips service exists in DSM backend; worker wrapper does not exist yet. |
| Build capability payload | Yes | No | Must be based on successful probes, not static config. |
| Register worker | Yes | No | Requires DSM API route and persistence. |
| Heartbeat | Yes | No | Requires DSM API route and liveness state. |
| Poll jobs | Yes | No | Requires DSM API route and scheduler. |
| Report job started/running/failed/completed | Yes | No | Requires DSM API route. |
| Upload logs | Optional first, recommended | No | Helps diagnose remote failures. |
| Workspace cleanup | Yes | No | Must prevent stale downloaded assets and result files. |
| Retry/backoff | Yes | No | Required for network and temporary DSM/API failures. |
| Service/daemon mode | Yes | No | Windows service/systemd/Docker entrypoint later. |

### 2. DSM API client functions

Must exist in the worker executable or worker support library:

| Function | Required | Current state |
|---|---:|---|
| Authenticate with worker token | Yes | Not implemented. |
| POST worker registration | Yes | Not implemented. |
| POST heartbeat | Yes | Not implemented. |
| GET/poll next job | Yes | Not implemented. |
| POST job status | Yes | Not implemented. |
| GET/download input asset bytes | Yes | Not implemented. |
| POST/upload ProcessorResult | Yes | Not implemented. |
| POST/upload worker logs | Recommended | Not implemented. |
| PUT/upload optional output artifact | Optional | Not implemented. |
| Renew/rotate worker token | Later | Not implemented. |

### 3. Face processor functions required on the worker host

The external worker must be able to execute these locally when it advertises the matching capabilities:

| Processor function | Capability name | Required for first worker | Exists in native processor | Notes |
|---|---|---:|---:|---|
| `version` | processor metadata | Yes | Yes | Used before registration. |
| `probe` | readiness/model check | Yes | Yes | Must verify model files and ONNXRuntime sessions. |
| `self-test` | local diagnostics | Recommended | Yes | Current implementation maps this to model probe. |
| `detect` | `face_native_detect` | Yes | Yes | Single-image face detection. |
| `embed` | `face_native_embed` | Yes | Yes | Single-image detection plus ArcFace embeddings. |
| `detect_batch` | `face_native_detect_batch` | Recommended | Yes | Useful for throughput; advertise only if tested. |
| `embed_batch` | `face_native_embed_batch` | Recommended | Yes | Functional test covers `embed_batch`. |
| `rank_embeddings` | `face_native_rank_embeddings` | Optional first, recommended | Yes | Enables offloading vector ranking if DSM delegates it. |
| `profile_math` | `face_native_profile_math` | Optional first, recommended | Yes | Enables offloading profile centroid/medoid math if DSM delegates it. |
| `worker` stdin/stdout loop | warm_processor_worker | Recommended | Yes | Allows model/session reuse on the worker host. |

Minimum first capability set:

```text
face_native_detect
face_native_embed
```

Recommended first capability set:

```text
face_native_detect
face_native_embed
face_native_detect_batch
face_native_embed_batch
face_native_rank_embeddings
face_native_profile_math
warm_processor_worker
```

### 4. Image preprocessing functions required on the worker host

These are required only when DSM assigns jobs that expect the worker to handle format conversion/preprocessing instead of receiving a DSM-prepared JPEG.

| Processor function | Required for first worker | Exists in repo | Notes |
|---|---:|---:|---|
| HEIF/HEIC decode through face processor | Optional | Yes, when built with HEIF headers and runtime decoder is available | The face processor can report `heif_decoder=available/unavailable` during probe. |
| JPEG decode through face processor | Yes | Yes | Baseline face input path. |
| `av-imgdata-image-processor version` | Optional | Yes when vips is built | Needed before advertising image_vips capability. |
| `av-imgdata-image-processor probe` | Optional | Yes through vips processor service expectations | Needed before advertising supported formats. |
| `process` resize/rotate/convert/auto-orient | Optional | Yes through NativeImageProcessorVipsService command wrapper | Required only if image preprocessing is delegated to worker. |
| `process-batch` | Optional | Yes through NativeImageProcessorVipsService command wrapper | Recommended for throughput if vips is delegated. |

Recommended first worker simplification:

```text
DSM sends original asset bytes.
Worker uses av-imgdata-face-processor for JPEG and built-in HEIF when available.
Worker advertises libvips/image preprocessing only after av-imgdata-image-processor is packaged and probed on that worker platform.
```

### 5. Contract and validation functions required on the worker host

| Function | Required | Current state |
|---|---:|---|
| Generate worker-local `face-native-job-input` JSON | Yes | Implemented only inside DSM backend service for local paths. |
| Map DSM asset reference to worker-local `input.image_path` | Yes | Not implemented. |
| Preserve `job_id`, `type`, `source_id`, model/options | Yes | Partly in local service. |
| Validate job input schema before execution | Recommended | Schema exists; worker validator not implemented. |
| Validate ProcessorResult schema before upload | Yes | Schema exists; worker validator not implemented. |
| Normalize processor exit codes/errors into DSM job status | Yes | Local service handles local exceptions; remote mapping not implemented. |
| Attach timing_ms and processor metadata | Yes | Native processor emits these for supported commands. |

Current contract job types:

```text
face_native_detect
face_native_embed
face_native_detect_batch
face_native_embed_batch
face_native_rank_embeddings
face_native_profile_math
```

The worker must not invent a separate remote result format. It must upload the same ProcessorResult shape used by local native execution.

### 6. Model/runtime files required on the worker host

A compatible worker host must provide:

```text
- av-imgdata-face-processor executable for the worker OS/architecture
- ONNXRuntime runtime library compatible with that executable
- libjpeg-compatible runtime library
- optional libheif runtime and HEVC/AV1 decoder if HEIF is advertised
- optional av-imgdata-image-processor executable if image_vips is advertised
- optional libvips runtime libraries if image_vips is advertised
- InsightFace-compatible ONNX model files, normally buffalo_l:
  - det_10g.onnx
  - w600k_r50.onnx
```

Worker registration must include the processor version, backend, model name, model readiness, supported commands, supported image formats if applicable, and relevant runtime settings.

## ProcessorContract

Current native face contracts:

```text
processor_contract/schemas/face-native-job-input.schema.json
processor_contract/schemas/face-native-result.schema.json
```

Current job types:

```text
face_native_detect
face_native_embed
face_native_detect_batch
face_native_embed_batch
face_native_rank_embeddings
face_native_profile_math
```

Required common input fields:

```text
contract_version
job_id
type
input
options
```

Required single-image input fields:

```text
input.image_path
input.source_id
options.model_root
options.model_name
options.min_confidence
options.max_faces
options.det_size
options.normalize_coordinates
```

Required batch-image input fields:

```text
input.image_paths
options.model_root
options.model_name
options.min_confidence
options.max_faces
options.det_size
options.normalize_coordinates
```

Required vector/ranking input fields by job type:

```text
face_native_rank_embeddings:
  target_embeddings
  profile_embeddings

face_native_profile_math:
  embeddings
```

Required result fields:

```text
contract_version
job_id
type
status
processor.name
processor.version
processor.backend
result
error
warnings
timing_ms
```

The same result contract must be used for local native execution and external worker execution.

## DSM Package Ownership

The DSM backend owns:

```text
- DSM integration
- API routes
- authentication/session handling
- config normalization
- native processor status probing
- local/remote/native target selection
- worker registration and token management
- worker capability persistence
- status payload building
- runtime state and progress ordering
- result validation before commit
- findings/result persistence
- final DSM and Synology Photos writes
- conflict detection and write locks
```

## Native Processor Ownership

The native C++ face processor may own:

```text
- version reporting
- probe command
- self-test command
- image decode for explicitly supported formats
- image preprocessing required by face inference
- ONNXRuntime session setup
- SCRFD detector execution and post-processing
- ArcFace embedding execution and normalization
- multi-image detect/embed batches
- embedding ranking
- profile centroid/medoid math
- local persistent stdin/stdout worker loop
- ProcessorResult JSON output
- ProcessorError JSON output
- timing_ms fields
```

The native C++ face processor must not own:

```text
- DSM authorization
- DSM API calls
- worker registration
- heartbeat
- job polling
- DSM file download/upload
- Synology Photos API calls
- findings persistence
- final write decisions
- UI state decisions
```

The optional native libvips image processor may own:

```text
- image format probe/status
- image resize
- image rotate
- image convert
- image auto-orient
- image batch processing
- decoded/preprocessed output generation
```

The optional native libvips image processor must not own:

```text
- face detection
- face embeddings
- recognition decisions
- DSM writes
- worker registration or polling
```

## External Worker Ownership

The external worker owns:

```text
- DSM Worker API client
- local config parsing
- local capability probing
- registration request
- heartbeat loop
- job polling loop
- Variant B file download
- local temp workspace
- processor execution wrapper
- optional persistent processor subprocess management
- ProcessorResult schema validation before upload
- result upload
- local logs
- service/daemon mode
- retry/backoff behavior
```

The external worker may execute:

```text
av-imgdata-face-processor detect/embed
av-imgdata-face-processor detect_batch/embed_batch
av-imgdata-face-processor rank_embeddings/profile_math
av-imgdata-face-processor worker
av-imgdata-image-processor process/process-batch when image_vips is packaged for that worker
```

The external worker must not execute:

```text
DSM metadata writes
Synology Photos person/face writes
findings persistence writes
UI state changes
configuration writes except local worker config/token state
```

## External Worker API Requirements

Minimum DSM endpoints:

```text
POST /api/worker/register
POST /api/worker/heartbeat
GET  /api/worker/jobs/next
POST /api/worker/jobs/{job_id}/status
POST /api/worker/jobs/{job_id}/result
POST /api/worker/jobs/{job_id}/log
GET  /api/worker/jobs/{job_id}/input/{asset_id}
PUT  /api/worker/jobs/{job_id}/output/{asset_id}
```

Worker-facing jobs should use asset references, not NAS-local paths.

Example DSM job payload:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "face_native_embed",
  "asset": {
    "asset_id": "asset-456",
    "filename": "image.jpg",
    "size": 1234567,
    "sha256": "optional"
  },
  "options": {
    "model_name": "buffalo_l",
    "min_confidence": 0.5,
    "max_faces": 0,
    "det_size": [640, 640],
    "normalize_coordinates": true
  }
}
```

Worker-local processor input:

```json
{
  "contract_version": "1.0",
  "job_id": "job-123",
  "type": "face_native_embed",
  "input": {
    "image_path": "/var/tmp/av-imgdata-worker/job-123/input.jpg",
    "source_id": "asset-456"
  },
  "options": {
    "model_root": "/opt/av-imgdata-worker/models",
    "model_name": "buffalo_l",
    "min_confidence": 0.5,
    "max_faces": 0,
    "det_size": [640, 640],
    "normalize_coordinates": true
  }
}
```

## Worker Capability Model

A worker must report capabilities only after local processor probe succeeds.

Example registration excerpt:

```json
{
  "worker_id": "worker-01",
  "platform": "linux",
  "arch": "amd64",
  "capabilities": [
    "face_native_detect",
    "face_native_embed",
    "face_native_detect_batch",
    "face_native_embed_batch",
    "face_native_rank_embeddings",
    "face_native_profile_math"
  ],
  "processors": [
    {
      "name": "av-imgdata-face-processor",
      "version": "av-imgdata-face-processor 0.5.0-onnxruntime-native-heif",
      "backend": "native",
      "hot_path_available": true,
      "commands": [
        "detect",
        "embed",
        "detect_batch",
        "embed_batch",
        "rank_embeddings",
        "profile_math",
        "worker",
        "probe",
        "version",
        "self-test"
      ],
      "model_name": "buffalo_l",
      "model_status": "ready",
      "heif_decoder_available": true
    }
  ],
  "features": {
    "api_file_transfer": true,
    "native_face_processor": true,
    "warm_processor_worker": true,
    "native_image_vips": false
  }
}
```

If `native_image_vips=true`, the worker must also report:

```text
- av-imgdata-image-processor version
- backend
- supported input/output formats
- process/process-batch availability
- fallback behavior
```

## Status Requirements

The face processor status model must distinguish:

```text
status_refreshing
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

For ready status, the payload must expose:

```text
enabled
available
hot_path_available
backend
path
version
model_root
model_name
probe_result
heif_decoder_available
AV_IMGDATA_ORT_INTRA_THREADS
AV_IMGDATA_ORT_GRAPH_OPT_LEVEL
last_error if present
```

The optional libvips image status model must distinguish:

```text
vips_disabled
vips_binary_missing
vips_binary_not_executable
vips_version_failed
vips_probe_failed
vips_ready
```

The optional libvips status payload must expose:

```text
enabled
preferred
available
backend
path
version
formats
fallback
probe
last_error if present
```

The face processor status must not be called a pip package status anymore.

## What Works Now

```text
- Native C++ face processor source exists.
- CMake builds av-imgdata-face-processor with ONNXRuntime C API and libjpeg.
- Optional HEIF compile-time header support and runtime decoder probing exist.
- Toolkit build path calls native face processor build.
- Toolkit build path runs smoke and functional checks.
- Package install fails fast if required native face processor or libonnxruntime is missing.
- Backend NativeFaceProcessorService probes status/version/model readiness.
- Backend executes detect/embed through processor JSON input/output files.
- Backend supports local persistent processor mode through av-imgdata-face-processor worker.
- Backend supports embed_batch through run_faces_batch.
- Native processor supports vector ranking and profile math.
- Processor contract schemas include single-image, batch, rank and profile math jobs.
- Optional native libvips image processor service exists.
- ImageDecodeService can use libvips and batch libvips decode when configured.
```

## What Does Not Work Yet

```text
- No external worker runtime exists.
- No UI-free C++ av-imgdata-worker executable exists.
- No DSM Worker API routes exist.
- No worker registration/heartbeat/job polling exists.
- No worker auth/token lifecycle exists.
- No remote worker capability persistence exists.
- No remote worker scheduler/assignment logic exists.
- No API-based asset download/result upload path exists for workers.
- No worker-side schema validation exists.
- No worker package for Windows/Linux/Docker exists.
- No remote result validation/commit pipeline exists beyond local native processor result normalization.
- No remote concurrency/backpressure/dead-letter policy exists.
```

## Implementation Phases

### Phase 1: Current native baseline

Status: implemented in branch.

```text
- native av-imgdata-face-processor required for production face processing
- ONNXRuntime C API linked through package-local libonnxruntime
- libjpeg linked for JPEG decode
- optional HEIF runtime probing
- native timing_ms emitted and copied into backend-debug fields
- detect/embed implemented
- detect_batch/embed_batch implemented
- rank_embeddings/profile_math implemented
- local persistent worker mode implemented
```

### Phase 2: Native image preprocessing baseline

Status: partly implemented / optional.

```text
- optional av-imgdata-image-processor build path exists behind AV_IMGDATA_WITH_VIPS
- DSM backend service exists for libvips status and process/process-batch calls
- ImageDecodeService can prefer libvips for configured formats
- status wording and tests should stay separate from face inference status
```

### Phase 3: Status cleanup

Required next.

```text
- rename remaining UI/status wording from InsightFace package status to Native face processor where appropriate
- keep InsightFace only for model compatibility/license wording
- expose backend, hot_path_available, model_root, model_name, ORT settings and HEIF decoder status in status_blocks
- expose separate native_processors.IMAGE_PROCESSOR_VIPS block
- add tests for every native face and vips status reason
```

### Phase 4: Worker API foundation

```text
- add worker registration/heartbeat/job polling endpoints
- add WorkerRegistryService
- add WorkerAssignmentService
- add WorkerFileTransferService
- define worker registration/capability schemas
- define worker token/auth model
- define remote job state transitions
```

### Phase 5: UI-free C++ external worker runtime

```text
- create worker/ project
- implement av-imgdata-worker run/once/probe/version
- implement DSM API client
- implement local face processor probe
- implement optional local image processor probe
- implement Variant B download/upload
- translate DSM asset jobs into worker-local ProcessorContract inputs
- execute av-imgdata-face-processor locally
- optionally keep av-imgdata-face-processor worker subprocess warm
- validate ProcessorResult before upload
- package worker for Linux first, then Windows/Docker as separate artifacts
```

### Phase 6: Worker-side optional libvips integration

```text
- keep default image path unchanged
- add optional IMAGE_PROCESSOR_VIPS capability/status to worker registration
- allow worker-side libvips preprocessing only when probe reports ready
- do not advertise image_vips unless av-imgdata-image-processor and libvips runtime are present on the worker host
```

## Final Decision

```text
DSM package = controller and file authority
C++ face processor = required production ProcessorCore for InsightFace-compatible face processing on this branch
Python bridge = removed / not production fallback
Local persistent worker mode = stdin/stdout optimization, not external DSM worker
External worker = separate runtime using DSM Worker API and compatible processor binaries
First external worker = UI-free C++ runtime
ProcessorContract = shared boundary for local and remote execution
Status model = must report native processor readiness, not pip package readiness
libvips = optional image preprocessing backend, not face inference replacement
Additional DSM platforms = optional and additive
External worker platforms = packaged separately from DSM Toolkit
```