# Optional Worker Concept

## Purpose

This document describes an optional external worker subproject for `av_imgdata`.

The primary goal is to improve performance and keep the DSM package responsive by moving long-running or CPU/RAM-heavy processing out of the DSM package when a suitable external system is available.

The worker is optional. The DSM package must continue to work without a registered worker by using the existing local processing path or a local processor abstraction.

## Target Architecture

```text
DSM package
  - package lifecycle
  - DSM integration
  - configuration
  - authentication boundary
  - job creation
  - status persistence
  - file API for worker input/output
  - fallback local processing

Web UI / browser client
  - rendering
  - filtering and sorting already-loaded data
  - validation of simple forms
  - progress and log display
  - worker configuration screens

Optional external worker
  - runs outside DSM
  - pulls jobs from DSM
  - downloads input files through the DSM API
  - processes jobs on local CPU/GPU/RAM
  - uploads results through the DSM API
  - reports progress, logs, metrics, and errors
```

The DSM package remains the controller. The external worker provides compute capacity.

## Subproject Layout

Add the worker as a separate subproject:

```text
project-root/
  dsm-package / existing application code
  ui / existing frontend code
  worker/
    cmd/
    internal/
      api/
      capabilities/
      config/
      files/
      jobs/
      service/
    tests/
    build/
    README.md
  shared/
    api-contracts/
    job-schemas/
    status-schemas/
```

If the existing repository layout does not use `dsm-package/` and `ui/` as top-level folders, the worker should still be added as its own top-level `worker/` directory and the shared contracts should be placed where they best fit the current source layout.

## Required Refactoring In The DSM Package

### 1. Introduce a job model

Long-running actions must be represented as jobs instead of direct synchronous processing from routes or UI actions.

Required job fields:

```json
{
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

Recommended job status values:

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

Introduce a processor/dispatcher boundary:

```text
JobDispatcher
  - create_job
  - select_processor
  - assign_job
  - update_status

Processor implementations
  - LocalProcessor
  - RemoteWorkerProcessor
```

The initial implementation can route all jobs to `LocalProcessor`. Remote execution is then added without changing UI-facing routes again.

### 3. Keep API routes thin

Routes should validate requests, create jobs, return status, and expose results. They should not own workflow logic.

This follows the current planning rule from the modernization plan: do not make API routes workflow owners.

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

Optional endpoints:

```text
GET  /api/worker/config
POST /api/worker/capabilities
POST /api/worker/jobs/{job_id}/cancel
GET  /api/worker/jobs/{job_id}/input/{asset_id}
PUT  /api/worker/jobs/{job_id}/output/{asset_id}
```

### 5. Add capability-based assignment

A worker must announce what it can process.

Example capability payload:

```json
{
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

DSM should only assign jobs to workers with matching capabilities and a compatible protocol version.

## File Transfer Decision: Variant B Only

The worker concept uses Variant B: DSM provides files through its own API.

The worker does not require SMB, NFS, WebDAV, or direct access to DSM shares in the first implementation.

### Variant B flow

```text
1. UI starts an operation.
2. DSM creates a job.
3. Worker pulls the next compatible job.
4. Worker requests the input file through the DSM API.
5. DSM streams the file to the worker.
6. Worker processes the file in its local temp directory.
7. Worker uploads the result through the DSM API.
8. DSM validates and stores the result.
9. DSM updates persisted job/runtime status.
10. UI displays progress and completion state.
```

### Required file API behavior

Input download:

```text
GET /api/worker/jobs/{job_id}/input/{asset_id}
```

Result upload:

```text
PUT /api/worker/jobs/{job_id}/output/{asset_id}
```

Recommended support:

```text
- streaming download
- streaming upload
- file size limit validation
- content hash validation
- resumable upload later, if large files require it
- temporary file staging on DSM before final commit
- cleanup of abandoned temporary files
```

### Why Variant B is selected

Benefits:

```text
- works on Windows, Linux, macOS, Docker, and cloud systems
- no shared folder setup required
- no direct filesystem permissions need to be granted to the worker
- DSM remains the authority for file access
- simpler support for external networks and NAT/firewall setups
- easier to secure and audit than direct share access
```

Costs:

```text
- DSM still handles file streaming I/O
- very large files may need chunked or resumable transfer
- throughput depends on DSM network and API implementation
- implementation must avoid loading full files into memory
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

## Recommended Worker Technology

### Primary recommendation: Go

Use Go for the first native worker implementation.

Rationale:

```text
- single-binary delivery for Windows, Linux, macOS
- good HTTP/TLS/JSON support
- good concurrency for polling, transfer, and job execution
- low operational overhead
- no Python runtime or venv setup required
- easier cross-platform service packaging than C/C++
```

Expected build artifacts:

```text
worker-windows-amd64.exe
worker-linux-amd64
worker-linux-arm64
worker-darwin-arm64
```

### Alternative: Rust

Rust is a strong alternative if the worker itself performs heavy native processing.

Use Rust when:

```text
- maximum CPU performance is required
- memory safety is important
- a static native binary is desired
- processing code is expected to grow substantially
```

### C/C++ usage

Do not build the whole worker in C unless there is a measured need.

C or C++ is appropriate for narrow processing modules only:

```text
- hashing hot paths
- binary parsing
- image or video primitives
- compression/decompression primitives
```

The main worker process should remain in Go or Rust so networking, config, service handling, and error reporting stay maintainable.

### Python venv usage

A Python venv is acceptable for prototypes or for tasks that strongly depend on Python libraries.

It is not the preferred end-user worker format because:

```text
- Python version management is fragile on user systems
- venv setup is more error-prone than a native binary
- CPU-bound processing is usually slower unless native libraries do the work
- packaging for Windows, Linux, and macOS creates additional support cases
```

If Python processors are needed, prefer one of these forms:

```text
- packaged executable with PyInstaller or Nuitka
- Docker image for controlled environments
- plugin invoked by the Go/Rust worker with strict input/output contracts
```

## Client-Side Components

### Browser client candidates

The browser client can take over UI-side work:

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

The browser client must not own trusted processing decisions.

Do not move these responsibilities to the browser:

```text
- DSM file authorization
- secret handling
- final write decisions
- long-running processing
- mutation workflow ownership
- worker token generation
```

### Desktop client candidates

A desktop client can be added later, but it is not required for the first worker version.

Useful desktop client functions:

```text
- install/start/stop worker service
- show local worker status
- configure DSM URL and token
- display local logs
- run connection test
```

A desktop client should be considered a convenience wrapper around the worker, not a separate processing architecture.

### CLI client candidates

The worker should include a CLI from the first version:

```text
worker configure
worker register
worker start
worker status
worker test-connection
worker install-service
worker uninstall-service
```

This is useful for Windows Task Scheduler, Windows Service setup, systemd, Docker, and cloud-init.

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

### Phase 1: Local job abstraction

Status: Open.

Tasks:

```text
- identify long-running processing paths
- define job schema
- add job persistence
- add status values
- add LocalProcessor implementation
- route existing local processing through the processor boundary
```

Acceptance criteria:

```text
- current local behavior still works without external worker
- UI-facing behavior does not regress
- job status can be queried independently of processing implementation
```

### Phase 2: Worker API in DSM package

Status: Open.

Tasks:

```text
- add worker registration endpoint
- add heartbeat endpoint
- add next-job endpoint
- add progress/status/log endpoints
- add API input download endpoint
- add API result upload endpoint
- add token-based worker authentication
```

Acceptance criteria:

```text
- a test client can register as a worker
- a test client can pull a queued job
- a test client can download input through the DSM API
- a test client can upload output through the DSM API
- DSM records status transitions and errors
```

### Phase 3: First Go worker

Status: Open.

Tasks:

```text
- create worker subproject
- implement configuration loading
- implement registration
- implement heartbeat
- implement job polling
- implement API file download/upload
- implement at least one simple processing job
- implement structured logging
- provide Windows and Linux builds
```

Acceptance criteria:

```text
- worker runs on Windows and Linux
- worker processes a real job through Variant B API transfer
- worker can recover cleanly from DSM unavailability
- worker does not require a Python venv
```

### Phase 4: UI integration

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

### Phase 5: Performance hardening

Status: Deferred until measured.

Tasks:

```text
- measure DSM API transfer throughput
- measure CPU time moved away from DSM
- add chunked/resumable upload only if large files require it
- evaluate Rust/C modules only for measured hot paths
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
- Go worker
- pull model
- Variant B API file transfer only
- token authentication
- registration and heartbeat
- one or two concrete job types
- structured job status
- Windows and Linux builds
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
Optional Go worker = external compute component
File transfer = Variant B through DSM API only
Future performance modules = Rust/C only after measurement
Python venv = prototype or plugin option, not preferred runtime
```
