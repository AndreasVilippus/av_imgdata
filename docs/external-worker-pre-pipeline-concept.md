# External Worker Processing Concept Before Central Pipeline

## Purpose

This document defines the production architecture for external processor execution
before a central asynchronous pipeline is introduced.

The goal is to maximize use of the existing external Windows worker without copying
DSM workflows or moving Synology-specific authority away from the package.

## Architectural boundary

DSM remains authoritative for:

- operation identity and user-visible progress
- source selection
- Synology Photos API access
- metadata and sidecar reads/writes
- findings and review state
- person and face mutations
- target selection and fallback policy
- queue state and result consumption

The external worker owns only processor execution:

- image decoding required by the processor
- face detection
- face embedding
- multi-image detection/embedding batches
- embedding ranking
- profile vector math

The worker must not write package state, Synology Photos data or image metadata.

## Shared dispatch rule

All external face work goes through one DSM dispatch/result boundary:

```text
Domain workflow
→ detector/embedder adapter
→ ExternalWorkerProcessorService / batch extension
→ WorkerApiService queue
→ compatible external worker
→ processor result
→ normalized DSM result
→ existing domain workflow continues
```

A domain workflow must not implement a second external-worker-specific copy of its
business logic.

## Execution target policy

The integrated GUI paths use `external_preferred`.

```text
Worker API disabled
→ local native processor

No compatible fresh worker
→ local native processor

Compatible worker available
→ enqueue external job and wait

External job already enqueued and later fails
→ surface failure; do not start a duplicate local execution
```

Fallback is allowed only before enqueue. This prevents duplicate processing and keeps
write semantics deterministic.

## Processor contracts in production dispatch

The production DSM dispatch layer supports:

| Contract | Purpose |
| --- | --- |
| `face_native_detect` | detect faces in one shared-path image |
| `face_native_embed` | detect faces and create embeddings for one image |
| `face_native_detect_batch` | detect faces in multiple shared-path images in one processor job |
| `face_native_embed_batch` | detect/embed multiple images in one processor job |
| `face_native_rank_embeddings` | rank target embeddings against profile embeddings |
| `face_native_profile_math` | calculate centroid, medoid and intra-person similarity |

The schemas in `processor_contract/` remain the language-neutral authority for native
processor input and output.

## Batch is not the central pipeline

Batch execution combines multiple images inside one claimed processor job:

```text
DSM workflow
→ one detect_and_embed_many call
→ one face_native_embed_batch job
→ worker processes N images
→ one batch result
→ DSM workflow continues
```

This reduces process startup, model setup and request overhead. It does not create
multiple independent in-flight jobs and it does not change workflow ordering.

The later central pipeline instead concerns orchestration such as:

```text
queue work item 1..N
→ keep a bounded number of independent jobs in flight
→ receive results out of order
→ apply results in controlled order
→ refill the queue while DSM processes completed results
```

These two optimizations must remain separate.

## Shared-path contract

DSM never sends its absolute `/volume...` path as a portable worker path.

Single-image jobs use a relative `local_path`.
Batch jobs use relative `image_paths`.

Example:

```json
{
  "input_mode": "shared_path",
  "path_profile": "photos",
  "image_paths": [
    "2026/2026.08/a.heic",
    "2026/2026.08/b.jpg"
  ]
}
```

The external API loop validates every relative path and resolves it below its local
`path_base_dir`.

Examples:

```text
DSM root:     /volume1/photo
Windows root: \\savy\photo
Linux root:   /mnt/savy/photo
```

Rules:

- paths in transport payloads are relative and use `/`
- absolute or drive-qualified payload paths are rejected
- `..` traversal is rejected
- every batch entry is validated independently
- all DSM paths in one batch must belong to the same configured path profile
- worker-local absolute paths are created only after claim

This keeps one DSM job portable across workers with different mount paths.

## GUI/workflow integration

The existing processor boundaries are wrapped rather than replacing the workflows.

### Face-frame standardization

`FaceFrameStandardizationService._prepared_detector()` returns the external-capable
detector adapter. Existing scan, matching, findings and write behavior stays in the
service.

### Recognition

`FaceRecognitionService._prepared_embedder()` returns the external-capable embedder.
The adapter supports single embed, batch embed, ranking and profile math.

The recognition service already performs lookahead and calls `detect_and_embed_many()`.
That existing call now maps to `face_native_embed_batch` when supported by the worker.
No pipeline state is introduced.

### Face matching / missing InsightFace faces

The existing detector/embedder factories are wrapped only for the duration of the
InsightFace missing-face workflow. Its Photos and finding behavior is unchanged.

## Result consumption

Raw external results are not domain results.

The DSM consumer must:

1. verify job type and completed state;
2. obtain `processor_result`;
3. normalize through the same native processor normalization helpers used locally;
4. store the normalized result atomically with `result_consumed_at`;
5. purge the raw worker result after successful normalization;
6. return the normalized processor-shaped value to the existing workflow.

Consumption is idempotent. Reading an already consumed result returns the stored
normalized value instead of applying the raw result again.

## Batch result identity

Batch output is mapped back to the DSM source paths supplied when the job was created.
The processor result order is therefore treated as the contract order for the batch.
Domain workflows receive:

```text
{
  absolute DSM source path → normalized faces,
  ...
}
```

The external worker never decides Photos entity identity or final writes.

## Worker capability selection

A worker is compatible only when:

- heartbeat freshness is within the configured stale timeout;
- it advertises the required processor capability;
- image jobs advertise `shared_path` support;
- the Worker API is enabled.

Vector-only jobs such as ranking and profile math do not require a shared image-path
input mode.

For backward compatibility, a worker without a batch capability may still process
single-image jobs. The adapter falls back to individual external calls rather than
inventing a second batch implementation.

## Planned external warm runtime

The active worker protocol advertises only processor operations that are currently
executable end to end. `warm_processor_worker` has therefore been removed from active
capability advertisement and remains a planned runtime feature, not a job type.

The bundled native face processor supports a persistent `worker` command internally,
but the current external API loop starts `av-imgdata-worker once` for each claimed job.
Therefore the external runtime does not yet keep the native processor/model process
alive across jobs.

A correct implementation requires the long-running external runtime to own the
persistent processor process and to report truthful warm/readiness state. This is a
worker-runtime lifecycle change, not a DSM domain workflow change and not the central
pipeline.

Until that implementation exists:

- no warm-runtime capability is advertised;
- no `warm_processor_worker` job is accepted;
- no reduced cross-job model-load latency is claimed.

## Byte inputs

`detect_and_embed_bytes()` remains local because the current external input mode is
`shared_path`.

Supporting embedded previews remotely requires an explicit new transport contract,
such as staged shared assets or bounded byte upload. It must not be smuggled through
path fields.

## Platform status

Windows single-image shared-path execution is validated against the NAS.

The architecture and transport format remain platform-neutral. Linux and Docker must
validate:

- path-base mapping
- HEIC/HEIF decoding
- processor/model discovery
- batch path materialization
- result reporting

No Linux- or Docker-specific branch belongs in DSM business workflows.

## Before central pipeline: completion criteria

The pre-pipeline worker integration is complete when:

- all six face processor contracts above are dispatched and consumed centrally;
- recognition uses the existing batch call path when a compatible worker supports it;
- Windows single and batch execution are validated;
- local fallback remains valid when no compatible worker exists;
- worker/runtime warm-state claims are truthful;
- tests cover single, batch, vector, path-validation and result-consumption behavior;
- concepts and coverage documentation match the actual implementation.

After these conditions, further throughput work should be implemented as a central
pipeline service rather than by adding workflow-specific concurrency.
