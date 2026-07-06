#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.config_service import ConfigService  # noqa: E402
from services.face_model_store_service import FaceModelStoreError, FaceModelStoreService  # noqa: E402


def emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def service(args: argparse.Namespace) -> FaceModelStoreService:
    config_service = ConfigService(config_path=args.config) if args.config else ConfigService()
    package_var = Path(args.package_var) if args.package_var else None
    return FaceModelStoreService(config_service, package_var=package_var)


def cmd_status(args: argparse.Namespace) -> int:
    return emit(service(args).status(args.model_pack))


def cmd_acknowledge(args: argparse.Namespace) -> int:
    store = service(args)
    ack = store.acknowledge_usage(
        model_pack=args.model_pack,
        accepted_by=args.accepted_by,
        package_version=args.package_version,
        source=args.source,
    )
    return emit({"acknowledged": True, "ack": ack, "status": store.status(args.model_pack)})


def cmd_import(args: argparse.Namespace) -> int:
    store = service(args)
    try:
        result = store.import_model_files(Path(args.source_dir), model_pack=args.model_pack, source=args.source)
    except FaceModelStoreError as exc:
        return emit({"ok": False, "error": str(exc), "status": store.status(args.model_pack)}) or 1
    return emit({"ok": True, "status": result})


def cmd_clear_ack(args: argparse.Namespace) -> int:
    store = service(args)
    cleared = store.clear_acknowledgement(args.model_pack)
    return emit({"cleared": bool(cleared), "status": store.status(args.model_pack)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage AV ImgData DSM face model store metadata.")
    parser.add_argument("--config", default="", help="Optional config.json path. Defaults to SYNOPKG_PKGVAR/config.json.")
    parser.add_argument("--package-var", default=os.getenv("SYNOPKG_PKGVAR", ""), help="Optional package var root. Defaults to SYNOPKG_PKGVAR.")
    parser.add_argument("--model-pack", default=FaceModelStoreService.DEFAULT_MODEL_PACK)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    ack = sub.add_parser("acknowledge")
    ack.add_argument("--accepted-by", default="admin")
    ack.add_argument("--package-version", default=os.getenv("SYNOPKG_PKGVER", "unknown"))
    ack.add_argument("--source", default="manual")
    ack.set_defaults(func=cmd_acknowledge)

    imp = sub.add_parser("import")
    imp.add_argument("--source-dir", required=True, help="Directory containing det_10g.onnx and w600k_r50.onnx.")
    imp.add_argument("--source", default="manual")
    imp.set_defaults(func=cmd_import)

    sub.add_parser("clear-ack").set_defaults(func=cmd_clear_ack)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
