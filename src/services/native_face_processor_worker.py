#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector
from services.face_embedder import InsightFaceEmbedder


VERSION = "0.2.0-python-bridge"
PROCESSOR_NAME = "av-imgdata-face-processor"
BACKEND = "python_bridge"


def _read_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _processor_payload() -> Dict[str, str]:
    return {"name": PROCESSOR_NAME, "version": VERSION, "backend": BACKEND}


def _error_payload(job_id: str, job_type: str, code: str, message: str) -> Dict[str, Any]:
    return {
        "contract_version": "1.0",
        "job_id": job_id,
        "type": job_type,
        "status": "failed",
        "processor": _processor_payload(),
        "result": {"faces": []},
        "error": {"code": code, "message": message},
    }


def _success_payload(job_id: str, job_type: str, faces: List[Dict[str, Any]], duration_ms: float) -> Dict[str, Any]:
    return {
        "contract_version": "1.0",
        "job_id": job_id,
        "type": job_type,
        "status": "completed",
        "processor": _processor_payload(),
        "result": {"faces": faces},
        "diagnostics": {"duration_ms": round(duration_ms, 2), "faces_count": len(faces)},
    }


def _options(payload: Dict[str, Any]) -> Dict[str, Any]:
    options = payload.get("options")
    return options if isinstance(options, dict) else {}


def _det_size(value: Any) -> Tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return (max(1, int(value[0])), max(1, int(value[1])))
        except Exception:
            pass
    return (640, 640)


def _common_kwargs(options: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model_name": str(options.get("model_name") or "").strip(),
        "model_root": Path(str(options.get("model_root"))) if str(options.get("model_root") or "").strip() else None,
        "det_size": _det_size(options.get("det_size")),
        "det_thresh": float(options.get("min_confidence", 0.5) or 0.5),
        "max_num": int(options.get("max_faces", 0) or 0),
    }


def _image_path(payload: Dict[str, Any]) -> Path:
    input_payload = payload.get("input")
    if not isinstance(input_payload, dict):
        raise ValueError("input object is missing")
    image_path = str(input_payload.get("image_path") or "").strip()
    if not image_path:
        raise ValueError("input.image_path is missing")
    return Path(image_path)


def _run_faces(command: str, input_path: Path, output_path: Path) -> int:
    started_at = time.monotonic()
    payload = _read_json(input_path)
    job_id = str(payload.get("job_id") or "local")
    job_type = str(payload.get("type") or f"face_native_{command}")
    try:
        options = _options(payload)
        kwargs = _common_kwargs(options)
        if command == "embed":
            faces = InsightFaceEmbedder(**kwargs).detect_and_embed(_image_path(payload))
        else:
            faces = InsightFaceDetector(**kwargs).detect(_image_path(payload))
    except Exception as exc:
        _write_json(output_path, _error_payload(job_id, job_type, type(exc).__name__, str(exc)))
        return 1
    _write_json(output_path, _success_payload(job_id, job_type, faces, (time.monotonic() - started_at) * 1000))
    return 0


def _probe(model_root: Optional[str], model_name: Optional[str]) -> int:
    try:
        import cv2  # noqa: F401
        import insightface  # noqa: F401

        detector = InsightFaceDetector(model_name=model_name or "", model_root=Path(model_root) if model_root else None)
        detector._validate_model_files()
    except FaceDetectorUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    print(f"probe accepted by {BACKEND} for {model_root or ''}/{model_name or ''}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=PROCESSOR_NAME)
    parser.add_argument("command", choices=["version", "probe", "detect", "embed", "self-test"])
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--workdir")
    parser.add_argument("--model-root")
    parser.add_argument("--model-name")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"{PROCESSOR_NAME} {VERSION}")
        return 0
    if args.command == "probe":
        return _probe(args.model_root, args.model_name)
    if args.command == "self-test":
        return _probe(args.model_root, args.model_name)
    if not args.input or not args.output:
        print("--input and --output are required", file=sys.stderr)
        return 2
    return _run_faces(args.command, Path(args.input), Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
