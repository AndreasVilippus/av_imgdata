# External Worker GUI Coverage

## Scope before the central pipeline service

The DSM backend remains the source of truth for operation identity, status, findings,
review and writes. External workers execute only processor-contract operations. The
shared dispatch service applies `external_preferred`: local execution is allowed only
when no external worker is available before enqueue; no duplicate local retry is
started after enqueue.

Package and external worker are one versioned release unit. There is no compatibility
fallback for older worker versions, incomplete capability sets or mixed package/worker
releases. A fresh registered worker must match the package worker version and the full
active capability contract. Contract mismatch is an explicit error.

Batch execution is a processor optimization, not a pipeline. One existing workflow
call may submit several image paths as one processor job, but the DSM workflow still
waits for that job and applies its result synchronously. Queue prefill and multiple
independent in-flight jobs remain deferred to the central pipeline service.

## Worker-enabled GUI processes

| GUI area | Action | Worker contract |
| --- | --- | --- |
| Cleanup | Standardize face frames | `face_native_detect`; batch adapter available as `face_native_detect_batch` |
| Cleanup | Build person profiles | `face_native_embed`, `face_native_embed_batch`, `face_native_profile_math` |
| Cleanup | Review recognition reference faces | `face_native_rank_embeddings` |
| Face matching | Recognize unknown faces with InsightFace | `face_native_embed`, `face_native_embed_batch`, `face_native_rank_embeddings` |
| Checks | Person assignments with InsightFace | `face_native_embed`, `face_native_embed_batch`, `face_native_rank_embeddings` |
| Face matching | Search missing faces with InsightFace | `face_native_detect` or `face_native_embed`; batch interfaces are available when the caller supplies multiple paths |

The recognition service actions keep their existing operation/action identities:

- `recognition_build_profiles`
- `recognition_check_reference_outliers`
- `recognition_analyze_unknown_faces`
- `recognition_check_person_assignments`

The existing recognition lookahead already calls `detect_and_embed_many()`. With the
matching package worker release, that call maps to one external
`face_native_embed_batch` job instead of a sequence of individual external embed jobs.

## Implemented worker processor contracts

Production DSM dispatch/result handling and active worker advertisement exist for:

- `face_native_detect`
- `face_native_embed`
- `face_native_detect_batch`
- `face_native_embed_batch`
- `face_native_rank_embeddings`
- `face_native_profile_math`

For `shared_path` batch jobs, DSM stores relative `image_paths`. The Windows/Linux API
loop validates every path and materializes every entry below the worker's configured
`path_base_dir` before invoking the processor. Absolute paths, traversal and mixed
path-profile inputs are rejected.

## Package-worker compatibility rule

A fresh worker is usable only when all of the following match the package contract:

- `worker_version`
- complete active capability set
- required input mode for image jobs
- protocol-defined processor contracts

A fresh worker that violates this unit contract raises
`external_worker_contract_mismatch`. The DSM backend must not downgrade a batch call to
single-image external jobs and must not silently treat an older external worker as a
supported target.

The normal local package processor remains available only when there is no usable
external worker before enqueue or when the Worker API is disabled. That is execution
target selection, not version compatibility.

## Planned external warm runtime

`warm_processor_worker` is not advertised by the active worker protocol and is not an
enqueueable job type. The bundled face processor already has a persistent `worker`
command, but the external API loop currently launches `av-imgdata-worker once` per
claimed job and therefore cannot truthfully promise cross-job model residency.

A future warm-runtime implementation must change process ownership inside the
long-running external worker/API-loop and expose truthful readiness/diagnostics. This
is a separate runtime optimization and must not be confused with the central DSM
pipeline.

## Intentionally local work

- Synology Photos API access
- metadata and sidecar reads/writes
- findings, review and mutation logic
- image bytes extracted from embedded previews, because the current worker input
  contract is `shared_path`
- execution-target fallback when Worker API is disabled or no fresh external worker is
  available

## Deferred pipeline scope

Queue prefill, multiple independent in-flight work items, ordered result application,
durable per-item pipeline state and cancellation are intentionally deferred to a
central pipeline service. No workflow-specific pipeline implementation is introduced
here.

## Validation status

Windows single-image `shared_path` execution has been validated against the NAS and
returned usable face results. The new batch path requires the next Windows bundle/build
validation. Linux and Docker remain platform validation tasks; no platform-specific
business logic is introduced in the DSM dispatch layer.
