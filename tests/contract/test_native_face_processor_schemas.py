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
