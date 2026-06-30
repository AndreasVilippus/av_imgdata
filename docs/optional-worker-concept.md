# Optional Worker Concept

## Purpose

This document describes an optional external worker subproject for `av_imgdata`.

The primary goal is to improve performance and keep the DSM package responsive by moving long-running or CPU/RAM-heavy processing out of the DSM package when a suitable external system is available.

The worker is optional. The DSM package must continue to work without a registered worker by using the existing local processing path through the same processor contract.

## Architecture Summary

```text
DSM package = controller, DSM authority, job owner, status owner
Web UI      = browser client for display, configuration, progress, logs
Worker      = optional external execution host
ProcessorContract = language-neutral contract between DSM, worker, and processors
ProcessorCore     = reusable processing implementation behind that contract
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
        main.go | main.rs | main.cpp
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
      file-analysis.input.json
      file-analysis.result.json
      metadata-scan.input.json
      metadata-scan.result.json
    fixtures/
      images/
      sidecars/
      expected-results/
    openapi/
      worker-api.openapi.yaml
    README.md

  processors/                   # reusable ProcessorCore implementations
    python/
      av_imgdata_processor/
        cli.py
        contract.py
        dispatcher.py
        file_analysis.py
        metadata_scan.py
        preview_generation.py
        result_normalizer.py
        errors.py
      tests/
      pyproject.toml
      README.md
    rust/                       # optional later for measured hot paths
    cpp/                        # optional later for measured/native hot paths
    README.md

  package/                      # DSM packaging
    INFO
    scripts/
    conf/
    ui/

  tests/
    unit/
    integration/
    contract/
      test_processor_contract_local.py
      test_worker_api_contract.py
      test_local_vs_worker_result_equivalence.py
      test_processor_result_validation.py

  tools/
    validate_processor_contract.py
    generate_worker_contracts.py
    check_syntax_and_structure.py

  docs/
    architecture-and-development-guidelines.md
    optimization-modernization.md
    optional-worker-concept.md

  .github/
    workflows/
      backend-tests.yml
      ui-tests.yml
      worker-tests.yml
      processor-tests.yml
      contract-tests.yml
      package-build.yml
```

## Repository Ownership Rules

### `src/` remains DSM backend

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

### `worker/` is an external execution host

The worker owns:

```text
- DSM worker API client
- registration request
- heartbeat loop
- job polling loop
- API file download
- API result upload
- local temp workspace
- process execution wrapper
- optional native processing modules
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

### `processor_contract/` is the anti-duplication boundary

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

Python, Go, Rust, C, or C++ implementations must conform to the contract. No implementation-specific model should become the contract authority.

### `processors/` contains reusable processing implementations

`processors/` contains code that can be called by local DSM execution and by the worker.

Recommended first approach:

```text
- extract existing Python-heavy domain processing into processors/python/
- expose a processor CLI with JSON input/output
- let DSM LocalProcessorAdapter call it locally where practical
- let the worker call the same processor executable where practical
```

Target executable contract:

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
    "gpu": false,
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

## Component And Language Matrix

This matrix is for language selection. It does not force the entire worker into one language.

| Component | Owner | Go | Rust | C/C++ | Python | Notes |
|---|---|---:|---:|---:|---:|---|
| DSM package lifecycle | DSM package | No | No | No | Existing | DSM-native scripts and current backend patterns should stay. |
| DSM API routes | DSM backend | No | No | No | Yes/current | Keep thin and close to existing backend. |
| Job dispatcher | DSM backend | No | No | No | Yes/current | Needs runtime state and persistence integration. |
| Worker registration API | DSM backend + worker | Good | Good | Possible | DSM side current | JSON/HTTP contract allows different languages per side. |
| Worker heartbeat loop | Worker | Good | Good | Possible | Possible | C/C++ adds more lifecycle and error-handling code. |
| Worker job polling | Worker | Good | Good | Possible | Possible | HTTP, retry, backoff, cancellation, structured errors required. |
| Worker API file transfer | Worker | Good | Good | Risky | Possible | C/C++ must handle streaming, TLS, timeouts, partial files, cleanup safely. |
| Worker config loading | Worker | Good | Good | Possible | Possible | YAML/JSON parsing and validation are easier in Go/Rust/Python. |
| Worker service/daemon mode | Worker | Good | Good | Possible | Possible | Windows service plus systemd support is more maintenance in C/C++. |
| Worker CLI | Worker | Good | Good | Possible | Good | C/C++ is possible but less productive for config/help/diagnostics. |
| Local temp workspace | Worker | Good | Good | Possible | Possible | C/C++ needs careful cleanup and path handling. |
| JSON Schema validation | Worker + tests | Good | Good | Possible | Good | C/C++ libraries exist but add dependency/build complexity. |
| Processor contract | Shared | N/A | N/A | N/A | N/A | JSON Schema/OpenAPI is language-neutral. |
| Existing metadata parsing | ProcessorCore | Avoid rewrite | Avoid rewrite first | Avoid rewrite first | Best first | Reuse existing behavior before native rewrites. |
| Hashing hot path | Processor module | Good | Good | Good | Okay | C/C++ is suitable here if measured. |
| Binary parsing hot path | Processor module | Good | Good | Good | Depends | C/C++ is suitable only with strong fixtures and fuzz/error tests. |
| Image processing primitive | Processor module | Good | Good | Good | Good with libraries | C/C++ suitable if using stable library bindings and narrow scope. |
| Face/AI processing | Optional processor | Wrapper | Wrapper | Wrapper only | Often best | AI stacks often depend on Python/native wheels. Keep optional/license-aware. |
| Result validation before commit | DSM backend | No | No | No | Yes/current | DSM-only authority. |
| Final DSM/Photos writes | DSM backend | No | No | No | Yes/current | Must not move to worker. |
| Web UI | Browser | No | No | No | JS/Vue | Existing UI remains browser-side. |
| Contract tests | Tests | Useful | Useful | Limited | Good | Test stack should validate all implementations against shared fixtures. |

## Worker Language Decision

The worker language is not finalized by this concept. The decision should be made after separating worker responsibilities into two categories:

```text
1. Worker runtime/orchestration
   - API client
   - polling
   - heartbeat
   - config
   - logging
   - service mode
   - file transfer
   - invoking ProcessorCore

2. Processor modules
   - hashing
   - parsing
   - metadata extraction
   - preview generation
   - image or AI-heavy processing
```

The runtime/orchestration layer has different requirements than processor modules. C/C++ may be excellent for narrow processor modules, but it is not automatically the best choice for the worker runtime.

## Which Worker Components Exclude Or Strongly Discourage C/C++

Strictly speaking, few components make C/C++ impossible. The issue is not capability; it is maintenance cost, security risk, dependency complexity, and error handling.

### Components that strongly discourage C/C++ as first choice

| Component | Why C/C++ is a poor first choice |
|---|---|
| Worker API client | Requires robust HTTPS/TLS, JSON, auth headers, retry/backoff, timeouts, proxy handling, and structured errors. Go/Rust provide this with less custom code. |
| Variant B file streaming | Needs safe streaming download/upload, partial file cleanup, hash verification, temp staging, cancellation, timeout handling, and memory bounds. C/C++ can do it, but mistakes are more costly. |
| Heartbeat and job polling loop | Mostly I/O orchestration, not CPU-bound. C/C++ adds complexity without meaningful performance gain. |
| Service/daemon mode | Windows service, systemd, signal handling, graceful shutdown, and restart behavior are simpler to maintain in Go/Rust. |
| Configuration loading and validation | YAML/JSON config parsing, defaults, migrations, and user-friendly errors are more cumbersome in C/C++. |
| Structured logging and diagnostics | Cross-platform logs, log rotation, debug output, and support diagnostics are easier in Go/Rust/Python. |
| Contract/schema validation | JSON Schema validation and helpful validation errors are more productive in Python/Go/Rust. C/C++ adds library and build burden. |
| Cross-platform packaging | Windows/Linux/macOS builds are possible in C/C++, but runtime library, TLS, compiler, and dependency differences increase support load. |
| Worker update/installation UX | Installer/service integration plus user diagnostics are not performance-critical. C/C++ gives little benefit. |
| Error reporting back to DSM | Structured, stable error categories matter more than raw speed. Safer higher-level languages reduce accidental divergence. |

### Components where C/C++ is acceptable or useful

| Component | C/C++ suitability | Condition |
|---|---:|---|
| Hashing large files | Good | Only if Go/Rust/Python-native library is not fast enough. |
| Binary parsing | Good | Must have fixtures, bounds checks, fuzz/error tests, and strict output contract. |
| Image/video primitive | Good | Prefer narrow module around a stable library; do not make it the whole worker. |
| Compression/decompression | Good | Use well-maintained libraries; keep wrapper small. |
| Existing native library binding | Good | Use when an existing C/C++ library is the correct dependency. |
| GPU/native acceleration wrapper | Conditional | Keep orchestration outside C/C++; expose a narrow processor contract. |

### Components that should not be in C/C++ for this project

These are not good C/C++ targets because they are authority, policy, or product-behavior components, not CPU-bound processing:

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

Those should remain DSM-backend owned.

## Language Options For The Worker Runtime

### Option A: Go worker runtime

Good fit when the worker is primarily an orchestrator.

```text
Strengths:
- single binaries
- strong HTTP/TLS/JSON support
- simple concurrency
- good Windows/Linux/macOS builds
- good CLI/service mode support
- lower operational overhead than Python venv

Weaknesses:
- less ideal than Rust/C for very tight CPU loops
- reimplementing existing Python domain logic in Go would risk divergence
```

Use Go if the worker mostly downloads files, runs ProcessorCore, uploads results, and reports status.

### Option B: Rust worker runtime

Good fit when memory safety, native binaries, and future native processing are important.

```text
Strengths:
- native speed
- strong memory safety
- good HTTP/JSON ecosystem
- good cross-platform builds
- better fit than C/C++ for safe orchestration

Weaknesses:
- higher learning/build complexity than Go
- fewer contributors may be comfortable with it
```

Use Rust if the worker runtime and processor modules are expected to converge into a native implementation over time.

### Option C: C/C++ worker runtime

Possible, but not recommended as the default runtime.

```text
Strengths:
- maximum control
- excellent for native library integration
- good for narrow hot paths

Weaknesses:
- high maintenance cost for HTTP/TLS/config/service/error handling
- higher risk of memory and lifetime errors
- more complex cross-platform dependency packaging
- little performance benefit for I/O-heavy orchestration
```

Use C/C++ only if there is a strong external constraint, such as an existing mature C/C++ codebase that already implements most worker runtime functions safely.

### Option D: Python worker runtime

Useful for prototypes or Python-heavy processing, but not ideal as an end-user default.

```text
Strengths:
- fastest to prototype
- can reuse existing code directly
- strong library ecosystem

Weaknesses:
- venv and Python version support burden
- weaker end-user packaging story
- less attractive for Windows service deployment
```

Use Python for ProcessorCore first if current logic is Python-heavy. Avoid requiring users to manage a venv for the worker runtime.

## Recommended Worker Language Position

Do not decide only between Go and C/C++. Decide by layer:

```text
Worker runtime/orchestration:
  Preferred: Go or Rust
  Not preferred: C/C++

ProcessorCore first extraction:
  Preferred: existing Python implementation behind JSON contract
  Later: packaged executable if cross-language reuse is needed

Measured hot paths:
  Preferred: Rust or C/C++ module behind ProcessorContract
```

Current recommendation:

```text
- Keep the worker runtime language open between Go and Rust.
- Do not choose C/C++ for the full worker runtime unless there is a concrete existing C/C++ foundation.
- Allow C/C++ for narrow processor modules where measurement proves value.
- Use the ProcessorContract so the runtime language can be changed later without changing DSM workflows.
```

## Shared Local And Worker Execution Components

Some parts are needed by both local DSM execution and external worker execution. These must be identified before implementation to avoid duplicate logic.

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

The central rule is: local and remote execution must use the same processor contract, and where practical the same processor implementation.

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

The dispatcher decides where a job runs. The job implementation should not know whether it was started locally or remotely.

Preferred contract:

```text
ProcessorInput JSON + input file reference(s)
  -> ProcessorCore
  -> ProcessorResult JSON + output artifact reference(s)
```

Both local and worker execution must produce the same `ProcessorResult` shape.

## Processor Implementation Options

| Option | Description | Duplication risk | Operational risk | Recommendation |
|---|---|---:|---:|---|
| Shared Python processor library | Extract current processing logic into importable Python modules used by local DSM path and optionally by packaged worker processor | Low | Medium | Good first extraction if current behavior is Python-heavy. |
| Processor executable | Package processing as a CLI executable with JSON input/output; DSM local adapter and worker both invoke it | Very low | Medium | Best long-term cross-language anti-duplication boundary. |
| Go/Rust worker reimplements Python logic | Recreate processing logic natively | High | Medium | Avoid until tests and profiling prove it is worth it. |
| C/C++ processor module | Native module for a measured hot path | Low to medium | Medium | Good only behind the ProcessorContract. |
| Separate local and remote implementations | Local Python logic and remote native logic independently implement same job | Very high | High | Do not use except as a temporary migration step behind contract tests. |

Recommended path:

```text
1. Extract a local processor boundary in the current backend.
2. Define JSON schemas and fixtures for job input/result/progress.
3. Move pure processing into a ProcessorCore boundary.
4. Let LocalProcessorAdapter call ProcessorCore locally.
5. Let RemoteWorkerProcessorAdapter send the same job contract to the worker.
6. Let the worker call a packaged ProcessorCore executable or a contract-tested native module.
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

Before moving real work to the worker, add tests that compare local and remote-style execution through the same contract.

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

The worker should include CLI commands from the first version:

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

Windows example:

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

Linux example:

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

### Phase 1: Repository structure and contract

Status: Open.

Tasks:

```text
- add processor_contract/
- add initial JSON schemas
- add OpenAPI worker API draft
- add examples and fixtures
- add contract validation tool
```

Acceptance criteria:

```text
- schemas validate examples
- version field is present
- contract tests can run without optional worker implementation
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
- decide whether first ProcessorCore stays Python or becomes a processor executable
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
- decide between Go and Rust for runtime/orchestration
- do not choose C/C++ for the full runtime unless a concrete constraint requires it
- implement configuration loading
- implement registration
- implement heartbeat
- implement job polling
- implement API file download/upload
- implement structured logging
```

Acceptance criteria:

```text
- worker runs on Windows and Linux
- worker can register and heartbeat
- worker can pull a test job
- worker can download/upload through Variant B API transfer
- worker does not require a user-managed Python venv
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
- evaluate Rust/C/C++ modules only for measured hot paths
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
- independent duplicate reimplementation of existing parser/workflow logic
- full C/C++ worker runtime without a concrete external requirement
```

## Performance Expectation

Expected benefits:

```text
- DSM package remains responsive during heavy operations
- CPU and RAM-heavy work can run on stronger Windows/Linux/cloud systems
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
Web UI = browser client for display and configuration
Worker = optional external execution host, not a second backend
Worker runtime language = open between Go and Rust until implementation decision
C/C++ = allowed for narrow measured processor modules, not preferred for full worker runtime
File transfer = Variant B through DSM API only
ProcessorContract = anti-duplication boundary
Local and remote execution = same job/result/progress schema
ProcessorCore = shared implementation where practical, executable boundary if cross-language reuse is needed
Python venv = prototype or plugin option, not preferred user-managed runtime
```
