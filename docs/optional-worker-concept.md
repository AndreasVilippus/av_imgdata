# Optional External Worker Concept

## Purpose

The optional external worker moves compute-intensive processor work from DSM to a
Windows or Linux host while the DSM package remains the authoritative application.

The external worker is optional. Package-internal native processing remains the local
execution path and pre-enqueue fallback.

Detailed current processor integration is defined in:

- `docs/external-worker-pre-pipeline-concept.md`
- `docs/external-worker-gui-coverage.md`
- `processor_contract/README.md`
- `docs/qt6-worker-gui-lgpl-concept.md`

## Current validated status

Windows `shared_path` single-image execution has completed a real NAS round trip:

```text
DSM Worker API
→ registration and heartbeat
→ capability-based claim
→ UNC path materialization
→ native image/face processing
→ structured result upload
→ DSM result consumption
→ existing workflow continues
```

Linux and Docker remain platform-validation targets. They must use the same DSM job
and processor contracts rather than platform-specific workflow logic.

## Authority

DSM owns:

- package configuration
- authentication, enrollment and token revocation
- Synology Photos access
- source selection
- execution-target selection
- job creation and queue state
- operation/action/mode/operation_id identity
- result validation and normalization
- findings and review state
- final Photos, database, sidecar and metadata writes
- user-visible progress and errors

The external worker owns:

- registration and heartbeat
- compatible job claim
- worker-local path materialization
- processor execution
- local workspace and diagnostics
- result or failure reporting

The worker must never directly mutate Synology Photos databases or package-owned
runtime state.

## Production processing flow

```text
DSM domain workflow
→ existing detector/embedder boundary
→ shared external-worker adapter
→ Worker API queue
→ external worker
→ native processor contract
→ Worker API result
→ DSM result consumer
→ existing domain workflow
```

There must not be separate local and external copies of a domain workflow.

## Execution policy

The GUI-integrated face workloads use `external_preferred`:

```text
Worker API disabled                       → local
no compatible fresh worker               → local
compatible worker before enqueue         → external
external job fails after enqueue          → fail, no duplicate local retry
```

A later explicit administration setting may expose other policies, but workflow code
must continue to use the shared dispatch service.

## Processor contracts

The active worker advertises and the DSM dispatches exactly these processor jobs:

```text
face_native_detect
face_native_embed
face_native_detect_batch
face_native_embed_batch
face_native_rank_embeddings
face_native_profile_math
```

All six have DSM-side production dispatch/result handling.

The language-neutral schemas under `processor_contract/` are the contract authority.
Recognition decisions, thresholds, findings and persistence remain DSM responsibilities.

## Batch execution

Batch operations are now part of the pre-pipeline architecture.

`face_native_embed_batch` is used by the existing Recognition lookahead through its
already established `detect_and_embed_many()` boundary. This avoids one external job
per image without introducing a second Recognition workflow.

`face_native_detect_batch` is available through the same detector adapter/service
boundary for callers that already operate on a group of images.

Batch is not the future central pipeline:

- batch = multiple images inside one processor job;
- pipeline = multiple independent jobs simultaneously in flight while DSM applies
  earlier results and keeps the worker supplied.

The central pipeline remains a separate later service.

## Shared-path transport

`shared_path` is the current production input mode.

DSM transports only relative paths. The external API loop maps them to its local root.

Example:

```text
DSM:     /volume1/photo/2026/a.heic
payload: 2026/a.heic
Windows: \\nas\photo\2026\a.heic
Linux:   /mnt/nas/photo/2026/a.heic
```

Single jobs use `local_path`. Batch jobs use `image_paths`.

Required path rules:

- relative paths only
- `/` as portable payload separator
- no drive-qualified or absolute paths
- no `..` traversal
- each batch entry validated independently
- DSM batch inputs must share one path profile
- worker-local absolute paths are created only after claim

This permits one queued job format to work with different Windows/Linux mount roots.

## Result consumption

Worker result recording is not the final business operation.

DSM result consumption:

1. verifies completed state and expected job type;
2. extracts the processor result;
3. normalizes through the existing native processor normalization helpers;
4. stores the normalized value and consumption timestamp atomically;
5. removes the raw worker result after successful normalization;
6. returns the processor-shaped result to the original domain workflow.

Consumption is idempotent.

## Worker application

The preferred Windows operating model remains the Qt desktop application described in
`docs/qt6-worker-gui-lgpl-concept.md`.

The application supervises the existing API-loop process rather than implementing a
second queue client. Command-line operation remains supported for Windows diagnostics,
Linux and automation.

The external bundle remains responsible for:

- worker executable
- API-loop executable
- face processor
- optional image processor used for supported decoding/normalization
- runtime libraries
- user-supplied model installation/configuration
- worker configuration/token files
- logs and probes

Secrets must not be emitted into normal logs or UI status.

## Worker liveness

A worker is usable when:

- it is registered;
- its heartbeat is fresh;
- it advertises the requested processor capability;
- image jobs have a compatible input mode;
- the Worker API is enabled.

Current controlled-rollout assumptions remain conservative: a JSON Worker API state
store and a small number of workers/jobs. Transactional storage such as SQLite should
be evaluated before high-volume multi-worker orchestration.

## Planned persistent warm runtime

`warm_processor_worker` is not currently advertised by the active protocol and is not
a processor job contract.

The package-internal native processor service can keep the face processor's persistent
`worker` subprocess alive. The current *external* API loop, however, invokes
`av-imgdata-worker once` for each claimed job. It therefore does not yet provide true
cross-job persistent model residency.

A correct implementation must change process ownership in the long-running external
worker/API-loop and expose truthful warm/readiness diagnostics. Until then:

- no warm capability is advertised;
- no warm job is accepted;
- no cross-job model residency is promised.

This runtime optimization is independent from the DSM central pipeline and should be
implemented/validated separately.

## Intentionally local inputs and work

The following remain local by design:

- Synology Photos requests and mutations
- metadata and sidecar access
- findings/review persistence
- embedded preview bytes processed through `detect_and_embed_bytes()`

The last item remains local because the external input contract currently supports
`shared_path`, not arbitrary byte uploads. A future staged-asset or byte-input contract
must be explicit and bounded.

## Recovery and lifecycle direction

The current queue supports queued, claimed, completed and failed states. Production
hardening still needs lease/recovery semantics for crashed workers before aggressive
multi-worker concurrency is enabled.

Target lifecycle work remains:

```text
claim lease
attempt identity
lease renewal
expired claim recovery
late-result rejection
cancellation/invalidated-result handling
```

These rules are prerequisites for a robust central pipeline with several independent
in-flight jobs.

## Security

Production constraints:

- Worker API disabled by default
- HTTPS through DSM/reverse proxy for non-local transport
- unique token per worker
- worker ID bound to credentials
- revocation and rotation
- no arbitrary NAS paths supplied by workers
- no Synology database credentials on workers
- request/result size limits
- structured audit/debug logging without secrets

## Pre-pipeline completion state

Before implementing the central pipeline, the intended state is:

```text
single detect             integrated
single embed              integrated
detect batch              integrated in dispatch/adapter transport
embed batch               integrated and used by Recognition lookahead
embedding ranking         integrated
profile math              integrated
byte preview input        intentionally local
external persistent warm  planned runtime work; not advertised as available
Windows single path       validated
Windows batch path        requires bundle/runtime validation
Linux/Docker              requires platform validation
```

After batch validation and worker-runtime truthfulness are complete, further throughput
improvements should be implemented once in a central pipeline service rather than in
individual domain workflows.
