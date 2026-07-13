# Optional External Worker Concept

## Purpose

This document defines the target architecture and implementation plan for optional external workers in `av_imgdata`.

The primary objective is to move compute-intensive image and face processing from the NAS to a Windows or Linux host while the DSM package remains the authoritative controller.

The external worker is optional. The package-internal processor path remains available as the local execution path and fallback.

## Current Status

The first complete Windows `shared_path` round trip has been validated with version `0.10.0`:

```text
DSM Worker API
→ worker registration
→ heartbeat
→ job claim
→ UNC path resolution
→ HEIC image decode
→ native face detection
→ structured result upload
→ completed server-side job state
```

Validated test job:

```text
job_id: unc-face-test-004
job type: face_native_detect
input mode: shared_path
worker path base: \\savy\photo
input: 2026/2026.02/20260301_152542.heic
worker exit code: 0
server report: result
```

The Windows API-loop process launch defect was fixed by replacing manual shell-command assembly with the runtime process launcher that passes executable and arguments separately.

## Current Implemented Components

### DSM package

```text
- optional FastAPI Worker API mounted at /worker-api
- token authentication
- worker registration
- heartbeat handling
- job enqueue
- priority queue
- capability-based job-type filtering
- claim ownership
- result and failure recording
- package-local worker state persistence
- worker and queue status
- worker deletion with claimed-job requeue
```

Current endpoints:

```text
GET  /worker-api/status
POST /worker-api/register
POST /worker-api/heartbeat
POST /worker-api/claim
POST /worker-api/result
POST /worker-api/fail
```

### External worker bundle

```text
- Windows and Linux bundle targets
- worker configuration and token files
- API loop executable
- worker executable
- native face processor
- ONNX Runtime and HEIF support
- face model bundle
- shared_path resolution through --path-base-dir
- structured processor results
```

### Validated processor path

```text
av-imgdata-worker-api-loop
→ av-imgdata-worker once
→ av-imgdata-face-processor
→ processor-result JSON
→ Worker API result endpoint
```

## Authority And Responsibility

The DSM package remains responsible for:

```text
- package configuration
- authentication and token management
- worker enrollment and revocation
- Synology Photos integration
- source-file selection
- job creation
- job ownership and queue state
- execution-target selection
- result validation
- retries and timeout decisions
- final database and metadata writes
- user-visible status and progress
- conflict handling
- persistence
```

The external worker is responsible for:

```text
- registration and heartbeat
- claiming compatible jobs
- resolving or downloading inputs
- executing compatible processors
- reporting structured results or failures
- maintaining its local workspace
- exposing operational diagnostics
```

The worker must never write directly into Synology Photos databases or package-owned state.

## Target Runtime Flow

```text
DSM application operation
→ JobDispatcher
→ create external-worker job
→ WorkerApiService.enqueue_job
→ worker heartbeat and claim
→ worker executes processor
→ POST result or fail
→ DSM result consumer validates response
→ domain service applies result
→ original operation/progress state advances
```

The existing Worker API currently covers the middle section. The missing production work is primarily the integration before enqueue and after result recording.

## Windows Worker Application

### Decision

The preferred Windows operating model is a desktop application that starts, stops and supervises the existing worker runtime.

A Windows Service is not required for the first production rollout. It may remain an optional later operating mode for unattended servers.

The desktop application is preferred initially because it provides:

```text
- explicit user control over start and stop
- visible connection and worker state
- simpler SMB access under the logged-in user account
- no separate Windows service-account setup
- direct access to user-session UNC credentials
- easier configuration, diagnostics and log inspection
- safer controlled rollout while the protocol is still evolving
```

### Architecture

The application should not duplicate worker or processor logic.

Preferred first implementation:

```text
av-imgdata-worker-gui.exe
→ validates configuration and dependencies
→ starts av-imgdata-worker-api-loop.exe through QProcess
→ reads structured JSON output from stdout/stderr
→ displays connection, claim, job and error state
→ stops the API loop gracefully
```

This follows the separate Qt GUI concept in `docs/qt6-worker-gui-lgpl-concept.md`.

The existing executables remain independently usable from the command line.

### Required application functions

Initial application surface:

```text
- Start Worker
- Stop Worker
- Restart Worker
- connection status: disconnected, connecting, online, degraded
- worker state: stopped, idle, processing, stopping, failed
- current worker ID and API URL
- configured shared-path root
- last heartbeat time
- current job ID and type
- latest processor timing/result summary
- recent errors
- open log directory
- run connectivity probe
- run path-access probe
- run processor/model probe
```

Configuration screen:

```text
- Worker API URL
- worker ID
- token file or enrollment workflow
- worker configuration file
- shared-path base directory
- polling interval
- log directory and retention
- start minimized
- start worker when application opens
- optional launch application at Windows sign-in
```

Secrets must not be shown in logs or normal status views.

### Process ownership

The GUI owns the API-loop child process it starts.

Required behavior:

```text
- prevent two API-loop instances for the same worker configuration
- use absolute executable and configuration paths
- pass executable and arguments separately through QProcess
- capture stdout and stderr continuously
- retain the real child exit code
- provide graceful stop before forced termination
- show unexpected child-process termination as a visible error
- allow restart without closing the GUI
```

The API loop must also remain capable of running independently for Linux, automation and diagnostics.

### Closing and session behavior

Default behavior:

```text
- closing the main window minimizes the application to the notification area
- choosing Exit stops the worker after confirmation when a job is active
- Windows sign-out or shutdown requests a graceful worker stop
- the application must not silently abandon an active child process
```

A setting may allow immediate exit when no job is active.

### Autostart policy

Autostart is optional and user-controlled:

```text
1. launch GUI manually and start worker manually
2. launch GUI manually and auto-start worker
3. launch GUI at Windows sign-in and auto-start worker
```

The first release should not silently install a Windows Service.

For machines that must process jobs without an interactive login, an optional service mode can be designed later using the same worker binaries and configuration contract.

### UNC and SMB access

The worker should continue using UNC paths such as:

```text
\\savy\photo
```

Because the GUI and child process run in the logged-in user session, they inherit that user's SMB access. The application must include a path-access probe and show a clear error when the configured share or test file is unavailable.

Mapped drive letters may be supported for interactive use but UNC paths remain the recommended configuration because they are unambiguous and also usable by future service or unattended modes.

## Continuous Worker Operation

The API loop runs continuously whenever the user has started the worker in the application.

Equivalent command-line form:

```powershell
$Bundle = "C:\Program Files\AV ImgData Worker"

& "$Bundle\bin\av-imgdata-worker-api-loop.exe" `
  --config "$Bundle\config\worker.json" `
  --worker-bin "$Bundle\bin\av-imgdata-worker.exe" `
  --path-base-dir "\\savy\photo"
```

Omitting `--max-iterations` means the loop continues polling according to `poll_interval_seconds`.

The GUI should supervise this process and present its structured output rather than implement a second polling loop.

## Worker Liveness Model

A worker is considered available only when:

```text
- registered
- last heartbeat is within the configured timeout
- advertised capabilities match the job
- required input mode is supported
- worker is not administratively disabled
```

Recommended initial values:

```text
poll interval:       2 seconds
heartbeat interval:  10 seconds or less
stale timeout:       30 seconds
claim lease:         5 minutes initially
```

The current API loop sends a heartbeat before each claim. The production implementation should keep this behavior but separate heartbeat freshness from job execution duration where long-running jobs require it.

## Job Lifecycle

Target states:

```text
queued
claimed
running
completed
failed
retry_wait
cancelled
expired
```

The current implementation uses:

```text
queued
claimed
completed
failed
```

Required ownership and timing fields:

```text
created_at
updated_at
claimed_at
started_at
finished_at
claimed_by
attempts
attempt_id
lease_expires_at
next_retry_at
```

## Claim Lease And Recovery

A claimed job must not remain permanently blocked when the application is closed, the worker crashes or network access is lost.

Required behavior:

```text
1. server assigns a claim lease and immutable attempt_id
2. worker renews the lease while processing
3. server detects expired leases
4. expired jobs return to queued or failed according to retry policy
5. late results from an expired attempt are rejected
```

When the user requests Stop while a job is active, the GUI should initially offer:

```text
- wait for current job, then stop
- cancel/abort worker process and let the server recover the lease
- keep running
```

Graceful completion should be the default.

## Execution Target Selection

Target abstraction:

```text
JobDispatcher
├── LocalNativeProcessorAdapter
└── ExternalWorkerProcessorAdapter
```

Policy options:

```text
local_only
external_preferred
external_required
local_preferred
```

Initial default:

```text
local_preferred
```

Controlled external rollout can use `external_preferred` for selected operations or job types.

Fallback decisions must be explicit. A failed external job must not silently execute locally when duplicate processing could cause conflicting writes.

## Input Modes

### shared_path

`shared_path` is the preferred LAN mode.

Example payload:

```json
{
  "input_mode": "shared_path",
  "path_profile": "photos",
  "local_path": "2026/2026.02/20260301_152542.heic",
  "min_confidence": 0.5,
  "max_faces": 10,
  "det_size": [640, 640]
}
```

Worker configuration examples:

```text
Windows: \\savy\photo
Linux:   /mnt/savy/photo
```

Rules:

```text
- local_path is always relative
- payload separator is /
- absolute paths are rejected
- drive-qualified paths are rejected
- path traversal is rejected
- resolved files must remain below the configured base
```

### download

`download` remains the planned fallback for workers without NAS-share access.

Proposed endpoint:

```text
GET /worker-api/jobs/{job_id}/input
```

`download` is not required for the first productive LAN rollout.

## Capabilities

Workers advertise processor and input capabilities separately.

Example:

```json
{
  "worker_id": "windows-worker-01",
  "capabilities": [
    "face_native_detect",
    "face_native_embed",
    "input_shared_path"
  ]
}
```

Claim matching must check job type, input mode, protocol version and relevant processor/model availability.

Future worker metadata may include CPU, RAM, GPU, model versions, processor versions, maximum concurrency and current load.

## Result Contract And Server Processing

Recording a result in `worker-api-state.json` is not the final business operation.

The server requires a result-consumer layer:

```text
ExternalWorkerResultConsumer
→ load completed worker job
→ validate contract version
→ validate job type and attempt
→ validate processor status and result schema
→ map result to originating domain operation
→ execute package-owned final write
→ update progress/status
→ mark result consumed
```

Each external job stores origin metadata:

```json
{
  "origin": {
    "operation_id": "scan-2026-001",
    "task_id": "photo-12345-face-detect",
    "service": "face_indexing",
    "entity_type": "photo",
    "entity_id": "12345"
  }
}
```

Result application must be idempotent. Reprocessing a completed result must not create duplicate records or corrupt progress counters.

## Automatic Job Dispatch

Manual calls to `WorkerApiService.enqueue_job` are test tooling only.

Production job creation must be integrated into the normal services that currently invoke processors locally.

Initial integration target:

```text
face_native_detect for one image
```

Required adapter behavior:

```text
1. receive the same logical processor request as the local adapter
2. select a path profile
3. convert the NAS source path to relative local_path
4. attach origin metadata
5. enqueue the worker job
6. return an asynchronous task reference
7. allow status polling or event-driven continuation
```

After the single-image flow is reliable, extend to embeddings, batch operations and suitable image-processor jobs.

## Persistence And Concurrency

The current JSON state store is acceptable for protocol development and controlled single-worker testing.

Initial safe mode:

```text
- one Worker API backend process
- one external worker application
- one active job at a time
```

Before high-volume or multi-worker use, migrate or evaluate migration to transactional storage such as SQLite for atomic claims, leases, retries, indexed queue selection, result-consumption state and cleanup.

## Security

Required production controls:

```text
- Worker API disabled by default
- HTTPS through DSM Reverse Proxy
- unique token per worker
- token revocation and rotation
- worker ID bound to token
- no arbitrary source paths accepted from workers
- no package database credentials on workers
- no Synology Photos database writes from workers
- request and result size limits
- audit log for registration, claims, results and failures
```

Tokens must not be committed to the repository or included in redistributable bundles.

## Logging And Diagnostics

Server logs should include job ID, attempt ID, worker ID, queue duration, claim duration, execution duration, result application duration, final status and error code.

Worker application logs should include:

```text
- application start and stop
- child-process command without secrets
- registration status
- heartbeat failures
- claim status
- resolved input path
- processor exit code and timing
- result upload status
- child-process exit status
- retry and reconnect decisions
```

The GUI should display a bounded recent-event view while writing full rotating logs to disk.

## Packaging And Administration

The Windows bundle should provide:

```text
- av-imgdata-worker-gui.exe
- existing API-loop, worker and processor executables
- Qt shared libraries and required plugins
- configuration template
- enrollment/token workflow
- connectivity, path and processor probes
- log directory
- upgrade and licensing information
```

The GUI should use Qt 6 shared libraries under the policy documented in `docs/qt6-worker-gui-lgpl-concept.md`.

The DSM package should provide worker enrollment, path-profile configuration, worker online/offline status, queue counts, recent failures and revoke/remove controls.

## Implementation Plan

### Phase 1: Windows worker control application

Goal: make the validated worker controllable and continuously usable without PowerShell.

```text
- create Qt Widgets application target
- supervise av-imgdata-worker-api-loop through QProcess
- implement Start, Stop and Restart
- parse structured API-loop JSON events
- show stopped, connecting, idle, processing and failed states
- implement configuration editor
- add connectivity, UNC path and processor/model probes
- add graceful stop and active-job warning
- add reconnect/backoff visibility
- add rotating logs and recent-event view
- add optional start-at-login and start-worker-on-open settings
```

Acceptance criteria:

```text
- user can start and stop the worker from the application
- no PowerShell command is required
- worker remains idle and later claims a newly queued job
- worker status and current job are visible
- temporary API/network interruption is visible and recoverable
- completed result reaches the DSM Worker API
- application restart does not require reconfiguration
```

### Phase 2: Automatic server dispatch

Goal: normal DSM processing creates external jobs without test scripts.

```text
- introduce JobDispatcher abstraction
- implement ExternalWorkerProcessorAdapter
- add path-profile configuration
- implement NAS path to relative local_path conversion
- integrate face_native_detect single-image flow
- attach operation/task/entity origin metadata
- expose asynchronous task status
- preserve local processor adapter as fallback
```

Acceptance criteria:

```text
- a normal DSM operation queues a worker job
- no manual Python enqueue command is required
- only compatible online workers can claim the job
- the originating DSM task remains traceable through job_id
```

### Phase 3: Result consumption and final writes

Goal: returned worker results affect the real package workflow.

```text
- implement ExternalWorkerResultConsumer
- validate ProcessorContract and worker result schemas
- map result to originating task/entity
- apply results through existing package/domain services
- make result application idempotent
- mark results consumed
- update progress and final operation status
- route worker failures into user-visible operation errors
```

### Phase 4: Reliability and recovery

```text
- add running state
- add claim leases and attempt IDs
- add lease renewal
- requeue expired claims
- implement retry policy and backoff
- reject stale results
- add cancellation semantics
- add queue and history cleanup
- define server and application restart recovery
```

### Phase 5: Administration and observability

```text
- DSM worker administration API/UI
- enrollment and token rotation
- worker online/offline/stale status
- queue and failure views
- per-job diagnostics
- configuration validation
- health metrics and structured logs
```

### Phase 6: Scale and additional operating modes

```text
- download input mode
- Linux systemd packaging
- optional Windows Service mode for unattended hosts
- multiple workers
- worker concurrency slots
- transactional queue storage
- batch jobs
- optional Docker/cloud/GPU workers
```

## Immediate Next Steps

```text
1. implement the Qt Windows worker control application as a QProcess supervisor
2. add Start, Stop, status display and persistent configuration
3. run the API loop continuously from the application
4. verify that a job queued after application startup is claimed without restart
5. add server path-profile configuration for /volume1/photo
6. implement ExternalWorkerProcessorAdapter for face_native_detect
7. enqueue jobs from the normal face-processing workflow
8. implement result-consumer mapping and final writes
9. add leases, retries and stale-worker recovery
10. add DSM administration/status UI
```

The first vertical production slice is complete only when this flow works without manual commands:

```text
user/package operation
→ automatic enqueue
→ running Windows worker application claims job
→ face processing
→ result return
→ server validation
→ package-owned final write
→ operation completion
```

## Final Decisions

```text
- DSM remains the authoritative controller and final-write owner.
- The internal processor remains available.
- External workers are optional execution targets.
- Windows shared_path is the first production target.
- A controllable desktop application is the preferred first Windows operating mode.
- The GUI supervises the existing API loop instead of duplicating worker logic.
- UNC paths remain the recommended Windows path configuration.
- Windows Service mode is optional and deferred to unattended deployments.
- Manual enqueue commands remain test tooling only.
- Automatic dispatch and result consumption are the next core milestones.
- download mode, multiple workers and GPU/cloud execution follow after the first complete production slice.
```