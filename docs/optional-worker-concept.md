# Optional Worker Concept

## Purpose

This document describes an optional external worker concept for `av_imgdata` while keeping the DSM package restricted to runtimes that are either part of DSM, available through official Synology packages, or shipped explicitly as package-owned native components.

The worker is optional. The DSM package must continue to work without a registered worker by using the local processing path through the same processor contract.

## Runtime Scope

### Allowed on DSM

The DSM package may rely on these runtime categories:

```text
- POSIX shell for DSM package lifecycle scripts
- existing backend runtime only if declared as an official Synology package dependency or packaged with the SPK
- browser JavaScript for the Web UI
- native C/C++ components shipped as package binaries for the target Synology architecture
- other native Linux executables shipped with the package for the target Synology architecture
- external tools only when explicit, configurable, status-visible, and license-aware
```

C/C++ components are acceptable for NAS packages when they are shipped as compiled package artifacts. The package must not require a C/C++ compiler or development toolchain to be present on the NAS.

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

These technologies may still be used outside the NAS to build worker binaries, processor binaries, or packaged native artifacts. They must not become manual NAS prerequisites.

## Architecture Summary

```text
DSM package = controller, DSM authority, job owner, status owner
Web UI      = browser client for display, configuration, progress, logs
Worker      = optional external execution host
ProcessorContract = language-neutral contract between DSM, worker, and processors
ProcessorCore     = reusable processing implementation or executable behind that contract
```

The worker is not a second backend. It is only an execution target for jobs created and owned by DSM.

## Recommended Git Structure

Use one monorepo. Do not split the worker into a separate repository at the beginning. The worker, contract, tests, package, and existing backend must evolve together while the contract is still being stabilized.

```text
av_imgdata/
  src/                         # existing DSM backend
    api/
    services/
    models/
    parser/
    handler/
    processors/

  ui/                          # existing browser UI
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
    examples/
    fixtures/
    openapi/
      worker-api.openapi.yaml
    README.md

  processors/                   # reusable ProcessorCore implementations or executables
    python/                     # only with official dependency or packaged executable
    native/                     # shipped C/C++ or other native binaries per Synology architecture
    README.md

  package/                      # DSM packaging
    INFO
    scripts/
    conf/
    ui/
    bin/                        # packaged native binaries, including C/C++ processors

  tests/
    unit/
    integration/
    contract/

  tools/
  docs/
  .github/workflows/
```

## DSM Package Ownership

The existing backend remains responsible for:

```text
- DSM integration
- API routes
- authentication/session handling
- configuration normalization
- job creation
- job dispatching
- worker registration and token management
- status payload building
- runtime state and progress ordering
- finding/result persistence
- final DSM file writes
- final Synology Photos writes
- conflict detection and write locks
- local fallback execution
```

New backend modules should stay focused:

```text
src/services/job_service.py
src/services/job_dispatcher.py
src/services/worker_registry_service.py
src/services/worker_auth_service.py
src/services/worker_file_transfer_service.py
src/services/processor_result_validator.py
src/api/worker_routes.py
src/api/job_routes.py
src/models/job.py
src/models/worker.py
src/models/processor_result.py
src/processors/local_processor_adapter.py
src/processors/processor_contract_loader.py
```

## Worker Ownership

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
- optional external processing modules
- local worker logs
- service/daemon mode
- CLI commands
```

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

`processor_contract/` is language-neutral. It defines the shared schema and examples for all execution targets.

The contract is the source of truth for:

```text
- job schema
- job input schema
- job result schema
- progress event schema
- processor error schema
- worker registration schema
- worker capabilities schema
- worker API OpenAPI contract
- deterministic fixtures and expected results
```

No implementation-specific model may become the contract authority.

## ProcessorCore

`processors/` contains reusable processing implementations or executables.

DSM-safe approaches:

```text
- Python ProcessorCore only when Python is an official Synology package dependency or packaged as a controlled executable
- C/C++ ProcessorCore components shipped as compiled package binaries for each supported Synology architecture
- other native ProcessorCore executables shipped for the target Synology architecture
- external tool integration only when explicit, configurable, status-visible, and license-aware
```

Recommended executable boundary:

```text
av-imgdata-processor run \
  --input job-input.json \
  --output job-result.json \
  --workdir /tmp/av-imgdata-job-123
```

Both local and remote execution should produce the same `ProcessorResult` shape.

## Required DSM Refactoring

### 1. Introduce a job model

Long-running actions must be represented as jobs instead of direct synchronous processing from routes or UI actions.

Required job fields:

```json
{
  "contract_version": "1.0",
  "job_id": "string",
  "type": "string",
  "operation": "string",
  "mode": "string",
  "priority": "normal",
  "status": "queued",
  "input": {},
  "options": {},
  "created_at": "iso-8601",
  "updated_at": "iso-8601"
}
```

Recommended status values:

```text
queued
assigned
running
uploading
completed
failed
cancelled
timeout
```

### 2. Add a processor boundary

Existing workflow code should not decide directly whether work is local or remote.

```text
JobDispatcher
  - create_job
  - select_processor
  - assign_job
  - update_status

Processor implementations
  - LocalProcessorAdapter
  - RemoteWorkerProcessorAdapter
```

The initial implementation can route all jobs to `LocalProcessorAdapter`. Remote execution can then be added without changing UI-facing routes again.

### 3. Keep API routes thin

Routes should validate requests, create jobs, return status, and expose results. They should not own workflow logic.

### 4. Add worker registration and heartbeat

Minimum endpoints:

```text
POST /api/worker/register
POST /api/worker/heartbeat
GET  /api/worker/jobs/next
POST /api/worker/jobs/{job_id}/status
POST /api/worker/jobs/{job_id}/result
POST /api/worker/jobs/{job_id}/log
```

Variant B file endpoints:

```text
GET /api/worker/jobs/{job_id}/input/{asset_id}
PUT /api/worker/jobs/{job_id}/output/{asset_id}
```

### 5. Add capability-based assignment

Example capability payload:

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
    "hashing"
  ],
  "features": {
    "api_file_transfer": true,
    "share_file_transfer": false
  }
}
```

DSM should assign jobs only to compatible workers.

## File Transfer Decision: Variant B Only

The worker concept uses Variant B: DSM provides files through its own API.

The worker does not require SMB, NFS, WebDAV, or direct access to DSM shares in version 1.

```text
1. UI starts an operation.
2. DSM creates a job.
3. Worker pulls the next compatible job.
4. Worker downloads input through the DSM API.
5. DSM streams the file to the worker.
6. Worker processes the file in its local temp directory.
7. Worker uploads the result through the DSM API.
8. DSM validates and stages the result.
9. DSM commits or records the result through DSM-owned logic.
10. DSM updates persisted job/runtime status.
11. UI displays progress and completion state.
```

Required file API behavior:

```text
- streaming download
- streaming upload
- file size validation
- content hash validation
- temporary staging before final commit
- abandoned temp cleanup
- resumable upload later only if measurements show need
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

The pull model is preferred because the worker can run behind NAT, on Windows desktops, on laptops, in Docker, or in cloud environments without requiring DSM to initiate inbound connections.

## DSM-Compatible Component Matrix

| Component | Allowed DSM runtime | Notes |
|---|---|---|
| DSM package lifecycle | `/bin/sh` | Package start/stop/status scripts remain shell scripts. |
| DSM API routes | Existing backend runtime, official dependency, or packaged runtime | Keep routes thin. |
| Job dispatcher | Existing backend runtime, official dependency, or packaged runtime | Must remain close to runtime state and persistence. |
| Worker registration API | Existing backend runtime | DSM side owns worker identity and token validation. |
| Variant B file streaming endpoints | Existing backend runtime with streaming I/O | Must not load full files into memory. |
| Status payload builder | Existing backend runtime | DSM remains source of truth for UI status. |
| Runtime state and job persistence | Existing backend runtime / SQLite-backed services | Worker must not persist authoritative state. |
| Local ProcessorCore | Python with official dependency, packaged executable, or C/C++ native binary | Must conform to ProcessorContract. |
| Hashing hot path | C/C++ native binary or existing backend runtime | C/C++ is acceptable when shipped as package binary. |
| Binary parsing hot path | C/C++ native binary or packaged executable | Requires strict fixtures and validation. |
| Image processing primitive | C/C++ native binary or external tool | Keep as narrow processor module. |
| ExifTool integration | Existing backend adapter or packaged external tool | Must stay explicit and status-visible. |
| Web UI | Browser JavaScript | No NAS backend runtime dependency. |
| Contract tests | Existing test stack outside runtime package | Tests validate schemas and executable behavior. |

## NAS-Language Decision Rules

Do not choose one language for the whole system. Choose by runtime category.

```text
- Use shell only for DSM lifecycle scripts.
- Use the existing backend runtime only if it is packaged or declared as an official Synology dependency.
- Use browser JavaScript only for UI-side work.
- Use C/C++ for NAS-local performance components when shipped as compiled package binaries.
- Use native executables for isolated processor modules instead of requiring toolchains on DSM.
- Do not require Go, Rust, C/C++ compiler toolchains, .NET, Ruby, or user-managed venvs on DSM.
```

C/C++ remains valid for NAS package components, especially for:

```text
- hashing large files
- binary parsing
- image processing primitives
- compression/decompression
- native library bindings
- bounded ProcessorCore executables
```

C/C++ should not take over DSM authority components:

```text
- DSM authentication/session logic
- Synology Photos session bootstrap
- worker token creation/revocation
- final permission decisions
- final DSM/Photos writes
- authoritative runtime state
- status payload aggregation
- conflict detection and write locks
- UI-visible workflow state decisions
```

## External Worker Language Position

The external worker language is intentionally not a DSM runtime decision.

The worker may be implemented in any language that can produce a supported executable or package for the intended external platform. The DSM package only communicates with it through the worker API and ProcessorContract.

The DSM concept therefore does not require a Go/Rust/C#/Java/.NET/etc. runtime on the NAS for the worker.

## Shared Local And Worker Execution Components

Required by both local and worker execution:

```text
- job input schema
- job option schema
- job result schema
- error schema
- progress event schema
- supported job type names
- capability names
- processor version / protocol version
- file hash and integrity rules
- metadata normalization rules for processor outputs
- validation rules for processor results before commit
- deterministic test fixtures for each supported job type
```

These pieces should live in `processor_contract/`.

Usually shared as implementation, not only schema:

```text
- pure file analysis that does not require DSM APIs
- metadata parsing that operates on local files or streamed inputs
- sidecar parsing logic once the input file set is staged locally
- hash generation
- preview generation if the same output is required locally and remotely
- result normalization from external tools such as ExifTool
```

Must remain DSM-owned:

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

Worker-owned only:

```text
- worker registration client
- DSM worker API client
- heartbeat loop
- job polling loop
- local temp workspace management
- worker service installation
- local worker log file handling
```

## Duplication Avoidance Strategy

The central rule is: local and remote execution must use the same processor contract, and where practical the same processor implementation or executable.

Target execution model:

```text
UI/API request
  -> DSM creates Job
  -> JobDispatcher selects execution target
     -> LocalProcessorAdapter
        -> ProcessorContract
        -> ProcessorCore or processor executable
     -> RemoteWorkerProcessorAdapter
        -> DSM Worker API
        -> external worker
        -> ProcessorContract
        -> ProcessorCore or processor executable
  -> DSM validates result
  -> DSM commits result or records findings
  -> DSM status builder exposes final state
```

Preferred contract:

```text
ProcessorInput JSON + input file reference(s)
  -> ProcessorCore
  -> ProcessorResult JSON + output artifact reference(s)
```

Both local and worker execution must produce the same `ProcessorResult` shape.

## Processor Implementation Options

| Option | Description | DSM compatibility | Recommendation |
|---|---|---|---|
| Existing backend modules | Keep current implementation behind LocalProcessorAdapter | Compatible if backend runtime is packaged/official | Good first step. |
| Python processor library | Extract current logic into reusable modules | Compatible only with official/package-managed runtime | Useful if current code is Python-heavy. |
| Processor executable | CLI executable with JSON input/output | Compatible if shipped for target architecture | Best long-term anti-duplication boundary. |
| C/C++ processor module | Native processor for measured hot path | Compatible when shipped as package binary | Good for NAS performance components. |
| Separate local and remote implementations | Local and worker each implement same job independently | Compatible but high divergence risk | Avoid. |

Recommended path:

```text
1. Extract a local processor boundary in the current backend.
2. Define JSON schemas and fixtures for job input/result/progress.
3. Move pure processing into a ProcessorCore boundary.
4. Let LocalProcessorAdapter call ProcessorCore locally.
5. Let RemoteWorkerProcessorAdapter send the same job contract to the worker.
6. Use package-managed backend modules or shipped native/C/C++ executables for DSM-local processing.
```

## Current Package Areas Relevant For Local And Worker Execution

| Current area | Needed locally | Needed by worker | Ownership decision |
|---|---:|---:|---|
| Long-running operation identity (`operation`, `mode`, `action`, `operation_id`, `revision`) | Yes | Reports into it | DSM owns schema and ordering; worker only emits progress events. |
| Status payload building | Yes | No direct ownership | DSM remains source of truth. Worker sends raw progress/result; DSM builds UI status. |
| File analysis / findings storage | Yes | Worker may generate findings | DSM owns persistence. Worker may produce finding candidates in result JSON. |
| Metadata parsing | Yes | Yes, for remote analysis jobs | Extract behind ProcessorCore or shared executable to avoid two parser implementations. |
| ExifTool-backed access | Yes | Possibly | Keep command/result normalization shared; DSM or worker may execute depending on selected target. |
| Checks workflow | Yes | Possibly for scan phase | DSM owns workflow and final write decisions. Worker can execute scan/analyze substeps only. |
| FaceMatch workflow | Yes | Possibly for CPU-heavy match/analysis | DSM owns Photos identity/write flow. Worker can execute bounded compute phases only. |
| Cleanup workflow | Yes | Possibly for scan phase | DSM owns deletion/write authority. Worker can generate candidates only. |
| Write locks/conflict handling | Yes | No | DSM-only. Worker must not commit final writes. |
| Config normalization | Yes | Worker reads limited subset | DSM owns full config. Worker receives normalized, minimal job options. |
| UI rendering and reconnect behavior | Yes | No | Browser/DSM only. Worker is not a UI state owner. |

## Contract Tests To Prevent Duplication Drift

Required tests:

```text
- same input fixture produces same ProcessorResult schema locally and through worker simulation
- same error condition produces same structured error category
- progress events are accepted but UI status is still built by DSM
- worker result cannot bypass DSM validation
- worker cannot return unsupported output fields without validation failure
- local fallback returns equivalent result shape when worker is unavailable
```

Acceptance criteria:

```text
- no UI route needs to know whether the job ran locally or remotely
- no workflow contains separate local and remote business branches beyond adapter selection
- no processor logic is copied into both DSM backend and worker without a contract test proving equivalence
- no remote job type is enabled until contract fixtures exist for it
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
```

A desktop client can be added later as a setup wrapper only. It should not contain processing logic.

The worker may include CLI commands:

```text
worker configure
worker register
worker start
worker status
worker test-connection
worker install-service
worker uninstall-service
```

## Security Requirements

The worker must not execute arbitrary commands supplied by DSM jobs.

Required controls:

```text
- worker token authentication
- TLS/HTTPS support
- token rotation support
- worker IDs
- capability whitelist
- explicit allowed job types
- protocol version check
- input path/reference validation on DSM side
- output validation before final commit
- no shell eval
- no arbitrary command job type
- minimal filesystem permissions for worker temp directory
- structured error responses without leaking secrets
```

Allowed job types must be explicit:

```text
file_analysis
metadata_scan
preview_generation
hash_file
```

Forbidden generic job types:

```text
shell_exec
run_command
eval
remote_script
```

## Configuration Example

Windows worker example:

```yaml
server:
  url: "https://dsm.local:5001"
  token: "REPLACE_WITH_WORKER_TOKEN"

worker:
  name: "windows-worker-01"
  max_parallel_jobs: 2
  temp_dir: "C:\\DSMWorker\\temp"

files:
  mode: "api"

capabilities:
  - "file_analysis"
  - "metadata_scan"
  - "preview_generation"
  - "hash_file"

logging:
  level: "info"
  file: "worker.log"
```

Linux worker example:

```yaml
server:
  url: "https://dsm.local:5001"
  token: "REPLACE_WITH_WORKER_TOKEN"

worker:
  name: "linux-worker-01"
  max_parallel_jobs: 4
  temp_dir: "/var/tmp/av-imgdata-worker"

files:
  mode: "api"

capabilities:
  - "file_analysis"
  - "metadata_scan"
  - "preview_generation"
  - "hash_file"
```

## Implementation Phases

### Phase 1: Runtime and repository constraints

Status: Open.

Tasks:

```text
- document official DSM runtime dependencies
- decide which backend runtime is an explicit package dependency
- decide which C/C++ or native processor binaries are shipped with the package
- add processor_contract/
- add initial JSON schemas
- add contract validation tool
```

Acceptance criteria:

```text
- package does not require manual runtime/toolchain installation on DSM
- C/C++ components are shipped as compiled artifacts, not built on the NAS
- schemas validate examples
```

### Phase 2: Local job abstraction

Status: Open.

Tasks:

```text
- identify long-running processing paths
- define job persistence
- add status values
- add LocalProcessorAdapter
- route existing local processing through the processor boundary
```

Acceptance criteria:

```text
- current local behavior still works without external worker
- UI-facing behavior does not regress
- job status can be queried independently of processing implementation
```

### Phase 3: Shared ProcessorCore and anti-duplication tests

Status: Open.

Tasks:

```text
- define ProcessorInput schema
- define ProcessorResult schema
- define ProcessorError schema
- define ProgressEvent schema
- add fixtures for first supported job types
- add local-vs-worker-simulation equivalence tests
- decide whether first ProcessorCore stays in package-managed backend modules or becomes a processor executable
```

Acceptance criteria:

```text
- local execution and worker-style execution return the same result shape
- worker output cannot bypass DSM validation
- no duplicated processing branch is introduced without a contract test
```

### Phase 4: Worker runtime skeleton

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
```

Acceptance criteria:

```text
- worker runs on at least Windows and Linux
- worker can register and heartbeat
- worker can pull a test job
- worker can download/upload through Variant B API transfer
- worker does not require a NAS-side runtime beyond DSM package endpoints
```

### Phase 5: First real remote job

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
- local and worker execution produce equivalent ProcessorResult
- failed worker jobs show actionable errors
- DSM remains the authority for final result handling
```

### Phase 6: UI integration

Status: Open.

Tasks:

```text
- show registered workers
- show heartbeat/last-seen state
- show worker capabilities
- show job assignment target
- show worker logs or recent worker errors
- add worker token creation/revocation UI if appropriate
```

Acceptance criteria:

```text
- user can see whether remote worker acceleration is active
- user can distinguish local processing from worker processing
- failed worker jobs show actionable errors
```

### Phase 7: Performance hardening

Status: Deferred until measured.

Tasks:

```text
- measure DSM API transfer throughput
- measure CPU time moved away from DSM
- add chunked/resumable upload only if large files require it
- evaluate C/C++ native processor components only for measured hot paths
- evaluate multiple parallel workers only after single-worker behavior is stable
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
- monorepo structure with worker/ and processor_contract/
- DSM package limited to official/package-managed runtimes and shipped native binaries
- C/C++ allowed for shipped NAS processor components
- pull model
- Variant B API file transfer only
- token authentication
- registration and heartbeat
- one or two concrete job types
- structured job status
- shared ProcessorContract schemas
- local-vs-worker contract tests
- Windows and Linux worker builds
- local fallback in DSM
```

Version 1 should not include:

```text
- SMB/NFS/WebDAV file access
- direct worker inbound API
- Redis/RabbitMQ/NATS queue
- Kubernetes orchestration
- arbitrary shell commands
- dynamic remote scripts
- mandatory Python venv
- manual NAS-side compiler/toolchain installation
- independent duplicate reimplementation of existing parser/workflow logic
```

## Performance Expectation

Expected benefits:

```text
- DSM package remains responsive during heavy operations
- CPU and RAM-heavy work can run on stronger Windows/Linux/cloud systems
- NAS-local C/C++ processor binaries can improve bounded local hot paths
- worker can use more parallelism than the DSM package should use locally
- UI remains browser-side and avoids adding rendering load to DSM
```

Expected limits:

```text
- file transfer still uses DSM network and API I/O
- large files may be bottlenecked by upload/download time
- performance gains depend on how much processing time exceeds transfer time
```

The first measurable target should be end-to-end job time:

```text
local DSM processing time
vs.
DSM API transfer time + external worker processing time + result upload time
```

Remote processing is worthwhile when the external processing gain is larger than the transfer overhead.

## Final Decision

Adopt this direction:

```text
DSM package = controller and file authority
DSM runtimes = shell, official/package-managed backend runtime, browser JS, shipped native binaries
C/C++ = valid for shipped NAS processor components and measured local hot paths
Web UI = browser client for display and configuration
Worker = optional external execution host, not a second backend
Worker runtime language = external-platform decision, not NAS runtime requirement
File transfer = Variant B through DSM API only
ProcessorContract = anti-duplication boundary
Local and remote execution = same job/result/progress schema
ProcessorCore = shared implementation or executable where practical
No manual NAS-side compiler/toolchain/runtime setup
```
