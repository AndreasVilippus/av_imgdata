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

## Continuous Worker Operation

For production use, the worker API loop must run continuously rather than with `--max-iterations 1`.

Interactive Windows command:

```powershell
$Bundle = "C:\Program Files\AV ImgData Worker"

& "$Bundle\bin\av-imgdata-worker-api-loop.exe" `
  --config "$Bundle\config\worker.json" `
  --worker-bin "$Bundle\bin\av-imgdata-worker.exe" `
  --path-base-dir "\\savy\photo"
```

Omitting `--max-iterations` means the loop continues polling according to `poll_interval_seconds`.

The worker must eventually be installed as a managed background service:

```text
Windows:
- Windows Service preferred
- automatic start
- restart on failure
- dedicated service account with SMB permissions
- stdout/stderr redirected to rotating logs

Linux:
- systemd unit
- Restart=on-failure
- dedicated user
- mounted NAS share
- journal or rotating file logs
```

A mapped drive letter must not be assumed for a Windows Service. UNC paths should be the default because drive mappings are normally user-session specific.

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

The additional states are required before general production use.

Required timestamps and ownership fields:

```text
created_at
updated_at
claimed_at
started_at
finished_at
claimed_by
attempts
lease_expires_at
next_retry_at
```

## Claim Lease And Recovery

A claimed job must not remain permanently blocked when a worker crashes or loses network access.

Required behavior:

```text
1. server assigns a claim lease
2. worker periodically renews the lease while processing
3. server detects expired leases
4. expired jobs return to queued or failed according to retry policy
5. late results from an expired claim are rejected unless they match the active attempt token
```

Each claim should receive an immutable attempt identifier:

```text
job_id
attempt_id
claimed_by
lease_expires_at
```

Result and failure requests must include `attempt_id` to prevent stale workers from overwriting a newer attempt.

## Execution Target Selection

Target abstraction:

```text
JobDispatcher
├── LocalNativeProcessorAdapter
└── ExternalWorkerProcessorAdapter
```

Recommended policy options:

```text
local_only
external_preferred
external_required
local_preferred
```

Default production policy should initially be:

```text
local_preferred
```

During controlled rollout, selected job types or operations can use:

```text
external_preferred
```

Fallback decisions must be explicit. A failed external job must not silently execute locally when duplicate processing could cause conflicting writes.

## Input Modes

### shared_path

`shared_path` is the preferred LAN mode.

DSM stores a relative path under a configured NAS path profile. Each worker resolves it against its own local path base.

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

Required controls:

```text
- worker token authentication
- active claim ownership
- attempt validation
- server-controlled source path
- path-profile validation
- streaming response
- size limits
- timeout and cleanup policy
```

`download` is not required for the first productive LAN rollout.

## Capabilities

Workers must advertise processor and input capabilities separately.

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

Claim matching must check:

```text
- job type
- input mode
- protocol version
- processor/model availability where relevant
```

Future metadata may include:

```text
CPU architecture
logical CPU count
RAM
GPU backend
GPU memory
model versions
processor versions
maximum concurrency
current load
```

## Result Contract And Server Processing

Recording a result in `worker-api-state.json` is not the final business operation.

The server requires a result-consumer layer:

```text
ExternalWorkerResultConsumer
→ load completed worker job
→ validate contract version
→ validate job type and attempt
→ validate processor status
→ validate expected result schema
→ map result to originating domain operation
→ execute package-owned final write
→ update progress/status
→ mark result consumed
```

Each external job should store origin metadata such as:

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

The server must support idempotent result consumption. Reprocessing the same completed result must not create duplicate records or corrupt progress counters.

Recommended additional fields:

```text
result_consumed_at
result_consumer_version
result_apply_status
result_apply_error
```

## Automatic Job Dispatch

Manual calls to `WorkerApiService.enqueue_job` are suitable for tests only.

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

After the single-image flow is reliable, extend to:

```text
face_native_embed
face batch operations
ranking/profile operations where suitable
optional image processor jobs
```

## Persistence

The current JSON state store is acceptable for protocol development and controlled single-worker testing.

Before high-volume production use, assess migration to SQLite or the package database because the system will require:

```text
- atomic claims
- multiple concurrent workers
- leases
- retry scheduling
- indexed queue selection
- result-consumption state
- retention and cleanup
- operational history
```

A staged rollout may retain JSON initially if only one worker and one API process are allowed.

## Concurrency

Initial safe mode:

```text
- one worker process
- one active job at a time
- one Worker API backend process controlling the JSON state file
```

Later concurrency model:

```text
- worker declares max_concurrency
- server allows multiple claims per worker or worker slots
- processor/model reuse is enabled where safe
- queue storage provides atomic transactions
```

Concurrency must not be increased until queue claims and final result application are transaction-safe.

## Security

Required production controls:

```text
- Worker API disabled by default
- HTTPS through DSM Reverse Proxy
- unique token per worker
- token revocation
- scoped tokens
- worker ID bound to token
- no arbitrary source paths accepted from workers
- no direct package database credentials on workers
- no Synology Photos database writes from workers
- request and result size limits
- audit log for registration, claims, results and failures
```

Tokens should not be committed to the repository or included in redistributable bundles.

## Logging And Diagnostics

Server logs should include:

```text
job_id
attempt_id
worker_id
job type
queue duration
claim duration
execution duration
result application duration
final status
error code
```

Worker logs should include:

```text
registration status
heartbeat failures
claim status
resolved input path
worker command
processor exit code
processor timing
result upload status
retry decisions
```

Secrets and full authorization headers must never be logged.

## Packaging And Administration

The DSM package should provide:

```text
- downloadable Windows worker ZIP
- downloadable Linux worker archive
- generated configuration template
- worker enrollment/token workflow
- path-profile configuration
- worker list and last-seen status
- revoke/remove action
- queue counts
- recent failures
```

The worker bundle should provide:

```text
- install/start/stop scripts
- service installation helper
- configuration validation command
- connectivity probe
- path-access probe
- processor/model probe
- log directory
- upgrade instructions
```

## Implementation Plan

### Phase 1: Persistent worker runtime

Goal: keep the validated Windows worker running and ready for jobs.

```text
- run API loop without --max-iterations
- define production worker.json
- verify repeated empty claims and later job pickup
- add graceful shutdown handling
- add reconnect/backoff behavior
- add rotating worker logs
- package Windows Service installation and removal scripts
- run service under an account with UNC share access
- document firewall, Reverse Proxy and SMB requirements
```

Acceptance criteria:

```text
- worker starts automatically after Windows reboot
- worker appears online in DSM status
- worker survives temporary API/network interruption
- a job queued after worker startup is claimed without manual restart
- completed result reaches the DSM Worker API
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

Acceptance criteria:

```text
- detected faces are applied through the same domain path as local processing
- duplicate result delivery does not duplicate writes
- malformed results are rejected and retained for diagnostics
- originating operation completes or fails correctly
```

### Phase 4: Reliability and recovery

Goal: tolerate crashes, disconnects and retries safely.

```text
- add running state
- add claim leases and attempt IDs
- add lease renewal
- requeue expired claims
- implement retry policy and backoff
- reject stale results
- add cancellation
- add queue and history cleanup
- define server restart recovery
```

Acceptance criteria:

```text
- killing a worker does not permanently block a job
- a retried job cannot be overwritten by the previous worker attempt
- server and worker restarts preserve correct job state
```

### Phase 5: Administration and observability

Goal: make the feature operable without command-line inspection.

```text
- worker administration API/UI
- enrollment and token rotation
- worker online/offline/stale status
- queue and failure views
- per-job diagnostics
- configuration validation
- health metrics and structured logs
```

### Phase 6: Scale and additional input modes

Goal: support broader deployments after the LAN worker path is stable.

```text
- input capability matching
- download input endpoint and worker cache
- Linux service packaging
- multiple workers
- worker concurrency slots
- transactional queue storage
- batch jobs
- optional Docker/cloud/GPU workers
```

## Immediate Next Steps

The next implementation sequence is:

```text
1. install the Windows API loop as a continuously running service
2. verify that it claims a job queued after service startup
3. add server path-profile configuration for /volume1/photo
4. implement ExternalWorkerProcessorAdapter for face_native_detect
5. enqueue jobs from the normal face-processing workflow
6. implement result-consumer mapping and final writes
7. add leases, retries and stale-worker recovery
8. add administration/status UI
```

The first vertical production slice is complete only when this flow works without manual commands:

```text
user/package operation
→ automatic enqueue
→ persistent Windows worker claim
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
- UNC paths are preferred for Windows background services.
- Manual enqueue commands remain test tooling only.
- Automatic dispatch and result consumption are the next core milestones.
- download mode, multiple workers and GPU/cloud execution follow after the first complete production slice.
```
