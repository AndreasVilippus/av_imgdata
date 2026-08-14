# Processor Contract

This directory contains the language-neutral contract between the DSM backend
and replaceable processor implementations.

The implemented native face processor boundary is defined by:

- `schemas/face-native-job-input.schema.json`
- `schemas/face-native-result.schema.json`

The DSM backend owns workflow, status, persistence, target selection and final
writes. Native processors only read validated inputs and return structured result
JSON.

The current native face processor contract includes:

- `face_native_detect`
- `face_native_embed`
- `face_native_detect_batch`
- `face_native_embed_batch`
- `face_native_rank_embeddings`
- `face_native_profile_math`

Recognition decisions, thresholds, findings and persistence stay in the DSM
backend.

## Shared-path jobs

Single-image shared-path jobs carry one relative `local_path`. Batch jobs carry a
relative `image_paths` array. The external worker transport materializes those
paths below its configured local path base after claim; DSM absolute paths are not
portable processor inputs.

Batch results preserve input order and are normalized by DSM through the same
native face normalization helpers used by local processing.

## Runtime capabilities are not processor job types

Worker/runtime capabilities may describe execution features in addition to the six
processor contracts above. In particular, `warm_processor_worker` is a runtime
lifecycle capability name, not a `face-native-job-input` type and must not be
enqueued as a processor job.

True external warm processing requires the long-running worker runtime to retain the
native processor/model process across claimed jobs. That lifecycle is separate from
this processor input/result contract.
