# Optional Worker Concept

## Purpose

This document describes the optional worker architecture for `av_imgdata` on the `C/C++-component-test` branch after the native C++ face processor became the required production path for InsightFace-compatible face processing.

The DSM package remains:

```text
- controller
- DSM authority
- job owner
- status owner
- final write owner
```

Expensive processing may run through:

```text
- local native C++ processor binary shipped in the SPK
- local native persistent subprocess mode for repeated jobs
- optional external worker that executes a compatible processor binary/module
```

The external worker remains optional. The native C++ processor is not optional for the InsightFace-compatible production hot path in this branch.

## Current Branch Facts

The current branch no longer treats the Python InsightFace/OpenCV/ONNXRuntime path as a production backend.

Implemented branch facts:

```text
- package build creates target/bin/av-imgdata-face-processor
- CMake requires ONNXRUNTIME_ROOT
- CMake requires libjpeg through JPEG_ROOT or the Toolkit/sysroot
- python_bridge is no longer a selectable CMake backend
- src/services/native_face_processor_worker.py has been removed
- the native processor exposes detect/embed/worker/probe/version/self-test
- the backend calls the binary through NativeFaceProcessorService
- only backend=native with hot_path_available=true is accepted for the production path
```

Observed and documented performance direction:

```text
- process-per-image Python/InsightFace execution was measured as too slow
- C++ native ONNXRuntime execution is now the replacement path
- persistent local worker mode exists, but still needs phase-level timing validation for actual speedup
```

## Architecture Summary

```text
DSM package
  = controller, status owner, job owner, final write owner

Web UI
  = browser UI for configuration, status, progress and logs

Local native C++ processor
  = package-shipped av-imgdata-face-processor
  = built by Synology Toolkit for the selected DSM platform
  = executes bounded ProcessorContract jobs

Local native persistent processor mode
  = av-imgdata-face-processor worker
  = stdin/stdout JSON request loop
  = local-only optimization for model/session reuse
  = not an external DSM worker

Optional external worker
  = separate runtime outside DSM
  = registers with DSM
  = heartbeats and polls jobs
  = downloads inputs through DSM API
  = executes compatible processor binary/module
  = uploads ProcessorResult to DSM

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

src/services/native_face_processor_service.py

processor_contract/
  README.md
  schemas/face-native-job-input.schema.json
  schemas/face-native-result.schema.json
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
DSM Worker API routes
worker registration endpoint
worker heartbeat endpoint
job polling endpoint
Variant B file download endpoint
result upload endpoint
worker capability persistence
external worker config format
external worker packaging for Windows/Linux/Docker
remote JobInput translation from DSM asset references to local worker files
worker-side ProcessorResult schema validation
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
- is an optimization inside LocalNativeProcessorAdapter
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
  -> av-imgdata-face-processor detect/embed or worker mode
  -> ProcessorResult validation
  -> result upload
```

Properties:

```text
- runs outside DSM, e.g. Linux host, Windows host, Docker or cloud host
- must authenticate to DSM
- must download input files through DSM API
- must create local job-input.json with worker-local image_path
- may use the same av-imgdata-face-processor command surface
- must upload results to DSM
- must not own final DSM writes
```

Rule:

```text
av-imgdata-face-processor is reusable by an external worker as ProcessorCore.
It is not itself the external worker runtime.
```

## Execution Targets

Supported target model:

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

## Runtime Scope On DSM

Allowed on DSM:

```text
- POSIX shell for DSM package lifecycle scripts
- package-managed backend runtime
- browser JavaScript for Web UI
- package-shipped native C/C++ binaries
- package-local shared libraries required by those binaries
- explicit external tools when configurable, status-visible, and license-aware
```

Not assumed on DSM:

```text
- Go runtime
- Rust toolchain or Rust compiler
- C/C++ compiler or build toolchain
- .NET runtime
- Ruby runtime
- user-managed Python venv
- user-installed Node.js runtime for backend execution
```

## Native Face Processor Build Policy

Canonical build command from Toolkit root:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Current build requirements:

```text
ONNXRUNTIME_ROOT/include/onnxruntime_c_api.h
ONNXRUNTIME_ROOT/lib/libonnxruntime.so
JPEG_ROOT/include/jpeglib.h
JPEG_ROOT/lib/libjpeg.so or Toolkit sysroot equivalent
optional HEIF_ROOT/include/libheif/heif.h
```

Current branch rule:

```text
The SPK must contain the ONNXRuntime-native av-imgdata-face-processor variant.
The build should fail if the native processor or package-local libonnxruntime is missing.
```

## ProcessorContract

Current native face contracts:

```text
processor_contract/schemas/face-native-job-input.schema.json
processor_contract/schemas/face-native-result.schema.json
```

Required job types:

```text
face_native_detect
face_native_embed
```

Required input fields:

```text
contract_version
job_id
type
input.image_path
input.source_id
options.model_root
options.model_name
options.min_confidence
options.max_faces
options.det_size
options.normalize_coordinates
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
result.faces
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
- status payload building
- runtime state and progress ordering
- result validation before commit
- findings/result persistence
- final DSM and Synology Photos writes
- conflict detection and write locks
```

## Native Processor Ownership

The native C++ binary may own:

```text
- version reporting
- probe command
- self-test command
- image decode for explicitly supported formats
- image preprocessing
- ONNXRuntime session setup
- SCRFD detector execution and post-processing
- ArcFace embedding execution and normalization
- local persistent stdin/stdout worker loop
- ProcessorResult JSON output
- ProcessorError JSON output
- timing_ms fields
```

The native C++ binary must not own:

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

## External Worker Ownership

The external worker owns:

```text
- DSM Worker API client
- registration request
- heartbeat loop
- job polling loop
- Variant B file download
- local temp workspace
- processor execution wrapper
- ProcessorResult schema validation before upload
- result upload
- local logs
- service/daemon mode
```

The external worker may execute:

```text
av-imgdata-face-processor detect/embed
av-imgdata-face-processor worker
future av-imgdata-image-processor when libvips feature is packaged for that worker
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
  "capabilities": ["face_native_detect", "face_native_embed"],
  "processors": [
    {
      "name": "av-imgdata-face-processor",
      "version": "av-imgdata-face-processor 0.5.0-onnxruntime-native-heif",
      "backend": "native",
      "hot_path_available": true,
      "commands": ["detect", "embed", "worker", "probe", "version"],
      "model_name": "buffalo_l",
      "model_status": "ready"
    }
  ],
  "features": {
    "api_file_transfer": true,
    "native_face_processor": true,
    "warm_processor_worker": true
  }
}
```

## Status Requirements

The status model must distinguish:

```text
disabled
license_not_acknowledged
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
ORT_INTRA_THREADS
ORT_GRAPH_OPT_LEVEL
last_error if present
```

For future libvips support, the status model must also allow a separate image backend block:

```text
native_processors.IMAGE_PROCESSOR_VIPS
```

The face processor status must not be called a pip package status anymore.

## Implementation Phases

### Phase 1: Current native baseline

Status: implemented in branch.

```text
- native av-imgdata-face-processor required for production face processing
- ONNXRuntime C API linked through package-local libonnxruntime
- libjpeg linked for JPEG decode
- native timing_ms emitted and copied into backend-debug fields
```

### Phase 2: Status cleanup

Required next.

```text
- rename UI/status wording from InsightFace package status to Native face processor where appropriate
- keep InsightFace only for model compatibility/license wording
- expose backend, hot_path_available, model_root, model_name, ORT settings and HEIF decoder status in status_blocks
- add tests for every native status reason
```

### Phase 3: Worker API foundation

```text
- add worker registration/heartbeat/job polling endpoints
- add WorkerRegistryService and WorkerFileTransferService
- define worker registration/capability schemas
```

### Phase 4: External worker runtime

```text
- create worker/ project
- implement DSM API client
- implement local processor probe
- implement Variant B download/upload
- execute av-imgdata-face-processor locally
```

### Phase 5: Optional libvips integration

```text
- keep default image path unchanged
- add optional IMAGE_PROCESSOR_VIPS capability/status
- allow libvips to become preferred image preprocessing backend only when ready
```

## Final Decision

```text
DSM package = controller and file authority
C++ face processor = required production ProcessorCore for InsightFace-compatible face processing on this branch
Python bridge = removed / not production fallback
Local persistent worker mode = stdin/stdout optimization, not external DSM worker
External worker = separate runtime using DSM Worker API and compatible processor binaries
ProcessorContract = shared boundary for local and remote execution
Status model = must report native processor readiness, not pip package readiness
libvips = optional future image backend, not face inference replacement
Additional DSM platforms = optional and additive
External worker platforms = packaged separately from DSM Toolkit
```
