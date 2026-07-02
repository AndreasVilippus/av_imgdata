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

These documents define the native replacement direction for the optional `InsightFace` / `OpenCV` / `ONNXRuntime` Python wheelhouse block.

The current build reality is:

```text
- Toolkit exists on a Linux build machine.
- Repository is located under toolkit/source/av_imgdata.
- Package build starts from the Toolkit root.
- Canonical build command:

  source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake

- Current mandatory DSM platform is one selected Toolkit target.
- Additional DSM platforms are optional and additive.
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
  = package-shipped local processor executables
  = built by Synology Toolkit for the selected DSM platform
  = no compiler or toolchain required on NAS

Optional external worker
  = external execution host
  = uses DSM Worker API
  = may use the same ProcessorContract
  = may use the same or platform-equivalent processor binaries

ProcessorContract
  = language-neutral anti-duplication boundary
```

The worker is not a second backend. It is only an execution target for jobs created and owned by DSM.

Native C/C++ processors are not workflow owners. They are bounded execution modules that read contract input and write contract output.

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
4. DSM checks worker availability and capabilities.
5. DSM selects one execution target.
6. DSM validates ProcessorResult before committing any result.
```

Recommended first priority order:

```text
1. Local native C/C++ processor for supported platform and enabled capability
2. External worker if configured and capability-compatible
3. Existing local backend implementation as fallback where still available
```

The final priority order must remain configurable because small NAS systems may prefer remote workers, while stronger NAS systems may benefit from local native processors.

## Runtime Scope On DSM

### Allowed on DSM

The DSM package may rely on:

```text
- POSIX shell for DSM package lifecycle scripts
- existing backend runtime only if declared as official Synology dependency or packaged with the SPK
- browser JavaScript for Web UI
- package-shipped native C/C++ binaries for the selected Synology architecture
- package-local shared libraries required by those binaries
- explicit external tools when configurable, status-visible, and license-aware
```

C/C++ components are acceptable for NAS packages when built during the Toolkit build and shipped as package artifacts.

The package must not require a C/C++ compiler or development toolchain on the NAS.

### Not assumed on DSM

The DSM package must not assume these are installed on the NAS:

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

These technologies may still be used outside DSM to build artifacts, but they must not become manual NAS prerequisites.

## Recommended Repository Structure

Use one monorepo while the processor contract, DSM backend, worker, and native processor are still evolving together.

```text
av_imgdata/
  src/                         # existing DSM backend
    api/
    services/
    models/
    parser/
    handler/
    processors/
      local_processor_adapter.py
      local_native_processor_adapter.py
      remote_worker_processor_adapter.py
      processor_contract_loader.py

  ui/                          # browser UI
    src/

  worker/                      # optional external worker subproject
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

  processor_contract/           # language-neutral contract
    schemas/
      job.schema.json
      job-input.schema.json
      job-result.schema.json
      progress-event.schema.json
      processor-error.schema.json
      worker-capabilities.schema.json
      worker-registration.schema.json
      native-processor-status.schema.json
      face-native-detect-input.schema.json
      face-native-detect-result.schema.json
      face-native-embed-input.schema.json
      face-native-embed-result.schema.json
    examples/
    fixtures/
    openapi/
      worker-api.openapi.yaml
    README.md

  processors/                   # reusable processor implementations / executables
    native/
      face_processor/
        CMakeLists.txt
        src/
        include/
        tests/
        fixtures/
        third_party/
    python/                     # only with official/package-managed runtime
    README.md

  native_deps/                  # pinned native dependency sources/cache
    sources/
    patches/
    licenses/

  package/                      # DSM package assets
    INFO
    scripts/
    conf/
    ui/
    bin/                        # built native binaries copied into SPK
    lib/                        # package-local shared libraries copied into SPK
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
  .github/workflows/
```

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

Recommended modules:

```text
src/services/job_service.py
src/services/job_dispatcher.py
src/services/worker_registry_service.py
src/services/worker_auth_service.py
src/services/worker_file_transfer_service.py
src/services/processor_result_validator.py
src/services/native_processor_status_service.py
src/services/native_face_processor_service.py

src/api/worker_routes.py
src/api/job_routes.py
src/api/native_processor_routes.py

src/models/job.py
src/models/worker.py
src/models/processor_result.py
src/models/native_processor_status.py

src/processors/local_processor_adapter.py
src/processors/local_native_processor_adapter.py
src/processors/remote_worker_processor_adapter.py
src/processors/processor_contract_loader.py
```

## Native C/C++ Processor Ownership

Native C/C++ processor binaries own only bounded processing.

Example first binary:

```text
package/bin/av-imgdata-face-processor
```

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
```

Forbidden responsibilities:

```text
- DSM authorization
- Synology Photos API calls
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
- DSM worker API client
- registration request
- heartbeat loop
- job polling loop
- API file download
- API result upload
- local temp workspace
- process execution wrapper
- optional local processor binaries or modules
- worker-local logs
- service/daemon mode
- CLI commands
```

The worker may use the same `ProcessorContract` and may execute a platform-equivalent `av-imgdata-face-processor` binary.

The worker must not own:

```text
- DSM authorization
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

No Python, C++, worker, or DSM model may become the contract authority.

Required native face job types:

```text
face_native_detect
face_native_embed
face_native_probe
```

Required general processor result fields:

```json
{
  "contract_version": "1.0",
  "job_id": "string",
  "type": "string",
  "status": "completed|failed",
  "processor": {
    "name": "string",
    "version": "string",
    "backend": "string"
  },
  "result": {},
  "warnings": [],
  "error": null
}
```

## ProcessorCore Strategy

`ProcessorCore` is now an execution boundary, not one specific language.

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

Both local and remote execution must produce the same `ProcessorResult` shape.

## Native Face Processor Build Policy

The native face processor is built by the existing Toolkit build path.

Canonical command from Toolkit root:

```bash
source/av_imgdata/tools/build-package.sh -v 7.3 -p geminilake
```

The build wrapper should remain the only normal package build entrypoint.

Native build integration:

```text
1. tools/build-package.sh runs existing checks.
2. tools/build-package.sh runs Python tests.
3. If native face build is enabled, dependency cache and licenses are validated.
4. tools/build-package.sh forwards options to pkgscripts-ng/PkgCreate.py.
5. SynoBuildConf/build calls native build scripts inside the selected Toolkit platform environment.
6. C/C++ processor and package-local libraries are built for SYNO_PLATFORM.
7. SynoBuildConf/install copies binary, libraries, and third-party notices into the SPK.
8. result_spk/ receives the final SPK.
```

Recommended build flags:

```text
AV_IMGDATA_NATIVE_FACE=0|1
AV_IMGDATA_NATIVE_FACE_ONNX=0|1
AV_IMGDATA_NATIVE_FACE_OPENCV=0|1
AV_IMGDATA_NATIVE_FACE_DEPS=reuse|build
```

Initial defaults:

```text
AV_IMGDATA_NATIVE_FACE=0
AV_IMGDATA_NATIVE_FACE_ONNX=0
AV_IMGDATA_NATIVE_FACE_OPENCV=0
```

After skeleton proof:

```text
AV_IMGDATA_NATIVE_FACE=1
AV_IMGDATA_NATIVE_FACE_ONNX=0
AV_IMGDATA_NATIVE_FACE_OPENCV=0
```

After inference proof:

```text
AV_IMGDATA_NATIVE_FACE=1
AV_IMGDATA_NATIVE_FACE_ONNX=1
AV_IMGDATA_NATIVE_FACE_OPENCV=0
```

Full OpenCV should remain off unless fixture parity proves it is required.

## Native Dependency Policy

Preferred first native stack:

```text
- C++17
- nlohmann/json or equivalent small JSON parser
- libjpeg-turbo
- ONNXRuntime C API for real model execution
```

Optional later:

```text
- libpng + zlib
- minimal OpenCV C++ modules
```

Avoid initially:

```text
- full OpenCV
- HEIF/HEIC codec stack
- Exiv2
- custom ONNX inference implementation
```

License policy:

```text
- keep native stack permissive where possible
- include THIRD_PARTY_NOTICES/native-face-processor.md
- record static and dynamic linkage
- treat models separately from code dependencies
- do not include GPL/LGPL/patent-sensitive codec stacks without separate review
```

## Platform Policy

The current wheelhouse is already platform-specific. The native processor follows the same policy.

Required first platform:

```text
current Toolkit target, e.g. DSM 7.3 / geminilake
```

Optional later platforms:

```text
other x86_64 platform families
arm64 platform families
older ARM platforms only if package support explicitly requires them
```

Unsupported platform behavior:

```text
- package still starts
- native face processor capability is reported as unavailable for platform
- external worker may still be used if configured
- Python wheelhouse path may remain optional during migration
```

## File Transfer Decision: Variant B Only

The optional worker uses Variant B: DSM provides files through its own API.

The worker does not require SMB, NFS, WebDAV, or direct access to DSM shares in version 1.

```text
1. UI starts an operation.
2. DSM creates a job.
3. DSM selects local backend, local native, or remote worker target.
4. If remote worker is selected, worker pulls the compatible job.
5. Worker downloads input through DSM API.
6. Worker processes the file locally.
7. Worker uploads result through DSM API.
8. DSM validates ProcessorResult.
9. DSM commits or records result through DSM-owned logic.
10. DSM updates runtime/job status.
11. UI displays status.
```

Variant B endpoints:

```text
GET /api/worker/jobs/{job_id}/input/{asset_id}
PUT /api/worker/jobs/{job_id}/output/{asset_id}
```

Required file API behavior:

```text
- streaming download
- streaming upload
- file size validation
- content hash validation
- temporary staging before final commit
- abandoned temp cleanup
- resumable upload only if measurements show need
```

Required rule:

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

## Capability Model

Capabilities must distinguish local native processors from external workers.

Example native capability status:

```json
{
  "capability": "face_native_detect",
  "target": "local_native",
  "available": true,
  "platform": "geminilake",
  "binary": "bin/av-imgdata-face-processor",
  "processor_version": "0.1.0",
  "backend": "onnxruntime-capi",
  "model_status": "ready"
}
```

Example worker capability payload:

```json
{
  "contract_version": "1.0",
  "worker_id": "win-gpu-01",
  "name": "Windows GPU Worker",
  "platform": "windows",
  "arch": "amd64",
  "version": "0.1.0",
  "max_parallel_jobs": 2,
  "capabilities": [
    "file_analysis",
    "metadata_scan",
    "preview_generation",
    "hash_file",
    "face_native_detect",
    "face_native_embed"
  ],
  "features": {
    "api_file_transfer": true,
    "share_file_transfer": false,
    "native_face_processor": true
  }
}
```

DSM should assign jobs only to compatible targets.

## DSM-Compatible Component Matrix

| Component | Allowed DSM runtime | Notes |
|---|---|---|
| DSM package lifecycle | `/bin/sh` | Package start/stop/status scripts remain shell scripts. |
| DSM API routes | Existing backend runtime, official dependency, or packaged runtime | Keep routes thin. |
| Job dispatcher | Existing backend runtime, official dependency, or packaged runtime | Selects backend/native/worker target. |
| Worker registration API | Existing backend runtime | DSM owns worker identity and token validation. |
| Native processor status | Existing backend runtime invoking package binary | Version/probe/self-test only. |
| Variant B file streaming endpoints | Existing backend runtime with streaming I/O | Must not load full files into memory. |
| Status payload builder | Existing backend runtime | DSM remains UI status source of truth. |
| Runtime state and job persistence | Existing backend runtime / SQLite-backed services | Worker and native binary do not persist authoritative state. |
| Local backend ProcessorCore | Existing backend modules | Good fallback and migration bridge. |
| Local native ProcessorCore | C/C++ binary shipped in SPK | Best for bounded NAS-local hot paths. |
| Remote worker ProcessorCore | Worker-owned binary/module | Uses same ProcessorContract. |
| Hashing hot path | C/C++ native binary or existing backend runtime | Native candidate after measurement. |
| Image/face processor | C/C++ native binary | Primary C++ component. |
| ExifTool integration | Existing backend adapter or packaged external tool | Explicit and status-visible. |
| Web UI | Browser JavaScript | No NAS backend runtime dependency. |
| Contract tests | Existing test stack outside runtime package | Validate schemas and equivalence. |

## Target Selection Strategy

Target selection should be explicit and debuggable.

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

`auto` selection order should be configurable later. Initial order:

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

Implementation may differ, but output contract must not.

Usually shared as fixtures and contract first:

```text
- face detection input/result
- face embedding input/result
- metadata parsing result shape
- hash generation result shape
- preview generation result shape
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
        -> worker processor
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
- Python InsightFace path and native C++ face processor match fixture expectations within tolerance
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

Numeric tolerance examples:

```text
box coordinate tolerance: <= 0.01 normalized units
landmark tolerance: <= 0.01 normalized units
embedding cosine similarity: >= 0.995 against reference output
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

## Security Requirements

The worker and native processor must not execute arbitrary commands supplied by jobs.

Required controls:

```text
- explicit allowed job types
- protocol version check
- capability whitelist
- input path/reference validation on DSM side
- output validation before final commit
- processor subprocess timeout
- bounded temp workdir
- no shell eval
- no arbitrary command job type
- minimal filesystem permissions
- structured error responses without leaking secrets
```

Allowed job types must be explicit:

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

## Configuration Example

DSM local native processor config:

```json
{
  "native_processors": {
    "FACE_PROCESSOR": {
      "ENABLED": false,
      "PATH": "bin/av-imgdata-face-processor",
      "MODEL_ROOT": "",
      "MODEL_NAME": "",
      "TIMEOUT_SECONDS": 120,
      "MAX_IMAGE_BYTES": 67108864
    }
  }
}
```

Worker example:

```yaml
server:
  url: "https://dsm.local:5001"
  token: "REPLACE_WITH_WORKER_TOKEN"

worker:
  name: "worker-01"
  max_parallel_jobs: 2
  temp_dir: "/var/tmp/av-imgdata-worker"

files:
  mode: "api"

capabilities:
  - "file_analysis"
  - "metadata_scan"
  - "preview_generation"
  - "hash_file"
  - "face_native_detect"
  - "face_native_embed"
```

## Implementation Phases

### Phase 1: Contract and target model

Status: Open.

Tasks:

```text
- add target selection model: local_backend, local_native, remote_worker
- add ProcessorContract schemas for native face detection/embedding
- add native processor status schema
- add fixture definitions and expected result shapes
```

Acceptance criteria:

```text
- DSM can represent target capability without executing it
- schemas validate examples
- no workflow depends on one implementation language
```

### Phase 2: Local job abstraction

Status: Open.

Tasks:

```text
- identify long-running processing paths
- define job persistence
- add status values
- add LocalBackendProcessorAdapter
- add LocalNativeProcessorAdapter skeleton
- route existing local processing through processor boundary
```

Acceptance criteria:

```text
- current local behavior still works without native processor or worker
- UI-facing behavior does not regress
- job status can be queried independently of processing implementation
```

### Phase 3: Native C++ processor skeleton

Status: Open.

Tasks:

```text
- add processors/native/face_processor skeleton
- implement version/probe/self-test
- integrate with tools/build-package.sh / SynoBuildConf
- package binary into SPK for current platform
- add THIRD_PARTY_NOTICES
```

Acceptance criteria:

```text
- SPK contains bin/av-imgdata-face-processor for supported platform
- binary runs on target DSM
- version command works
- self-test works without model
- no NAS-side compiler/toolchain is required
```

### Phase 4: Native image and inference implementation

Status: Open.

Tasks:

```text
- add JPEG decode/preprocess first
- add ONNXRuntime C API integration
- add detector model execution
- add embedding model execution if required
- add structured errors
```

Acceptance criteria:

```text
- native output validates against ProcessorContract
- corrupt input produces structured error
- model missing does not block package startup
- no full OpenCV dependency unless explicitly justified by fixtures
```

### Phase 5: Local native integration

Status: Open.

Tasks:

```text
- add NativeFaceProcessorService
- add native processor status endpoint
- add UI status display
- add target selection for face jobs
- validate ProcessorResult before DSM commit
```

Acceptance criteria:

```text
- user can see native processor readiness
- local native target can run a bounded job
- DSM remains final authority for findings/writes/status
```

### Phase 6: Worker runtime skeleton

Status: Open.

Tasks:

```text
- create worker subproject
- implement configuration loading
- implement registration
- implement heartbeat
- implement job polling
- implement API file download/upload
- implement structured logging
- add ability to execute contract-compatible processor binaries/modules
```

Acceptance criteria:

```text
- worker registers and heartbeats
- worker can pull a test job
- worker can download/upload through Variant B
- worker reports capabilities including native-equivalent face capabilities when available
```

### Phase 7: First real remote job

Status: Open.

Tasks:

```text
- implement one bounded job type
- run it locally and remotely through the same ProcessorContract
- validate result before DSM commit
- show job target in status/debug information
```

Acceptance criteria:

```text
- local native and worker execution produce equivalent ProcessorResult
- failed worker jobs show actionable errors
- DSM remains authority for final result handling
```

### Phase 8: Performance hardening

Status: Deferred until measured.

Tasks:

```text
- measure local backend vs local native vs remote worker time
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
- local native C++ processor skeleton for current Toolkit platform
- ProcessorContract schemas for native face processor status and results
- pull-model worker concept
- Variant B API file transfer only
- target model: local_backend, local_native, remote_worker
- structured job status
- local-vs-native and native-vs-worker contract tests
- local fallback in DSM
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
- startup no longer needs runtime pip install for native-supported platform after migration
- remote worker remains available for weak NAS systems or GPU/stronger hosts
- same ProcessorContract keeps local and remote behavior comparable
```

Expected limits:

```text
- local NAS CPU remains limited compared with desktop/cloud workers
- ONNXRuntime and model inference may still be expensive on NAS
- remote processing still pays DSM API transfer cost
- platform-specific native binaries require Toolkit build and runtime validation
```

Measure these before claiming speedups:

```text
local backend processing time
vs.
local native processor time
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
Worker = optional external execution host, not a second backend
Worker runtime language = external-platform decision, not NAS runtime requirement
File transfer = Variant B through DSM API only
ProcessorContract = anti-duplication boundary
Local backend, local native, and remote worker execution = same job/result/progress schema
No manual NAS-side compiler/toolchain/runtime setup
Additional DSM platforms = optional and additive
```
