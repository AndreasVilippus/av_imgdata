# External Worker GUI Coverage

## Scope before the central pipeline service

The DSM backend remains the source of truth for operation identity, status, findings,
review and writes. External workers execute only processor-contract operations. The
shared dispatch service applies `external_preferred`: local execution is allowed only
before a job is enqueued; no duplicate local retry is started after enqueue.

## Worker-enabled GUI processes

| GUI area | Action | Worker contract |
| --- | --- | --- |
| Cleanup | Standardize face frames | `face_native_detect` |
| Cleanup | Build person profiles | `face_native_embed`, `face_native_profile_math` |
| Cleanup | Review recognition reference faces | `face_native_rank_embeddings` |
| Face matching | Recognize unknown faces with InsightFace | `face_native_embed`, `face_native_rank_embeddings` |
| Checks | Person assignments with InsightFace | `face_native_embed`, `face_native_rank_embeddings` |
| Face matching | Search missing faces with InsightFace | `face_native_detect` or `face_native_embed` |

The recognition service actions use their existing operation/action identities:

- `recognition_build_profiles`
- `recognition_check_reference_outliers`
- `recognition_analyze_unknown_faces`
- `recognition_check_person_assignments`

## Intentionally local work

- Synology Photos API access
- metadata and sidecar reads/writes
- findings, review and mutation logic
- image bytes extracted from embedded previews, because the current worker input
  contract is `shared_path`
- target selection fallback when Worker API is disabled or no compatible worker is
  ready

## Deferred pipeline scope

Queue prefill, multiple in-flight work items, ordered result application, durable
per-item pipeline state and cancellation are intentionally deferred to a central
pipeline service. No workflow-specific pipeline implementation is introduced here.
