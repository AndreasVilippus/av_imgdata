import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.config_service import ConfigService
from services.native_face_processor_service import NativeFaceProcessorService, NativeFaceProcessorUnavailable


def _write_fake_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 9.9-test")
    raise SystemExit(0)
if cmd == "probe":
    print("probe accepted by native heif_decoder=available")
    raise SystemExit(0)
if cmd in {"detect", "embed"}:
    output = Path(args[args.index("--output") + 1])
    output.write_text(json.dumps({
        "contract_version": "1.0",
        "job_id": "job-test",
        "type": "face_native_" + cmd,
        "status": "completed",
        "processor": {"name": "fake", "version": "9.9-test", "backend": "test"},
        "result": {
            "faces": [{
                "confidence": 0.91,
                "box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "unit": "normalized"},
                "embedding": [0.25, 0.75],
            }]
        },
    }), encoding="utf-8")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_skeleton_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import sys

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 0.1.0-skeleton")
    raise SystemExit(0)
if cmd == "probe":
    print("probe accepted by skeleton")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_bridge_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import sys

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 0.2.0-python-bridge")
    raise SystemExit(0)
if cmd == "probe":
    print("bridge probe should not run during status")
    raise SystemExit(99)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_onnxruntime_smoke_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import sys

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 0.3.0-onnxruntime-smoke")
    raise SystemExit(0)
if cmd == "probe":
    print("probe accepted by onnxruntime_smoke")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_failing_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 9.9-test")
    raise SystemExit(0)
if cmd == "probe":
    raise SystemExit(0)
if cmd in {"detect", "embed"}:
    output = Path(args[args.index("--output") + 1])
    output.write_text(json.dumps({
        "contract_version": "1.0",
        "job_id": "job-test",
        "type": "face_native_" + cmd,
        "status": "failed",
        "processor": {"name": "fake", "version": "9.9-test", "backend": "native"},
        "result": {"faces": []},
        "error": {
            "code": "image_decode_failed",
            "message": "jpeg decode failed: /photo/example.heic",
            "retryable": False,
            "phase": "inference",
        },
    }), encoding="utf-8")
    raise SystemExit(1)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_input_echo_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 9.9-test")
    raise SystemExit(0)
if cmd == "probe":
    print("probe accepted by native heif_decoder=available")
    raise SystemExit(0)
if cmd in {"detect", "embed"}:
    input_path = Path(args[args.index("--input") + 1])
    output = Path(args[args.index("--output") + 1])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    image_path = payload["input"]["image_path"]
    output.write_text(json.dumps({
        "contract_version": "1.0",
        "job_id": "job-test",
        "type": "face_native_" + cmd,
        "status": "completed" if image_path.endswith(".jpg") else "failed",
        "processor": {"name": "fake", "version": "9.9-test", "backend": "test"},
        "result": {"faces": []},
        "input_seen": payload["input"],
        "error": {} if image_path.endswith(".jpg") else {"code": "wrong_input", "message": image_path},
    }), encoding="utf-8")
    raise SystemExit(0 if image_path.endswith(".jpg") else 1)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_worker_processor(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
cmd = args[0] if args else ""
if cmd == "version":
    print("av-imgdata-face-processor 9.9-test")
    raise SystemExit(0)
if cmd == "probe":
    print("probe accepted by native heif_decoder=available")
    raise SystemExit(0)
if cmd == "worker":
    for line in sys.stdin:
        request = json.loads(line)
        output = Path(request["output"])
        output.write_text(json.dumps({
            "contract_version": "1.0",
            "job_id": "job-test",
            "type": "face_native_" + request["command"],
            "status": "completed",
            "processor": {"name": "fake", "version": "9.9-test", "backend": "worker-test"},
            "timing_ms": {
                "total": 12.34,
                "image_decode": 1.0,
                "model_load": 0.0,
                "detector_prepare": 2.0,
                "detector_run": 3.0,
                "detector_decode": 4.0,
                "recognizer_prepare": 5.0,
                "recognizer_run": 6.0,
                "recognizer_runs": 2,
                "recognized_faces": 2,
                "recognizer_batch_size": 2,
                "recognizer_batched": True,
                "recognizer_batch_fallback": False,
                "reused_models": True,
            },
            "result": {"faces": []},
        }), encoding="utf-8")
        print(json.dumps({"request_id": request["request_id"], "returncode": 0}), flush=True)
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_native_face_processor_status_and_embed_contract(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_fake_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()
    assert status["available"] is True
    assert status["reason"] == "ready"
    assert status["backend"] == "native"
    assert status["inference_available"] is True
    assert status["heif_decoder_available"] is True
    assert "9.9-test" in status["version"]

    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg")
    faces = service.create_embedder(model_name="fallback").detect_and_embed(image)

    assert faces == [{
        "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.6000000000000001},
        "score": 0.91,
        "embedding": [0.25, 0.75],
        "x": 0,
        "y": 0,
        "w": 0,
        "h": 0,
        "center": {"x": 0.25, "y": 0.4},
    }]


def test_native_face_processor_logs_structured_result_error_on_nonzero_exit(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_failing_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    events = []
    service = NativeFaceProcessorService(config, package_root=tmp_path, debug_logger=lambda event, **fields: events.append((event, fields)))
    image = tmp_path / "image.heic"
    image.write_bytes(b"heic")

    with pytest.raises(NativeFaceProcessorUnavailable) as exc_info:
        service.create_embedder(model_name="fallback").detect_and_embed(image)

    assert "image_decode_failed: jpeg decode failed: /photo/example.heic" in str(exc_info.value)
    failed_events = [fields for event, fields in events if event == "native_face_processor_run_failed"]
    assert failed_events
    assert failed_events[-1]["returncode"] == 1
    assert failed_events[-1]["result_status"] == "failed"
    assert failed_events[-1]["error_code"] == "image_decode_failed"
    assert failed_events[-1]["error_message"] == "jpeg decode failed: /photo/example.heic"
    assert failed_events[-1]["processor_backend"] == "native"
    assert failed_events[-1]["output"] == ""


def test_native_face_processor_decodes_heic_to_jpeg_before_native_run(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_input_echo_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
        "files": {
            "IMAGE_DECODER_EXTENSIONS": ["heic", "heif"],
        },
    })
    events = []
    decoder = SimpleNamespace(
        decode_to_jpeg=lambda image_path: SimpleNamespace(
            success=True,
            image_bytes=b"\xff\xd8decoded-jpeg\xff\xd9",
            source="pillow-heif",
            error="",
        )
    )
    service = NativeFaceProcessorService(
        config,
        package_root=tmp_path,
        debug_logger=lambda event, **fields: events.append((event, fields)),
        image_decoder=decoder,
    )
    image = tmp_path / "image.heic"
    image.write_bytes(b"heic")

    faces = service.create_embedder(model_name="fallback").detect_and_embed(image)

    assert faces == []
    decoded_events = [fields for event, fields in events if event == "native_face_processor_input_decoded"]
    assert decoded_events
    assert decoded_events[-1]["source"] == "pillow-heif"
    assert decoded_events[-1]["decoded_suffix"] == ".jpg"
    assert [event for event, _fields in events].index("native_face_processor_input_decoded") < [
        event for event, _fields in events
    ].index("native_face_processor_run_finished")


def test_native_face_processor_reuses_persistent_worker(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_worker_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    events = []
    service = NativeFaceProcessorService(config, package_root=tmp_path, debug_logger=lambda event, **fields: events.append((event, fields)))
    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg")
    embedder = service.create_embedder(model_name="fallback")

    assert embedder.detect_and_embed(image) == []
    assert embedder.detect_and_embed(image) == []

    started = [fields for event, fields in events if event == "native_face_processor_worker_started"]
    assert len(started) == 1
    assert len([event for event, _fields in events if event == "native_face_processor_run_finished"]) == 2
    finished = [fields for event, fields in events if event == "native_face_processor_run_finished"]
    assert finished[-1]["native_timing_ms"]["total"] == 12.34
    assert finished[-1]["native_model_load_ms"] == 0.0
    assert finished[-1]["native_detector_run_ms"] == 3.0
    assert finished[-1]["native_recognizer_runs"] == 2
    assert finished[-1]["native_recognized_faces"] == 2
    assert finished[-1]["native_recognizer_batch_size"] == 2
    assert finished[-1]["native_recognizer_batched"] is True
    assert finished[-1]["native_recognizer_batch_fallback"] is False
    assert finished[-1]["native_reused_models"] is True


def test_native_face_processor_passes_onnxruntime_environment_config(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_worker_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "ORT_INTRA_THREADS": 2,
                "ORT_GRAPH_OPT_LEVEL": "extended",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    events = []
    service = NativeFaceProcessorService(config, package_root=tmp_path, debug_logger=lambda event, **fields: events.append((event, fields)))
    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg")

    assert service.create_embedder(model_name="fallback").detect_and_embed(image) == []

    starts = [fields for event, fields in events if event == "native_face_processor_run_start"]
    workers = [fields for event, fields in events if event == "native_face_processor_worker_started"]
    assert starts[-1]["AV_IMGDATA_ORT_INTRA_THREADS"] == "2"
    assert starts[-1]["AV_IMGDATA_ORT_GRAPH_OPT_LEVEL"] == "extended"
    assert workers[-1]["AV_IMGDATA_ORT_INTRA_THREADS"] == "2"
    assert workers[-1]["AV_IMGDATA_ORT_GRAPH_OPT_LEVEL"] == "extended"


def test_native_face_processor_status_reports_python_bridge_disabled_without_debug_enabled(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_bridge_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["available"] is False
    assert status["reason"] == "python_bridge_disabled"
    assert status["backend"] == "python_bridge"
    assert status["inference_available"] is False
    assert status["hot_path_available"] is False
    assert "disabled by default" in status["last_error"]


def test_native_face_processor_status_reports_python_bridge_as_diagnostic_only_with_debug_enabled(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_bridge_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
        "debug": {
            "BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED": True,
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["available"] is False
    assert status["reason"] == "python_bridge_diagnostic_only"
    assert status["backend"] == "python_bridge"
    assert status["inference_available"] is False
    assert status["hot_path_available"] is False
    assert status["probe_skipped"] == "python_bridge_status_probe_disabled"
    assert "too slow" in status["last_error"]
    assert "enabled" not in status["last_error"] or "disabled" not in status["last_error"]


def test_native_face_processor_status_reports_onnxruntime_smoke_as_not_complete(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_onnxruntime_smoke_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["available"] is False
    assert status["reason"] == "onnxruntime_smoke_only"
    assert status["backend"] == "onnxruntime_smoke"
    assert status["inference_available"] is False
    assert status["hot_path_available"] is False
    assert "not complete" in status["last_error"]


def test_native_face_processor_skeleton_is_not_inference_ready(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_skeleton_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": True,
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["present"] is True
    assert status["executable"] is True
    assert status["backend"] == "skeleton"
    assert status["available"] is False
    assert status["inference_available"] is False
    assert status["hot_path_available"] is False
    assert status["reason"] == "skeleton_no_inference"
    assert "does not run inference" in status["last_error"]


def test_native_face_processor_defaults_to_required_and_reports_missing_binary(tmp_path):
    service = NativeFaceProcessorService(ConfigService(str(tmp_path / "config.json")), package_root=tmp_path)

    status = service.status()

    assert status["enabled"] is True
    assert status["available"] is False
    assert status["reason"] == "insightface_license_not_acknowledged"


def test_native_face_processor_status_requires_insightface_license_acknowledgement(tmp_path):
    processor = tmp_path / "av-imgdata-face-processor"
    _write_fake_processor(processor)
    config_path = tmp_path / "config.json"
    config = ConfigService(str(config_path))
    config.writeConfig({
        "native_processors": {
            "FACE_PROCESSOR": {
                "ENABLED": True,
                "PATH": str(processor),
                "MODEL_ROOT": str(tmp_path / "models"),
                "MODEL_NAME": "buffalo_l",
                "INSIGHTFACE_LICENSE_ACKNOWLEDGED": False,
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["present"] is True
    assert status["executable"] is True
    assert status["available"] is False
    assert status["reason"] == "insightface_license_not_acknowledged"
    assert "license" in status["last_error"].lower()
