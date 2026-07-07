#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.config_service import ConfigService  # noqa: E402
from services.face_model_store_service import FaceModelStoreService  # noqa: E402


def emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def default_package_var() -> Path:
    configured = str(os.getenv("SYNOPKG_PKGVAR") or "").strip()
    if configured:
        return Path(configured)
    return PROJECT_DIR


def default_config_path(package_var: Path) -> str:
    configured = str(os.getenv("AV_IMGDATA_CONFIG") or "").strip()
    if configured:
        return configured
    runtime_config = package_var / "config.json"
    if runtime_config.is_file():
        return str(runtime_config)
    source_config = PROJECT_DIR / "var" / "config.json"
    if source_config.is_file():
        return str(source_config)
    return ""


def default_worker_dir(target: str) -> Path:
    return PROJECT_DIR / "dist" / f"av-imgdata-worker-{target}"


def default_model_root(package_var: Path) -> Path:
    return package_var / ".models" / "face"


def build_store(args: argparse.Namespace) -> FaceModelStoreService:
    package_var = Path(args.package_var) if args.package_var else default_package_var()
    if args.use_config_model_root:
        config_path = args.config or default_config_path(package_var)
        config_service = ConfigService(config_path=config_path) if config_path else ConfigService(config_path=str(package_var / "config.json"))
    else:
        config_service = ConfigService(config_path=str(package_var / "config.json"))
    return FaceModelStoreService(config_service, package_var=package_var)


def read_worker_config(worker_dir: Path) -> Dict[str, Any]:
    config_path = worker_dir / "config" / "worker-config.example.json"
    if not config_path.is_file():
        return {}
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def write_worker_config(worker_dir: Path, config: Dict[str, Any]) -> None:
    config_path = worker_dir / "config" / "worker-config.example.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def configure_worker(args: argparse.Namespace) -> Dict[str, Any]:
    package_var = Path(args.package_var) if args.package_var else default_package_var()
    store = build_store(args)
    status = store.status(args.model_pack)
    worker_dir = Path(args.worker_dir) if args.worker_dir else default_worker_dir(args.target)
    config_path = worker_dir / "config" / "worker-config.example.json"
    model_root = args.model_root or str(default_model_root(package_var))
    if args.use_config_model_root and not args.model_root:
        model_root = str(Path(status["root"]))
    if args.relative:
        try:
            model_root = os.path.relpath(str(Path(model_root).resolve()), str(config_path.parent.resolve()))
        except Exception:
            pass

    config = read_worker_config(worker_dir)
    processors = config.setdefault("processors", {})
    if not isinstance(processors, dict):
        processors = {}
        config["processors"] = processors
    face = processors.setdefault("face", {})
    if not isinstance(face, dict):
        face = {}
        processors["face"] = face
    old_model_root = face.get("model_root")
    face["model_root"] = model_root
    face["model_name"] = args.model_pack

    if not args.dry_run:
        write_worker_config(worker_dir, config)

    expected_files: List[Dict[str, Any]] = []
    source_dir = Path(model_root)
    if not Path(model_root).is_absolute():
        source_dir = (config_path.parent / model_root)
    source_dir = source_dir / args.model_pack
    for filename in ("det_10g.onnx", "w600k_r50.onnx", "manifest.json", "LICENSE_ACK.json"):
        source = source_dir / filename
        expected_files.append({"name": filename, "path": str(source), "present": source.is_file()})

    return {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "mode": "configure_only_no_model_copy",
        "worker_dir": str(worker_dir),
        "config_path": str(config_path),
        "old_model_root": old_model_root,
        "new_model_root": model_root,
        "model_pack": args.model_pack,
        "package_var": str(package_var),
        "use_config_model_root": bool(args.use_config_model_root),
        "source_status": status,
        "expected_files": expected_files,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure a worker runtime to use the DSM/dev face model store without copying model files.")
    parser.add_argument("--config", default="", help="Optional config.json path. Used only with --use-config-model-root.")
    parser.add_argument(
        "--package-var",
        default="",
        help="Optional package/root directory. Defaults to SYNOPKG_PKGVAR, or the source tree when SYNOPKG_PKGVAR is unset.",
    )
    parser.add_argument("--model-pack", default=FaceModelStoreService.DEFAULT_MODEL_PACK)
    parser.add_argument("--target", default="linux-x86_64", help="Worker dist target used when --worker-dir is not set.")
    parser.add_argument("--worker-dir", default="", help="Worker runtime/dist directory. Defaults to dist/av-imgdata-worker-<target>.")
    parser.add_argument("--model-root", default="", help="Explicit model_root to write into worker config. Defaults to <package/root>/.models/face.")
    parser.add_argument("--use-config-model-root", action="store_true", help="Use native_processors.FACE_PROCESSOR.MODEL_ROOT from config as model_root.")
    parser.add_argument("--relative", action="store_true", help="Write model_root relative to the worker config directory when possible.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = configure_worker(args)
    emit(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
