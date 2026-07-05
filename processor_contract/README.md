# Processor Contract

This directory contains the language-neutral contract between the DSM backend
and replaceable processor implementations.

The first implemented contract covers the native face processor boundary:

- `schemas/face-native-job-input.schema.json`
- `schemas/face-native-result.schema.json`

The DSM backend owns workflow, status, persistence and final writes. Native
processors only read staged inputs and return structured result JSON.

The current native face processor contract includes single-image face
detection/embedding, multi-image detection/embedding batches, embedding ranking
and profile vector math. Recognition decisions, thresholds and persistence stay
in the DSM backend.
