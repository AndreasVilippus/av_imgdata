import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _load_schema(name: str):
    return json.loads((Path("processor_contract/schemas") / name).read_text(encoding="utf-8"))


def test_face_native_job_input_schema_accepts_minimal_embed_job():
    schema = _load_schema("face-native-job-input.schema.json")
    payload = {
        "contract_version": "1.0",
        "job_id": "job-1",
        "type": "face_native_embed",
        "input": {"image_path": "/tmp/input.jpg", "source_id": "item-1"},
        "options": {
            "model_root": "/tmp/models",
            "model_name": "buffalo_l",
            "min_confidence": 0.5,
            "max_faces": 0,
            "det_size": [640, 640],
            "normalize_coordinates": True,
        },
    }

    jsonschema.Draft202012Validator(schema).validate(payload)


def test_face_native_result_schema_accepts_box_and_embedding_result():
    schema = _load_schema("face-native-result.schema.json")
    payload = {
        "contract_version": "1.0",
        "job_id": "job-1",
        "type": "face_native_embed",
        "status": "completed",
        "processor": {"name": "fake", "version": "1", "backend": "test"},
        "timing_ms": {
            "total": 12.34,
            "image_decode": 1.0,
            "model_load": 0.0,
            "detector_prepare": 2.0,
            "detector_run": 3.0,
            "detector_decode": 4.0,
            "recognizer_prepare": 5.0,
            "recognizer_run": 6.0,
            "embedding_normalize": 0.1,
            "result_write": 0.0,
            "recognizer_runs": 1,
            "recognized_faces": 2,
            "recognizer_batch_size": 2,
            "recognizer_batched": True,
            "recognizer_batch_fallback": False,
            "reused_models": True,
        },
        "result": {
            "faces": [{
                "face_id": "local-1",
                "confidence": 0.9,
                "box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "unit": "normalized"},
                "embedding": [0.25, 0.75],
            }]
        },
        "warnings": [],
    }

    jsonschema.Draft202012Validator(schema).validate(payload)


def test_face_native_job_input_schema_accepts_batch_and_vector_jobs():
    schema = _load_schema("face-native-job-input.schema.json")
    validator = jsonschema.Draft202012Validator(schema)

    validator.validate({
        "contract_version": "1.0",
        "job_id": "batch-1",
        "type": "face_native_embed_batch",
        "input": {"image_paths": ["/tmp/a.jpg", "/tmp/b.jpg"]},
        "options": {"model_root": "/tmp/models", "model_name": "buffalo_l"},
    })
    validator.validate({
        "contract_version": "1.0",
        "job_id": "rank-1",
        "type": "face_native_rank_embeddings",
        "input": {},
        "options": {},
        "target_embeddings": [[1.0, 0.0]],
        "profile_embeddings": [[1.0, 0.0], [0.0, 1.0]],
    })
    validator.validate({
        "contract_version": "1.0",
        "job_id": "profile-1",
        "type": "face_native_profile_math",
        "input": {},
        "options": {},
        "embeddings": [[1.0, 0.0], [0.8, 0.2]],
    })


def test_face_native_result_schema_accepts_batch_and_vector_results():
    schema = _load_schema("face-native-result.schema.json")
    validator = jsonschema.Draft202012Validator(schema)

    validator.validate({
        "contract_version": "1.0",
        "job_id": "batch-1",
        "type": "face_native_embed_batch",
        "status": "completed",
        "result": {"images": [{"image_path": "/tmp/a.jpg", "status": "completed", "faces": []}]},
    })
    validator.validate({
        "contract_version": "1.0",
        "job_id": "rank-1",
        "type": "face_native_rank_embeddings",
        "status": "completed",
        "result": {
            "ranks": [{
                "target_index": 0,
                "best_index": 0,
                "best_score": 0.99,
                "second_index": 1,
                "second_score": 0.1,
                "margin": 0.89,
            }]
        },
    })
    validator.validate({
        "contract_version": "1.0",
        "job_id": "profile-1",
        "type": "face_native_profile_math",
        "status": "completed",
        "result": {
            "centroid_embedding": [0.99, 0.1],
            "medoid_index": 0,
            "intra_person_similarity": 0.98,
        },
    })
