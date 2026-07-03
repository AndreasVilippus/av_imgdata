# Optional Worker Concept

## Purpose

This document describes the optional worker architecture for `av_imgdata` after introducing native C/C++ processor components.

The goal is to keep the DSM package as the controller, DSM authority, status owner, and final write owner while allowing expensive processing to run either:

```text
- locally on DSM through package-shipped native C/C++ processor binaries
- locally on DSM through existing backend/package-managed code
- remotely through an optional external worker
```

The worker remains optional. The DSM package must continue to work without a registered worker.

The introduction of C/C++ components does not mean that the whole DSM backend or the worker runtime is rewritten in C/C++. C/C++ is used only for bounded processor executables behind `ProcessorContract`.

## Current Branch Context

This concept applies to branch:

```text
C/C++-component-test
```

Relevant related concept documents:

```text
docs/insightface-native-processor-replacement.md
docs/insightface-native-libraries-and-build.md
```

Current build reality:

```text
- Toolkit exists on a Linux build machine.
- Repository is located under toolkit/source/av_imgdata.
- Package build starts from the Toolkit root.
- Canonical build command:

  source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake

- Current mandatory DSM platform is one selected Toolkit target.
- Additional DSM platforms are optional and additive.
```

## Current Implementation Status

The current C++ component can already serve as a **ProcessorCore** and as a **local long-running subprocess worker**.

It is not yet a complete **external DSM worker**.

### Already present

```text
processors/native/face_processor/
  CMakeLists.txt
  src/main.cpp

tools/build-native-face-processor.sh

src/services/native_face_processor_service.py
src/services/native_face_processor_worker.py

processor_contract/
  README.md
  schemas/face-native-job-input.schema.json
  schemas/face-native-result.schema.json
```

The native processor exposes this command surface:

```text
av-imgdata-face-processor version
av-imgdata-face-processor probe --model-root <path> --model-name <name>
av-imgdata-face-processor detect --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor embed --input <job-input.json> --output <processor-result.json> --workdir <dir>
av-imgdata-face-processor worker
av-imgdata-face-processor self-test --model-root <path> --model-name <name>
```

The `worker` subcommand is a local stdin/stdout request loop. It is intended to keep model state warm across multiple image requests.

It is not a network worker and does not talk to DSM by itself.

### Not present yet

```text
- external worker runtime project
- DSM Worker API implementation
- worker registration endpoint
- worker heartbeat endpoint
- job polling endpoint
- Variant B file download endpoint for workers
- result upload endpoint for workers
- external worker config format
- external worker packaging for Windows/Linux/macOS/Docker
- worker capability registration based on av-imgdata-face-processor probe/version
- remote JobInput translation from DSM asset references to local worker files
- worker-side ProcessorResult schema validation
```

## Architecture Summary

```text
DSM package
  = controller
  = DSM authority
  = job owner
  = status owner
  = final write owner

Web UI
  = browser client for display, configuration, progress, logs

Native C/C++ processors
  = bounded package-shipped processor executables
  = built by Synology Toolkit for the selected DSM platform
  = no compiler or toolchain required on NAS
  = no DSM authority logic

Local native subprocess worker
  = av-imgdata-face-processor worker
  = local stdin/stdout loop
  = optimizes repeated local processing by reusing loaded models
  = not a DSM external worker

Optional external worker
  = external execution host
  = uses DSM Worker API
  = downloads inputs through DSM API
  = executes processor binaries/modules locally
  = uploads results back to DSM
  = may use the same ProcessorContract
  = may use a platform-equivalent av-imgdata-face-processor binary

ProcessorContract
  = language-neutral anti-duplication boundary
```

The worker is not a second backend. It is only an execution target for jobs created and owned by DSM.

Native C/C++ processors are not workflow owners. They read contract input and write contract output.

## Execution Targets

The same logical job may support multiple execution targets.

```text
JobDispatcher
  -> LocalBackendProcessorAdapter
  -> LocalNativeProcessorAdapter
  -> RemoteWorkerProcessorAdapter
```

Target selection rules:

```text
1. DSM creates and owns the job.
2. DSM checks configured execution preference.
3. DSM checks local native processor availability.
4. DSM checks registered worker availability and capabilities.
5. DSM selects one execution target.
6. DSM validates ProcessorResult before committing any result.
```

Recommended first priority order:

```text
1. Local native C/C++ processor for supported platform and enabled capability
2. External worker if configured and capability-compatible
3. Existing local backend implementation as fallback where still available
```

The priority order must remain configurable because weak NAS systems may prefer remote workers, while stronger NAS systems may benefit from local native processors.

## Local Subprocess Worker Versus External Worker

These two concepts must stay separate.

### Local subprocess worker

```text
DSM Backend
  -> NativeFaceProcessorService
  -> av-imgdata-face-processor worker
  -> stdin/stdout JSON request loop
  -> local file paths
  -> local result JSON
```

Properties:

```text
- runs on the same machine as DSM backend
- receives local temp file paths
- does not register with DSM
- does not call DSM APIs
- does not download or upload files
- reuses loaded models between requests
- is an optimization of LocalNativeProcessorAdapter
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
- runs outside DSM, e.g. Windows, Linux, Docker, cloud host
- must authenticate to DSM
- must download inputs through DSM API
- must create local job-input.json with worker-local image_path
- must execute a processor locally
- must upload result back to DSM
- must not own final DSM writes
```

Rule:

```text
av-imgdata-face-processor is reusable by an external worker as ProcessorCore.
It is not itself the external worker runtime.
```

## Recommended Repository Structure

Use one monorepo while the processor contract, DSM backend, worker, and native processor are still evolving together.

```text
av_imgdata/
  src/
    api/
      worker_routes.py
      job_routes.py
      native_processor_routes.py
    services/
      job_service.py
      job_dispatcher.py
      worker_registry_service.py
      worker_auth_service.py
      worker_file_transfer_service.py
      processor_result_validator.py
      native_processor_status_service.py
      native_face_processor_service.py
    processors/
      local_processor_adapter.py
      local_native_processor_adapter.py
      remote_worker_processor_adapter.py
      processor_contract_loader.py

  worker/
    cmd/
      av-imgdata-worker/
    internal/
      api/
      capabilities/
      config/
      files/
      jobs/
      processors/
      service/
      telemetry/
    build/
      windows/
      linux/
      macos/
      docker/
    tests/
    README.md

  processor_contract/
    schemas/
      job.schema.json
      job-input.schema.json
      job-result.schema.json
      progress-event.schema.json
      processor-error.schema.json
      worker-capabilities.schema.json
      worker-registration.schema.json
      native-processor-status.schema.json
      face-native-job-input.schema.json
      face-native-result.schema.json
    examples/
    fixtures/
    openapi/
      worker-api.openapi.yaml
    README.md

  processors/
    native/
      face_processor/
        CMakeLists.txt
        src/
        include/
        tests/
        fixtures/
        third_party/
    python/
    README.md

  native_deps/
    sources/
    patches/
    licenses/

  package/
    INFO
    scripts/
    conf/
    ui/
    bin/
    lib/
    THIRD_PARTY_NOTICES/

  tests/
    unit/
    integration/
    contract/
    native/

  tools/
    build-package.sh
    build-native-face-processor.sh
    native/
      check-native-deps.sh
      build-native-deps.sh
      build-libjpeg-turbo.sh
      build-onnxruntime.sh
      validate-native-face-artifact.sh

  docs/
  SynoBuildConf/
```

## Runtime Scope On DSM

Allowed on DSM:

```text
- POSIX shell for DSM package lifecycle scripts
- existing backend runtime only if declared as official Synology dependency or packaged with the SPK
- browser JavaScript for Web UI
- package-shipped native C/C++ binaries for the selected Synology architecture
- package-local shared libraries required by those binaries
- explicit external tools when configurable, status-visible, and license-aware
```

Not assumed on DSM:

```text
- Go runtime
- Rust toolchain or Rust compiler
- C/C++ compiler or build toolchain
- modern Java runtime unless declared as official package dependency
- .NET runtime
- Ruby runtime
- user-managed Python venv
- user-installed Node.js runtime for backend execution
```

C/C++ components are acceptable for NAS packages when built during the Toolkit build and shipped as package artifacts.

## DSM Package Ownership

The DSM backend remains responsible for:

```text
- DSM integration
- API routes
- authentication/session handling
- configuration normalization
- job creation
- job dispatching
- local/remote/native target selection
- worker registration and token management
- native processor status probing
- status payload building
- runtime state and progress ordering
- finding/result persistence
- final DSM file writes
- final Synology Photos writes
- conflict detection and write locks
- local fallback execution
```

## Native C/C++ Processor Ownership

Native C/C++ processor binaries own only bounded processing.

Allowed responsibilities:

```text
- version reporting
- probe command
- self-test command
- image decode for explicitly supported formats
- image preprocessing
- ONNXRuntime C API session setup
- face detection model execution
- face embedding model execution
- structured ProcessorResult JSON output
- structured ProcessorError JSON output
- local stdin/stdout worker loop for model reuse
```

Forbidden responsibilities:

```text
- DSM authorization
- DSM API calls
- Synology Photos API calls
- worker registration
- heartbeat
- job polling
- DSM file download/upload
- person creation
- face assignment
- metadata writes
- findings persistence
- runtime status aggregation
- job persistence
- conflict handling
- worker token handling
- UI state decisions
```

## External Worker Ownership

The external worker owns:

```text
- DSM Worker API client
- registration request
- heartbeat loop
- job polling loop
- API file download
- result upload
- local temp workspace
- processor execution wrapper
- optional local processor binary lifecycle
- local worker logs
- service/daemon mode
- CLI commands
```

The worker may use a platform-equivalent `av-imgdata-face-processor` binary.

The worker must not own:

```text
- DSM authorization rules
- Synology Photos session bootstrap
- final write decisions
- authoritative status aggregation
- job persistence
- conflict handling before final commit
- worker token creation or revocation
```

## ProcessorContract

`processor_contract/` is the anti-duplication boundary.

It defines:

```text
- job schema
- job input schema
- job result schema
- progress event schema
- processor error schema
- native processor status schema
- worker registration schema
- worker capabilities schema
- worker API OpenAPI contract
- deterministic fixtures and expected result shapes
```

Required native face job types:

```text
face_native_detect
face_native_embed
face_native_probe
```

Current native face input schema supports:

```text
contract_version
job_id
type: face_native_detect | face_native_embed
input.image_path
input.source_id
options.model_root
options.model_name
options.min_confidence
options.max_faces
options.det_size
options.normalize_coordinates
```

Current native face result schema supports:

```text
contract_version
job_id
type
status: completed | failed
processor.name
processor.version
processor.backend
timing_ms
result.faces
bbox or normalized box
embedding as float array or float32-le-base64
error.code
error.message
error.retryable
error.phase
warnings
```

No Python, C++, worker, or DSM model may become the contract authority.

## ProcessorCore Strategy

`ProcessorCore` is an execution boundary, not one specific language.

Supported forms:

```text
- existing backend module behind LocalBackendProcessorAdapter
- package-shipped native C/C++ executable behind LocalNativeProcessorAdapter
- worker-side executable or module behind RemoteWorkerProcessorAdapter
```

Preferred executable boundary:

```text
av-imgdata-face-processor detect \
  --input job-input.json \
  --output processor-result.json \
  --workdir /tmp/av-imgdata-job-123
```

Preferred warm-process boundary:

```text
av-imgdata-face-processor worker

stdin line:
  {"request_id":"...","command":"embed","input":"job-input.json","output":"processor-result.json"}

stdout line:
  {"request_id":"...","returncode":0}
```

Both local and remote execution must produce the same `ProcessorResult` shape.

## Native Face Processor Build Policy

The native face processor is built by the existing Toolkit build path.

Canonical command from Toolkit root:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

Native build integration:

```text
1. tools/build-package.sh runs existing checks.
2. tools/build-package.sh runs Python tests.
3. tools/build-package.sh forwards options to pkgscripts-ng/PkgCreate.py.
4. SynoBuildConf/build calls tools/build-native-face-processor.sh.
5. C/C++ processor and package-local libraries are built for SYNO_PLATFORM.
6. SynoBuildConf/install copies binary and libraries into SPK.
7. result_spk/ receives the final SPK.
```

Build dependencies for ONNXRuntime backend:

```text
- ONNXRUNTIME_ROOT with include/onnxruntime_c_api.h and lib/libonnxruntime.so
- JPEG_ROOT with include/jpeglib.h and lib/libjpeg.so
- optional HEIF_ROOT with include/libheif/heif.h
```

Recommended build flags:

```text
AV_FACE_PROCESSOR_BACKEND=onnxruntime | python_bridge
AV_IMGDATA_NATIVE_STRIP=0|1
ONNXRUNTIME_ROOT=/path/to/onnxruntime
JPEG_ROOT=/path/to/jpeg-root
HEIF_ROOT=/path/to/heif-root
```

Production branch rule:

```text
The SPK must contain the ONNXRuntime-native variant, not the python_bridge variant.
```

## External Worker Build And Packaging Policy

DSM Toolkit builds DSM artifacts only. It does not solve external worker packaging.

External worker packaging must be separate from the SPK build.

Required output families:

```text
worker/build/windows/
  av-imgdata-worker.exe
  av-imgdata-face-processor.exe
  onnxruntime.dll
  jpeg/libjpeg runtime files
  config example
  models directory placeholder

worker/build/linux/
  av-imgdata-worker
  av-imgdata-face-processor
  libonnxruntime.so*
  libjpeg.so*
  config example
  models directory placeholder

worker/build/macos/
  av-imgdata-worker
  av-imgdata-face-processor
  dylibs if supported later

worker/build/docker/
  Dockerfile
  av-imgdata-worker
  av-imgdata-face-processor
  required shared libraries
```

External worker packages must include:

```text
- worker runtime binary
- av-imgdata-face-processor binary for that platform
- required native libraries
- third-party notices
- example config
- model directory placeholder
- service install/uninstall helper where applicable
```

The external worker must probe the processor at startup:

```text
av-imgdata-face-processor version
av-imgdata-face-processor probe --model-root <worker-model-root> --model-name <model-name>
```

Only after a successful probe may it report `face_native_detect` or `face_native_embed` to DSM.

## Platform Policy

The current wheelhouse is already platform-specific. The native processor follows the same policy.

Required first DSM platform:

```text
current Toolkit target, e.g. DSM 7.3 / geminilake
```

Optional later DSM platforms:

```text
other x86_64 platform families
arm64 platform families
older ARM platforms only if package support explicitly requires them
```

External worker platforms are separate from DSM platforms:

```text
Windows x86_64
Linux x86_64
Linux arm64
Docker linux/amd64
Docker linux/arm64
macOS later only if needed
```

Unsupported platform behavior:

```text
- DSM package still starts
- native face processor capability is reported as unavailable for platform
- external worker may still be used if configured
- Python wheelhouse path may remain optional during migration
```

## Worker API Required For External Use

External workers require DSM-side API endpoints.

Minimum endpoints:

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

Endpoint ownership:

```text
worker_routes.py
  - request validation only
  - auth/token check
  - call services
  - return DTOs

worker_registry_service.py
  - worker identity
  - capabilities
  - last_seen
  - version/protocol validation

worker_file_transfer_service.py
  - safe file lookup
  - streaming download
  - temporary upload staging
  - hash validation
  - size validation

job_dispatcher.py
  - compatible job selection
  - assignment state
  - timeout/cancel handling

processor_result_validator.py
  - validate result schema
  - reject unsupported fields if required
  - normalize worker/native errors
```

## Variant B File Transfer For External Workers

The optional worker uses Variant B: DSM provides files through its own API.

External workers must not require SMB, NFS, WebDAV, or direct access to DSM shares in version 1.

Remote execution flow:

```text
1. UI starts an operation.
2. DSM creates a job.
3. DSM selects remote_worker target.
4. Worker polls next compatible job.
5. DSM returns a job with asset references, not raw NAS paths.
6. Worker downloads input through DSM API.
7. Worker writes input file into local temp workspace.
8. Worker creates job-input.json with worker-local image_path.
9. Worker runs av-imgdata-face-processor detect/embed or worker mode.
10. Worker validates processor-result.json.
11. Worker uploads result to DSM.
12. DSM validates ProcessorResult again.
13. DSM commits or records result through DSM-owned logic.
14. DSM updates runtime/job status.
15. UI displays status.
```

Worker-facing job payload should not expose direct DSM paths as required execution input.

Recommended DSM job payload for workers:

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

Worker-local ProcessorInput:

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

Required file API behavior:

```text
- streaming download
- streaming upload
- file size validation
- content hash validation when provided
- temporary staging before final commit
- abandoned temp cleanup
- resumable upload only if measurements show need
```

Required memory rule:

```text
Never load full job input or output files into memory in DSM or in the worker unless the file type is explicitly small and bounded.
```

## Worker Runtime Model

Use a pull model as the default.

```text
Worker -> DSM: register
Worker -> DSM: heartbeat
Worker -> DSM: request next job
DSM    -> Worker: job or no job
Worker -> DSM: status/progress/logs
Worker -> DSM: result upload
```

The pull model is preferred because workers can run behind NAT, on Windows desktops, on laptops, in Docker, or in cloud environments without inbound DSM connections.

## Worker Capability Model

Capabilities must distinguish local native processors from external workers.

Example local native capability status:

```json
{
  "capability": "face_native_embed",
  "target": "local_native",
  "available": true,
  "platform": "geminilake",
  "binary": "bin/av-imgdata-face-processor",
  "processor_version": "av-imgdata-face-processor 0.5.0-onnxruntime-native-heif",
  "backend": "native",
  "model_status": "ready"
}
```

Example worker registration payload:

```json
{
  "contract_version": "1.0",
  "worker_id": "worker-01",
  "name": "Windows GPU Worker",
  "platform": "windows",
  "arch": "amd64",
  "version": "0.1.0",
  "max_parallel_jobs": 2,
  "capabilities": [
    "face_native_detect",
    "face_native_embed"
  ],
  "processors": [
    {
      "name": "av-imgdata-face-processor",
      "version": "av-imgdata-face-processor 0.5.0-onnxruntime-native-heif",
      "backend": "native",
      "commands": ["detect", "embed", "worker", "probe", "version"],
      "model_name": "buffalo_l",
      "model_status": "ready"
    }
  ],
  "features": {
    "api_file_transfer": true,
    "share_file_transfer": false,
    "native_face_processor": true,
    "warm_processor_worker": true
  }
}
```

DSM should assign jobs only to compatible targets.

## External Worker Runtime Responsibilities

A minimal external worker must implement:

```text
worker configure
worker register
worker start
worker status
worker test-connection
worker install-service
worker uninstall-service
```

Runtime loop:

```text
1. read config
2. validate DSM URL and token
3. probe local av-imgdata-face-processor
4. register capabilities
5. heartbeat periodically
6. poll next compatible job
7. download input asset
8. create local ProcessorInput
9. execute processor
10. validate ProcessorResult
11. upload result
12. cleanup temp workspace
13. report structured status/logs
```

Processor execution options:

```text
Option A: one subprocess per job
  av-imgdata-face-processor embed --input ... --output ... --workdir ...

Option B: warm processor process
  av-imgdata-face-processor worker
  stdin/stdout JSON requests
```

Recommendation:

```text
Use Option B for face_native_detect and face_native_embed when multiple jobs use the same model.
Use Option A for simple diagnostics, isolated failures, or first implementation.
```

## Remote Worker Configuration Example

```yaml
server:
  url: "https://dsm.local:5001"
  token: "REPLACE_WITH_WORKER_TOKEN"

worker:
  id: "worker-01"
  name: "worker-01"
  max_parallel_jobs: 2
  temp_dir: "/var/tmp/av-imgdata-worker"

processor:
  path: "/opt/av-imgdata-worker/bin/av-imgdata-face-processor"
  mode: "warm_worker"
  timeout_seconds: 120

models:
  root: "/opt/av-imgdata-worker/models"
  face_model: "buffalo_l"

files:
  mode: "api"
  verify_sha256: true

capabilities:
  - "face_native_detect"
  - "face_native_embed"

logging:
  level: "info"
  file: "worker.log"
```

## DSM-Compatible Component Matrix

| Component | Allowed DSM runtime | Notes |
|---|---|---|
| DSM package lifecycle | `/bin/sh` | Package start/stop/status scripts remain shell scripts. |
| DSM API routes | Existing backend runtime, official dependency, or packaged runtime | Keep routes thin. |
| Job dispatcher | Existing backend runtime, official dependency, or packaged runtime | Selects backend/native/worker target. |
| Worker registration API | Existing backend runtime | DSM owns worker identity and token validation. |
| Variant B file streaming endpoints | Existing backend runtime with streaming I/O | Must not load full files into memory. |
| Status payload builder | Existing backend runtime | DSM remains UI status source of truth. |
| Runtime state and job persistence | Existing backend runtime / SQLite-backed services | Worker and native binary do not persist authoritative state. |
| Local backend ProcessorCore | Existing backend modules | Fallback and migration bridge. |
| Local native ProcessorCore | C/C++ binary shipped in SPK | Best for bounded NAS-local hot paths. |
| Local native subprocess worker | C/C++ binary `worker` subcommand | Local model reuse optimization. |
| Remote worker runtime | External binary/service | Owns DSM API client and remote processing loop. |
| Remote worker ProcessorCore | Worker-owned binary/module | Uses same ProcessorContract. |
| Image/face processor | C/C++ native binary | Primary C++ component. |
| Web UI | Browser JavaScript | No NAS backend runtime dependency. |
| Contract tests | Existing test stack outside runtime package | Validate schemas and equivalence. |

## Target Selection Strategy

Configuration example:

```json
{
  "processing": {
    "FACE_DETECTION_TARGET": "auto",
    "FACE_EMBEDDING_TARGET": "auto",
    "ALLOW_REMOTE_WORKER": true,
    "ALLOW_LOCAL_NATIVE": true,
    "ALLOW_LOCAL_BACKEND_FALLBACK": true
  }
}
```

Target modes:

```text
auto
local_native
remote_worker
local_backend
```

Initial `auto` order:

```text
1. local_native if ready and platform-supported
2. remote_worker if registered and compatible
3. local_backend if supported
```

For weak NAS systems a user may prefer:

```text
1. remote_worker
2. local_native
3. local_backend
```

## Shared Local And Worker Execution Components

Required by all execution targets:

```text
- job input schema
- job option schema
- job result schema
- processor error schema
- progress event schema
- supported job type names
- capability names
- processor version / protocol version
- file hash and integrity rules
- metadata normalization rules for processor outputs
- validation rules for processor results before commit
- deterministic test fixtures for each supported job type
```

DSM-owned only:

```text
- DSM authentication and user/session handling
- Synology Photos session bootstrap
- final permission decisions
- final writes to DSM-managed files or Photos objects
- authoritative runtime state
- job persistence
- worker token generation and revocation
- UI-visible status aggregation
- conflict detection before committing writes
```

## Duplication Avoidance Strategy

The central rule is:

```text
Local backend, local native, and remote worker execution must use the same ProcessorContract.
```

Target execution model:

```text
UI/API request
  -> DSM creates Job
  -> JobDispatcher selects execution target
     -> LocalBackendProcessorAdapter
        -> existing backend implementation
        -> ProcessorResult
     -> LocalNativeProcessorAdapter
        -> package/bin/av-imgdata-face-processor
        -> ProcessorResult
     -> RemoteWorkerProcessorAdapter
        -> DSM Worker API
        -> external worker
        -> worker-local av-imgdata-face-processor
        -> ProcessorResult
  -> DSM validates result
  -> DSM commits result or records findings
  -> DSM status builder exposes final state
```

Forbidden duplication pattern:

```text
DSM backend implements business logic A
Worker independently implements business logic A differently
Native binary returns unvalidated result shape B
```

Allowed variation:

```text
Different implementations may produce the same ProcessorResult shape,
provided fixture equivalence tests define tolerance and semantics.
```

## Contract Tests

Required tests:

```text
- local backend and local native output match schema
- local native and worker-style output match schema
- external worker job payload converts to native ProcessorInput correctly
- worker result validates against face-native-result.schema.json before upload
- DSM validates worker result again before final commit
- same error condition produces same structured error category
- progress events are accepted but UI status is built by DSM
- worker/native result cannot bypass DSM validation
- unsupported output fields fail validation
- local fallback returns equivalent result shape when native or worker is unavailable
```

Native face fixture set:

```text
- no face image
- one face frontal image
- multiple face image
- rotated image if supported
- low confidence face image
- large image requiring resize
- unsupported/corrupt file
- image with EXIF orientation if supported by native path
```

Remote worker fixture set:

```text
- asset download succeeds
- asset download hash mismatch
- model probe fails
- processor returns failed ProcessorResult
- worker loses heartbeat during job
- result upload fails
- DSM rejects invalid ProcessorResult
```

Numeric tolerance examples:

```text
box coordinate tolerance: <= 0.01 normalized units
landmark tolerance: <= 0.01 normalized units
embedding cosine similarity: >= 0.995 against reference output
```

## Security Requirements

The worker and native processor must not execute arbitrary commands supplied by jobs.

Required controls:

```text
- explicit allowed job types
- protocol version check
- capability whitelist
- input asset/reference validation on DSM side
- output validation before final commit
- processor subprocess timeout
- bounded temp workdir
- no shell eval
- no arbitrary command job type
- minimal filesystem permissions
- structured error responses without leaking secrets
- worker token authentication
- token rotation support
- TLS/HTTPS support
```

Allowed job types:

```text
file_analysis
metadata_scan
preview_generation
hash_file
face_native_detect
face_native_embed
```

Forbidden generic job types:

```text
shell_exec
run_command
eval
remote_script
```

## Client-Side Components

Browser client candidates:

```text
- table rendering
- sorting of already-loaded data
- filtering of already-loaded data
- simple form validation
- progress display
- log display
- worker registration/configuration forms
- native processor status display
- remote worker status display
- result preview for small bounded payloads
```

The browser client must not own:

```text
- DSM file authorization
- secret handling
- final write decisions
- long-running processing
- mutation workflow ownership
- worker token generation
- processor target selection authority
```

## Implementation Phases

### Phase 1: Contract and target model

Tasks:

```text
- add target selection model: local_backend, local_native, remote_worker
- add ProcessorContract schemas for native face detection/embedding
- add native processor status schema
- add worker registration/capability schemas
- add fixture definitions and expected result shapes
```

Acceptance criteria:

```text
- DSM can represent target capability without executing it
- schemas validate examples
- no workflow depends on one implementation language
```

### Phase 2: Local native processor integration

Tasks:

```text
- keep av-imgdata-face-processor as bounded ProcessorCore
- use detect/embed CLI boundary
- use worker subcommand for local model reuse
- validate ProcessorResult in DSM
- expose local native status in UI
```

Acceptance criteria:

```text
- current local behavior still works without external worker
- local native target can run a bounded job
- DSM remains final authority for findings/writes/status
```

### Phase 3: DSM Worker API

Tasks:

```text
- implement worker registration
- implement heartbeat
- implement job polling
- implement worker status/log endpoint
- implement Variant B input download
- implement result upload
- add token validation
- add worker capability persistence
```

Acceptance criteria:

```text
- external worker can register
- external worker can heartbeat
- external worker can receive no-job response
- DSM rejects unauthorized worker requests
```

### Phase 4: External worker runtime skeleton

Tasks:

```text
- create worker/ project
- implement config loader
- implement DSM API client
- implement processor probe
- implement capability registration
- implement heartbeat loop
- implement job polling loop
- implement temp workspace management
```

Acceptance criteria:

```text
- worker starts outside DSM
- worker registers capabilities based on av-imgdata-face-processor probe/version
- worker remains alive and heartbeats
```

### Phase 5: External worker file and processor execution

Tasks:

```text
- download input asset through DSM API
- write local ProcessorInput
- run av-imgdata-face-processor detect/embed
- support warm worker mode
- validate ProcessorResult locally
- upload result to DSM
- cleanup temp workspace
```

Acceptance criteria:

```text
- remote face_native_detect runs end-to-end
- remote face_native_embed runs end-to-end
- DSM validates result before commit
- failed worker jobs show actionable errors
```

### Phase 6: External worker packaging

Tasks:

```text
- create Windows package layout
- create Linux package layout
- create Docker package layout
- include av-imgdata-face-processor and libraries
- include third-party notices
- include example config and service helpers
```

Acceptance criteria:

```text
- worker package runs on at least one non-DSM Linux host
- worker can probe processor and register with DSM
- packaging does not depend on DSM Toolkit
```

### Phase 7: Performance hardening

Tasks:

```text
- measure local backend vs local native vs remote worker time
- measure model-load savings from warm worker mode
- measure DSM API transfer throughput
- measure native processor CPU/RAM use on NAS
- add chunked/resumable upload only if large files require it
- add optional platform builds only after current platform is stable
```

Acceptance criteria:

```text
- performance claims are backed by measurements
- no broad retry/fallback behavior is added without observed failure modes
- DSM memory usage remains bounded during file streaming
```

## Initial Scope

Version 1 should include:

```text
- monorepo structure with worker/, processor_contract/, processors/native/
- DSM package limited to official/package-managed runtimes and shipped native binaries
- local native C++ processor for current Toolkit platform
- local native subprocess worker mode for repeated local jobs
- ProcessorContract schemas for native face processor input/result
- target model: local_backend, local_native, remote_worker
- structured job status
- local-vs-native contract tests
- native-vs-worker-shape contract tests
- local fallback in DSM
```

External worker Version 1 should include:

```text
- worker runtime skeleton
- registration
- heartbeat
- job polling
- Variant B file download
- local ProcessorInput generation
- av-imgdata-face-processor execution
- ProcessorResult validation
- result upload
- Linux package first
```

Version 1 should not include:

```text
- mandatory additional DSM platforms
- SMB/NFS/WebDAV file access
- direct worker inbound API
- Redis/RabbitMQ/NATS queue
- Kubernetes orchestration
- arbitrary shell commands
- dynamic remote scripts
- mandatory Python venv
- manual NAS-side compiler/toolchain installation
- full OpenCV unless required by fixtures
- independent duplicate reimplementation of DSM workflow logic
```

## Performance Expectation

Expected benefits:

```text
- DSM package remains responsive during heavy operations
- local C++ processor can reduce NAS-local Python/OpenCV/InsightFace overhead
- local worker subcommand can reuse loaded models
- startup no longer needs runtime pip install for native-supported platform after migration
- remote worker remains available for weak NAS systems or GPU/stronger hosts
- same ProcessorContract keeps local and remote behavior comparable
```

Expected limits:

```text
- local NAS CPU remains limited compared with desktop/cloud workers
- ONNXRuntime and model inference may still be expensive on NAS
- remote processing still pays DSM API transfer cost
- platform-specific native binaries require build and runtime validation
- external worker packaging is separate from DSM Toolkit packaging
```

Measure these before claiming speedups:

```text
local backend processing time
vs.
local native one-shot processor time
vs.
local native warm-worker processor time
vs.
DSM API transfer time + remote worker processing time + result upload time
```

## Final Decision

Adopt this direction:

```text
DSM package = controller and file authority
DSM runtimes = shell, official/package-managed backend runtime, browser JS, shipped native binaries
C++ components = bounded package-shipped ProcessorCore executables built by Toolkit
Native face processor = first local C++ processor candidate
Local native worker mode = stdin/stdout optimization, not external DSM worker
External worker = separate runtime that uses DSM Worker API and may execute av-imgdata-face-processor
Worker runtime language = external-platform decision, not NAS runtime requirement
File transfer = Variant B through DSM API only
ProcessorContract = anti-duplication boundary
Local backend, local native, and remote worker execution = same job/result/progress schema
No manual NAS-side compiler/toolchain/runtime setup
Additional DSM platforms = optional and additive
External worker platforms = packaged separately from DSM Toolkit
```
