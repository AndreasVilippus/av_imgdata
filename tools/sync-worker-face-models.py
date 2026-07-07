#!/usr/bin/env python3
import argparse
import json
import os
import shutil
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


def build_store(args: argparse.Namespace) -> FaceModelStoreService:
    package_var = Path(args.package_var) if args.package_var else default_package_var()
    config_path = args.config or default_config_path(package_var)
    config_service = ConfigService(config_path=config_path) if config_path else ConfigService(config_path=str(package_var / "config.json"))
    return FaceModelStoreService(config_service, package_var=package_var)


def sync_models(args: argparse.Namespace) -> Dict[str, Any]:
    store = build_store(args)
    status = store.status(args.model_pack)
    worker_dir = Path(args.worker_dir) if args.worker_dir else default_worker_dir(args.target)
    destination_dir = worker_dir / ".models" / "face" / args.model_pack
    source_dir = Path(status["model_dir"])

    files = ["det_10g.onnx", "w600k_r50.onnx", "manifest.json", "LICENSE_ACK.json"]
    missing_required: List[str] = []
    planned: List[Dict[str, Any]] = []
    copied: List[Dict[str, Any]] = []

    for filename in files:
        source = source_dir / filename
        destination = destination_dir / filename
        required = filename in {"det_10g.onnx", "w600k_r50.onnx"}
        present = source.is_file()
        item = {
            "name": filename,
            "source": str(source),
            "destination": str(destination),
            "required": required,
            "present": present,
        }
        planned.append(item)
        if required and not present:
            missing_required.append(filename)

    if missing_required:
        return {
            "ok": False,
            "error": "required_model_files_missing",
            "missing": missing_required,
            "source_status": status,
            "worker_dir": str(worker_dir),
            "destination_dir": str(destination_dir),
            "planned": planned,
        }

    if not args.dry_run:
        destination_dir.mkdir(parents=True, exist_ok=True)
        for item in planned:
            if not item["present"]:
                continue
            shutil.copy2(item["source"], item["destination"])
            copied.append(item)

    return {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "source_status": status,
        "worker_dir": str(worker_dir),
        "destination_dir": str(destination_dir),
        "planned": planned,
        "copied": copied,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync DSM/dev face model store files into a worker runtime directory.")
    parser.add_argument("--config", default="", help="Optional config.json path. Defaults to package var config, then repo var/config.json.")
    parser.add_argument(
        "--package-var",
        default="",
        help="Optional package var root. Defaults to SYNOPKG_PKGVAR, or the source tree when SYNOPKG_PKGVAR is unset.",
    )
    parser.add_argument("--model-pack", default=FaceModelStoreService.DEFAULT_MODEL_PACK)
    parser.add_argument("--target", default="linux-x86_64", help="Worker dist target used when --worker-dir is not set.")
    parser.add_argument("--worker-dir", default="", help="Worker runtime/dist directory. Defaults to dist/av-imgdata-worker-<target>.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = sync_models(args)
    emit(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
