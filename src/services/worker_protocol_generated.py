#!/usr/bin/env python3
"""Generated from worker/protocol/worker-protocol.json. Do not edit manually."""

PROTOCOL_VERSION = "1.0"
WORKER_VERSION = "0.10.0"
CONFIG_SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 2
TOKEN_SCOPES = (
    "worker_api",
    "models_read",
)
CAPABILITIES = (
    "face_native_detect",
    "face_native_embed",
    "face_native_detect_batch",
    "face_native_embed_batch",
    "face_native_rank_embeddings",
    "face_native_profile_math",
    "warm_processor_worker",
)
INPUT_MODES = (
    "shared_path",
)
