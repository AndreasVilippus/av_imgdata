#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from services.config_service import ConfigService
from services.worker_api_service import WorkerApiError, WorkerApiService


PACKAGE_NAME = "AV_ImgData"
DSM_PACKAGE_VAR = Path("/var/packages") / PACKAGE_NAME / "var"


def default_package_var() -> Path:
    configured = os.getenv("SYNOPKG_PKGVAR", "").strip()
    if configured:
        return Path(configured)
    return PROJECT_DIR


def default_state_path() -> str:
    return os.getenv("AV_IMGDATA_WORKER_API_STATE_PATH", "").strip()


def print_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def load_json_arg(value: str):
    if not value:
        return {}
    path = Path(value)
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(value)


def resolve_state_path(args):
    configured = str(args.state_path or "").strip()
    package_var = Path(args.package_var)
    if not configured:
        return package_var / "worker-api-state.json"
    path = Path(configured)
    if path.is_absolute():
        return path
    return package_var / path


def repair_runtime_file_permissions(args):
    """Keep root-run admin commands compatible with the DSM package user.

    DSM administrators usually invoke this helper via sudo. Without repair, JSON
    runtime files can become root-owned while the FastAPI service runs as the
    package user. Use the package var directory owner as the authority and make
    known runtime files readable/writable by that owner only.
    """
    if os.name != "posix":
        return

    package_var = Path(args.package_var)
    try:
        owner = package_var.stat()
    except OSError:
        return

    paths = [package_var / "config.json", resolve_state_path(args)]
    for path in paths:
        try:
            if not path.exists():
                continue
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                os.chown(str(path), owner.st_uid, owner.st_gid)
            os.chmod(str(path), 0o600)
        except PermissionError:
            continue
        except OSError:
            continue


def build_service(args):
    return WorkerApiService(package_var=Path(args.package_var), state_path=resolve_state_path(args))


def build_config_service(args):
    return ConfigService(str(Path(args.package_var) / "config.json"))


def configure_worker_api(args, *, enabled: bool):
    service = build_config_service(args)
    config = service.readMergedConfig()
    worker_api = config.setdefault("worker_api", {})
    worker_api["ENABLED"] = bool(enabled)
    if enabled:
        worker_api["STATE_PATH"] = str(args.config_state_path or "worker-api-state.json")
    ok = service.writeConfig(config)
    if not ok:
        return {"status": "error", "code": "config_write_failed", "path": str(Path(args.package_var) / "config.json")}
    repair_runtime_file_permissions(args)
    return {
        "status": "ok",
        "worker_api": service.readMergedConfig().get("worker_api", {}),
        "config_path": str(Path(args.package_var) / "config.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage AV ImgData DSM-side external worker API state")
    parser.add_argument("--package-var", default=str(default_package_var()), help="Package var/root directory")
    parser.add_argument("--state-path", default=default_state_path(), help="Explicit state JSON path")
    sub = parser.add_subparsers(dest="command", required=True)

    enable_api = sub.add_parser("enable-api", help="Enable /worker-api in package config")
    enable_api.add_argument("--config-state-path", default="worker-api-state.json", help="State path stored in config; relative paths are resolved below package var")

    sub.add_parser("disable-api", help="Disable /worker-api in package config")
    sub.add_parser("api-config", help="Show worker_api package config")

    create_token = sub.add_parser("create-token")
    create_token.add_argument("--token-id", default="worker-default")

    register = sub.add_parser("register")
    register.add_argument("--token", required=True)
    register.add_argument("--worker-id", required=True)
    register.add_argument("--version", default="unknown")
    register.add_argument("--capability", action="append", default=[])
    register.add_argument("--metadata", default="{}")

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--token", required=True)
    heartbeat.add_argument("--worker-id", required=True)
    heartbeat.add_argument("--status", default="ready")
    heartbeat.add_argument("--capability", action="append", default=[])
    heartbeat.add_argument("--metadata", default="{}")

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--job-id", required=True)
    enqueue.add_argument("--type", required=True)
    enqueue.add_argument("--payload", default="{}", help="JSON string or JSON file path")
    enqueue.add_argument("--priority", type=int, default=100)

    claim = sub.add_parser("claim")
    claim.add_argument("--token", required=True)
    claim.add_argument("--worker-id", required=True)
    claim.add_argument("--capability", action="append", default=[])

    result = sub.add_parser("result")
    result.add_argument("--token", required=True)
    result.add_argument("--worker-id", required=True)
    result.add_argument("--job-id", required=True)
    result.add_argument("--result", default="{}", help="JSON string or JSON file path")

    fail = sub.add_parser("fail")
    fail.add_argument("--token", required=True)
    fail.add_argument("--worker-id", required=True)
    fail.add_argument("--job-id", required=True)
    fail.add_argument("--error", default="{}", help="JSON string or JSON file path")

    sub.add_parser("status")

    args = parser.parse_args()
    try:
        if args.command == "enable-api":
            print_json(configure_worker_api(args, enabled=True))
        elif args.command == "disable-api":
            print_json(configure_worker_api(args, enabled=False))
        elif args.command == "api-config":
            print_json({
                "status": "ok",
                "config_path": str(Path(args.package_var) / "config.json"),
                "worker_api": build_config_service(args).readMergedConfig().get("worker_api", {}),
            })
        else:
            service = build_service(args)
            if args.command == "create-token":
                payload = service.create_token(token_id=args.token_id)
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "register":
                payload = service.register_worker(
                    token=args.token,
                    worker_id=args.worker_id,
                    version=args.version,
                    capabilities=args.capability or None,
                    metadata=load_json_arg(args.metadata),
                )
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "heartbeat":
                payload = service.heartbeat(
                    token=args.token,
                    worker_id=args.worker_id,
                    status=args.status,
                    capabilities=args.capability or None,
                    metadata=load_json_arg(args.metadata),
                )
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "enqueue":
                payload = service.enqueue_job(job_id=args.job_id, job_type=args.type, payload=load_json_arg(args.payload), priority=args.priority)
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "claim":
                payload = service.claim_job(token=args.token, worker_id=args.worker_id, capabilities=args.capability or None)
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "result":
                payload = service.record_result(token=args.token, worker_id=args.worker_id, job_id=args.job_id, result=load_json_arg(args.result))
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "fail":
                payload = service.record_failure(token=args.token, worker_id=args.worker_id, job_id=args.job_id, error=load_json_arg(args.error))
                repair_runtime_file_permissions(args)
                print_json(payload)
            elif args.command == "status":
                print_json(service.status())
        return 0
    except WorkerApiError as exc:
        print_json({"status": "error", "code": exc.code, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())