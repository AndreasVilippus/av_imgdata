#!/usr/bin/env python3
"""Local bridge between av-imgdata-worker and the DSM-side worker API store.

This is an integration harness for Phase E before a DSM HTTP router exists. It
uses tools/worker-api-store.py as the API backend and the compiled worker binary
for actual job execution.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_DIR = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def normalize_local_image_path(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    path = Path(value)
    if path.is_absolute():
        return value
    candidates = [
        (PROJECT_DIR / value).resolve(),
        (PROJECT_DIR / "dist" / value).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str((PROJECT_DIR / value).resolve())


def extract_config(config_path: Path) -> Dict[str, Any]:
    config = read_json(config_path)
    config_dir = config_path.parent
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    workspace_root = resolve_path(config_dir, str(config.get("workspace_root") or "../work"))
    token_file = resolve_path(config_dir, str(auth.get("token_file") or "../worker.token"))
    return {
        "raw": config,
        "config_dir": config_dir,
        "worker_id": str(config.get("worker_id") or "worker-01"),
        "workspace_root": workspace_root,
        "token_file": token_file,
        "poll_interval_seconds": int(config.get("poll_interval_seconds") or 2),
    }


def read_token(token_file: Path) -> str:
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("worker token file is empty: %s" % token_file)
    return token


def run_api(api_tool: Path, package_var: Path, args: List[str]) -> Dict[str, Any]:
    cmd = [sys.executable, str(api_tool), "--package-var", str(package_var)] + args
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise RuntimeError("worker-api-store failed: %s\n%s" % (" ".join(cmd), completed.stderr or completed.stdout))
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("worker-api-store returned invalid JSON: %s" % completed.stdout) from exc


def capabilities() -> List[str]:
    return [
        "face_native_detect",
        "face_native_embed",
        "face_native_detect_batch",
        "face_native_embed_batch",
        "face_native_rank_embeddings",
        "face_native_profile_math",
        "warm_processor_worker",
    ]


def build_job_file_payload(claimed_job: Dict[str, Any]) -> Dict[str, Any]:
    payload = claimed_job.get("payload") if isinstance(claimed_job.get("payload"), dict) else {}
    job_payload: Dict[str, Any] = {
        "job_id": str(claimed_job.get("job_id") or ""),
        "type": str(claimed_job.get("type") or ""),
    }
    for key, value in payload.items():
        if key in ("image_path", "local_path"):
            job_payload[key] = normalize_local_image_path(value)
        elif key not in job_payload:
            job_payload[key] = value
    if "asset" not in job_payload and ("image_path" in job_payload or "local_path" in job_payload):
        job_payload["asset"] = {
            "asset_id": str(payload.get("asset_id") or claimed_job.get("job_id") or "asset"),
        }
        if "image_path" in job_payload:
            job_payload["asset"]["image_path"] = job_payload["image_path"]
        if "local_path" in job_payload:
            job_payload["asset"]["local_path"] = job_payload["local_path"]
    return job_payload


def run_worker_once(worker_bin: Path, config_path: Path, job_path: Path, timeout_seconds: int) -> Dict[str, Any]:
    cmd = [str(worker_bin), "once", "--config", str(config_path), "--job", str(job_path)]
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
    output = completed.stdout.strip()
    if not output:
        return {
            "worker_exit_code": completed.returncode,
            "status": "failed",
            "error": {"code": "worker_no_output", "message": completed.stderr.strip()},
        }
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return {
            "worker_exit_code": completed.returncode,
            "status": "failed",
            "raw_output": output,
            "error": {"code": "worker_invalid_json", "message": completed.stderr.strip()},
        }
    result["worker_exit_code"] = completed.returncode
    if completed.stderr.strip():
        result["worker_stderr"] = completed.stderr.strip()
    return result


def extract_error_summary(worker_result: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    error = worker_result.get("error") if isinstance(worker_result.get("error"), dict) else {}
    processor_result = worker_result.get("processor_result") if isinstance(worker_result.get("processor_result"), dict) else {}
    processor_error = processor_result.get("error") if isinstance(processor_result.get("error"), dict) else {}
    artifacts = worker_result.get("artifacts") if isinstance(worker_result.get("artifacts"), dict) else {}
    processor = worker_result.get("processor") if isinstance(worker_result.get("processor"), dict) else {}
    if processor.get("exit_code") is not None:
        summary["processor_exit_code"] = processor.get("exit_code")
    if error.get("code"):
        summary["error_code"] = error.get("code")
        summary["error_message"] = error.get("message", "")
    if processor_error.get("code"):
        summary["processor_error_code"] = processor_error.get("code")
        summary["processor_error_message"] = processor_error.get("message", "")
    if artifacts.get("processor_input"):
        summary["processor_input"] = artifacts.get("processor_input")
    if artifacts.get("processor_result"):
        summary["processor_result"] = artifacts.get("processor_result")
    if artifacts.get("claimed_job"):
        summary["claimed_job"] = artifacts.get("claimed_job")
    return summary


def execute_claimed_job(
    *,
    worker_bin: Path,
    config_path: Path,
    workspace_root: Path,
    claimed_job: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    job_id = str(claimed_job.get("job_id") or "job")
    job_path = workspace_root / "claimed-jobs" / (job_id + ".json")
    write_json(job_path, build_job_file_payload(claimed_job))
    result = run_worker_once(worker_bin, config_path, job_path, timeout_seconds)
    result.setdefault("artifacts", {})
    if isinstance(result["artifacts"], dict):
        result["artifacts"]["claimed_job"] = str(job_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run av-imgdata-worker against local worker-api-store.py")
    parser.add_argument("--worker-bin", required=True, help="Path to av-imgdata-worker executable")
    parser.add_argument("--config", required=True, help="Path to worker-config.json")
    parser.add_argument("--api-tool", default=str(PROJECT_DIR / "tools" / "worker-api-store.py"))
    parser.add_argument("--package-var", default=str(PROJECT_DIR))
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    worker_bin = Path(args.worker_bin)
    config_path = Path(args.config)
    api_tool = Path(args.api_tool)
    package_var = Path(args.package_var)
    config = extract_config(config_path)
    token = read_token(config["token_file"])
    caps = capabilities()

    events = []
    for iteration in range(1, max(1, args.max_iterations) + 1):
        run_api(api_tool, package_var, [
            "heartbeat",
            "--token", token,
            "--worker-id", config["worker_id"],
            "--status", "ready",
        ] + sum((["--capability", item] for item in caps), []))

        claimed = run_api(api_tool, package_var, [
            "claim",
            "--token", token,
            "--worker-id", config["worker_id"],
        ] + sum((["--capability", item] for item in caps), []))

        event: Dict[str, Any] = {"iteration": iteration, "claim_status": claimed.get("status")}
        if claimed.get("status") == "claimed" and isinstance(claimed.get("job"), dict):
            job = claimed["job"]
            worker_result = execute_claimed_job(
                worker_bin=worker_bin,
                config_path=config_path,
                workspace_root=config["workspace_root"],
                claimed_job=job,
                timeout_seconds=args.timeout_seconds,
            )
            event["job_id"] = job.get("job_id")
            event["worker_result_status"] = worker_result.get("processor_execution") or worker_result.get("status")
            if worker_result.get("worker_exit_code") == 0 and worker_result.get("processor_execution") == "completed":
                run_api(api_tool, package_var, [
                    "result",
                    "--token", token,
                    "--worker-id", config["worker_id"],
                    "--job-id", str(job.get("job_id")),
                    "--result", json.dumps(worker_result, ensure_ascii=False),
                ])
                event["reported"] = "result"
            else:
                event.update(extract_error_summary(worker_result))
                run_api(api_tool, package_var, [
                    "fail",
                    "--token", token,
                    "--worker-id", config["worker_id"],
                    "--job-id", str(job.get("job_id")),
                    "--error", json.dumps(worker_result, ensure_ascii=False),
                ])
                event["reported"] = "fail"
        events.append(event)
        if iteration < args.max_iterations:
            time.sleep(config["poll_interval_seconds"])

    print(json.dumps({"status": "ok", "mode": "local-api-runner", "events": events}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
