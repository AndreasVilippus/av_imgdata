import json
import os
from pathlib import Path

from services.config_service import ConfigService
from services.native_face_processor_service import NativeFaceProcessorService


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
    print("probe accepted by python_bridge")
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
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()
    assert status["available"] is True
    assert status["reason"] == "ready"
    assert status["backend"] == "native"
    assert status["inference_available"] is True
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


def test_native_face_processor_status_reports_python_bridge_backend(tmp_path):
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
            },
        },
    })
    service = NativeFaceProcessorService(config, package_root=tmp_path)

    status = service.status()

    assert status["available"] is True
    assert status["reason"] == "ready"
    assert status["backend"] == "python_bridge"
    assert status["inference_available"] is True


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
    assert status["reason"] == "skeleton_no_inference"
    assert "does not run inference" in status["last_error"]


def test_native_face_processor_defaults_to_required_and_reports_missing_binary(tmp_path):
    service = NativeFaceProcessorService(ConfigService(str(tmp_path / "config.json")), package_root=tmp_path)

    status = service.status()

    assert status["enabled"] is True
    assert status["available"] is False
    assert status["reason"] == "binary_missing"
