# External Worker GUI Coverage

## Scope before the central pipeline service

The DSM backend remains the source of truth for operation identity, status, findings,
review and writes. External workers execute only processor-contract operations. The
shared dispatch service applies `external_preferred`: local execution is allowed only
before a job is enqueued; no duplicate local retry is started after enqueue.

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

The existing recognition lookahead already calls `detect_and_embed_many()`. When a
compatible worker advertises `face_native_embed_batch`, that call is now one external
batch job instead of a sequence of individual external embed jobs.

## Implemented worker processor contracts

Production DSM dispatch/result handling exists for:

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

## `warm_processor_worker`

`warm_processor_worker` is currently advertised as a worker/runtime capability, but it
is not one of the face processor job contracts. The current external API loop launches
`av-imgdata-worker once` per claimed job, so it does not yet keep the face processor's
persistent `worker` process alive across claimed jobs.

Do not enqueue `warm_processor_worker` as if it were a completed processor contract.
A real warm-runtime implementation must own processor lifetime inside the long-running
external worker/API-loop process and expose truthful readiness/diagnostics. This is a
separate runtime optimization and must not be confused with the central DSM pipeline.

## Intentionally local work

- Synology Photos API access
- metadata and sidecar reads/writes
- findings, review and mutation logic
- image bytes extracted from embedded previews, because the current worker input
  contract is `shared_path`
- target selection fallback when Worker API is disabled or no compatible worker is
  ready

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
