# External Worker Processing Concept Before Central Pipeline

## Purpose

This document defines the architectural boundary for external processor execution before a central asynchronous pipeline is introduced.

It describes the required behavior and remaining validation scope only. Historical implementation steps, completed activities and speculative runtime optimizations are intentionally not tracked here.

## Architectural boundary

DSM remains authoritative for:

- operation identity and user-visible progress
- source and target selection
- Synology Photos API access
- metadata and sidecar reads/writes
- findings and review state
- person and face mutations
- execution-target and fallback policy
- queue state and result consumption
- final domain writes

The external worker executes processor contracts only. This includes image decoding required by a processor, face detection, face embedding, batch detection/embedding, embedding ranking and profile-vector math.

The worker must not write package state, Synology Photos data or authoritative image metadata.

## Shared dispatch boundary

External processor work must use the shared DSM dispatch/result boundary:

```text
Domain workflow
→ detector/embedder or processor adapter
→ shared external-worker dispatch service
→ WorkerApiService queue
→ compatible external worker
→ processor result
→ normalized DSM result
→ existing domain workflow continues
```

A domain workflow must not implement an external-worker-specific copy of its business logic.

Raw worker results are transport results, not domain results. DSM must normalize them through the same processor normalization rules used for local execution before domain logic consumes them.

Result consumption must be idempotent. A completed worker result must not be applied twice.

## Execution target policy

The normal integrated policy is `external_preferred`:

```text
Worker API disabled
→ local native processor

No compatible fresh worker
→ local native processor

Compatible worker available
→ enqueue external job and wait

External job already enqueued and later fails
→ surface failure; do not start duplicate local execution
```

Fallback is allowed only before enqueue.

A fresh external worker is compatible only when it matches the package worker contract for the current release, including:

- worker version
- complete active capability set
- required input mode
- processor-contract expectations
- heartbeat freshness

A fresh but incompatible worker is a contract error. The package must not silently downgrade to an older or incomplete worker behavior.

Vector-only processor jobs do not require a shared image-path input mode.

## Processor contracts

The external worker boundary supports these face processor contracts:

| Contract | Purpose |
| --- | --- |
| `face_native_detect` | detect faces in one shared-path image |
| `face_native_embed` | detect faces and create embeddings for one image |
| `face_native_detect_batch` | detect faces in multiple shared-path images in one processor job |
| `face_native_embed_batch` | detect/embed multiple images in one processor job |
| `face_native_rank_embeddings` | rank target embeddings against profile embeddings |
| `face_native_profile_math` | calculate centroid, medoid and intra-person similarity |

The schemas in `processor_contract/` are the language-neutral authority for processor input and output.

## Batch is not the central pipeline

Batch execution combines multiple images inside one claimed processor job. It reduces processor startup, model setup and request overhead, but it does not create multiple independent in-flight jobs and does not change workflow ordering.

A later central pipeline may introduce orchestration such as:

```text
queue work item 1..N
→ keep a bounded number of independent jobs in flight
→ receive results out of order
→ apply results in controlled order
→ refill the queue while DSM processes completed results
```

That pipeline must remain a central service. Workflow-specific concurrency must not be added as a substitute.

## Shared-path contract

DSM must never send absolute NAS paths as portable worker paths.

Single-image jobs use a relative `local_path`. Batch jobs use relative `image_paths`.

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

Rules:

- transport paths are relative and use `/`
- absolute or drive-qualified paths are rejected
- `..` traversal is rejected
- every batch entry is validated independently
- all paths in one batch belong to the same configured path profile
- worker-local absolute paths are created only after claim below the configured `path_base_dir`

This keeps DSM jobs portable across workers with different local mount paths.

## Batch result identity

Batch output is mapped back to the DSM source paths supplied when the job was created. Processor result order is therefore treated as contract order for the batch.

The external worker never decides Synology Photos entity identity, findings state or final writes.

## Byte inputs

Byte-only processor inputs remain local while the external worker contract is `shared_path` based.

Remote byte or embedded-preview processing requires a separate bounded transport contract, for example staged shared assets or explicit byte upload. Path fields must not be overloaded for this purpose.

## Platform validation

Windows single-image and batch shared-path execution are considered validated through development use against the NAS.

The following platform validations remain open:

### Linux

Validate at minimum:

- path-base mapping
- HEIC/HEIF decoding
- processor and model discovery
- batch path materialization
- result reporting

### Docker

Validate at minimum:

- path-base mapping and mounted shared storage
- HEIC/HEIF decoding
- processor and model discovery
- batch path materialization
- result reporting
- container runtime/startup behavior

Linux- or Docker-specific behavior belongs in worker runtime/path adapters and packaging, not in DSM domain workflows.

## Completion boundary

From the architectural perspective, the pre-pipeline worker model is complete when the shared processor boundary, target-selection rules, path contract, result normalization/idempotency and package-worker compatibility rules remain preserved.

Linux and Docker platform validation remain explicitly open tasks and do not justify workflow-specific deviations from this architecture.

Further throughput orchestration belongs in a central pipeline service rather than in individual domain workflows.
