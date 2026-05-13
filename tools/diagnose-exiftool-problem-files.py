#!/usr/bin/env python3
"""Measure ExifTool behavior for slow metadata problem files.

The script is intentionally standalone enough to run on the Synology host where
the original /volume1/photo files are available. It compares the native JPEG
header reader, normal ExifTool subprocess calls and ExifTool's stay_open mode.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_file_handler():
    try:
        from handler.file_handler import FileHandler

        return FileHandler
    except Exception as exc:
        return exc


def _now() -> float:
    return time.monotonic()


def _preview(value: Optional[str], limit: int = 1200) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"... <truncated {len(text) - limit} chars>"


def _file_stat(path: str) -> Dict[str, Any]:
    item = Path(path)
    info: Dict[str, Any] = {
        "path": path,
        "exists": item.exists(),
        "is_file": item.is_file(),
    }
    if not item.exists():
        return info
    stat = item.stat()
    info.update(
        {
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "mode": oct(stat.st_mode & 0o777),
        }
    )
    return info


def _native_jpeg_context(path: str) -> Dict[str, Any]:
    handler_or_error = _load_file_handler()
    if isinstance(handler_or_error, Exception):
        return {"success": False, "error": repr(handler_or_error)}
    start = _now()
    try:
        context = handler_or_error.readJpegContext(path)
        return {
            "success": True,
            "duration_seconds": round(_now() - start, 6),
            "context": context,
        }
    except Exception as exc:
        return {
            "success": False,
            "duration_seconds": round(_now() - start, 6),
            "error": repr(exc),
        }


def _run_exiftool(
    exiftool: str,
    args: List[str],
    path: Optional[str],
    timeout: float,
) -> Dict[str, Any]:
    command = [exiftool, *args]
    if path:
        command.append(path)
    start = _now()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1.0, timeout),
        )
        return {
            "command": command,
            "duration_seconds": round(_now() - start, 6),
            "timeout": False,
            "returncode": result.returncode,
            "stdout_preview": _preview(result.stdout),
            "stderr_preview": _preview(result.stderr),
            "stdout_length": len(result.stdout or ""),
            "stderr_length": len(result.stderr or ""),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "duration_seconds": round(_now() - start, 6),
            "timeout": True,
            "returncode": 124,
            "stdout_preview": _preview(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr_preview": _preview(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
    except Exception as exc:
        return {
            "command": command,
            "duration_seconds": round(_now() - start, 6),
            "timeout": False,
            "returncode": 126,
            "error": repr(exc),
        }


def _drain_stream(stream, target: List[bytes]) -> None:
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            target.append(chunk)
    except Exception:
        return


def _split_ready_response(buffer: bytes):
    lines = buffer.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == b"{ready}":
            return b"".join(lines[:index]), b"".join(lines[index + 1 :])
    return None, buffer


def _read_stay_open_response(process: subprocess.Popen, timeout: float) -> Dict[str, Any]:
    if process.stdout is None:
        return {"timeout": False, "error": "stdout pipe unavailable", "stdout": ""}

    output_buffer = b""
    deadline = _now() + max(1.0, timeout)
    stdout_fd = process.stdout.fileno()
    while True:
        response, output_buffer = _split_ready_response(output_buffer)
        if response is not None:
            return {
                "timeout": False,
                "stdout": response.decode("utf-8", errors="replace"),
            }
        remaining = deadline - _now()
        if remaining <= 0:
            return {
                "timeout": True,
                "stdout": output_buffer.decode("utf-8", errors="replace"),
            }
        ready, _, _ = select.select([stdout_fd], [], [], remaining)
        if not ready:
            return {
                "timeout": True,
                "stdout": output_buffer.decode("utf-8", errors="replace"),
            }
        chunk = os.read(stdout_fd, 8192)
        if not chunk:
            return {
                "timeout": False,
                "error": "process ended",
                "stdout": output_buffer.decode("utf-8", errors="replace"),
            }
        output_buffer += chunk


def _run_stay_open_sequence(
    exiftool: str,
    requests: Iterable[Dict[str, Any]],
    timeout: float,
) -> Dict[str, Any]:
    stderr_chunks: List[bytes] = []
    start = _now()
    try:
        process = subprocess.Popen(
            [exiftool, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except Exception as exc:
        return {"success": False, "error": repr(exc)}

    stderr_thread = None
    if process.stderr is not None:
        stderr_thread = threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_chunks),
            daemon=True,
        )
        stderr_thread.start()

    results: List[Dict[str, Any]] = []
    try:
        for request in requests:
            req_start = _now()
            args = [str(arg) for arg in request["args"]]
            path = str(request["path"])
            if process.stdin is None:
                results.append({"name": request["name"], "error": "stdin pipe unavailable"})
                break
            process.stdin.write(("\n".join([*args, path]) + "\n-execute\n").encode("utf-8"))
            process.stdin.flush()
            response = _read_stay_open_response(process, timeout)
            entry = {
                "name": request["name"],
                "args": args,
                "path": path,
                "duration_seconds": round(_now() - req_start, 6),
                "timeout": bool(response.get("timeout")),
                "stdout_preview": _preview(response.get("stdout")),
                "stdout_length": len(response.get("stdout") or ""),
            }
            if response.get("error"):
                entry["error"] = response["error"]
            results.append(entry)
            if response.get("timeout") or response.get("error"):
                break
    finally:
        try:
            if process.stdin is not None and process.poll() is None:
                process.stdin.write(b"-stay_open\nFalse\n")
                process.stdin.flush()
        except Exception:
            pass
        try:
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        if stderr_thread is not None:
            stderr_thread.join(timeout=0.2)

    return {
        "success": True,
        "duration_seconds": round(_now() - start, 6),
        "returncode": process.returncode,
        "stderr_preview": _preview(b"".join(stderr_chunks).decode("utf-8", errors="replace")),
        "stderr_length": len(b"".join(stderr_chunks)),
        "requests": results,
    }


def _progress_payload(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    url = request.get("url") if isinstance(request.get("url"), str) else ""
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    content = response.get("content") if isinstance(response.get("content"), dict) else {}
    text = content.get("text")
    if not isinstance(text, str):
        return None
    if "file_analysis_progress" not in url and "analysis_stage" not in text:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _extract_paths_from_har(har_path: str, top: int) -> List[str]:
    data = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = data.get("log", {}).get("entries", [])
    samples: List[Dict[str, Any]] = []
    for entry in entries:
        payload = _progress_payload(entry)
        if not payload:
            continue
        if payload.get("analysis_stage") != "exiftool_context_fallback":
            continue
        started = entry.get("startedDateTime")
        current = payload.get("current_path") or payload.get("current_file") or payload.get("currentFile")
        if not isinstance(started, str) or not isinstance(current, str):
            continue
        samples.append({"started": started, "path": current})

    scored: Dict[str, int] = {}
    for sample in samples:
        scored[sample["path"]] = scored.get(sample["path"], 0) + 1
    ordered = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    return [path for path, _count in ordered[:top]]


def _diagnose_file(exiftool: str, path: str, timeout: float) -> Dict[str, Any]:
    stat = _file_stat(path)
    result: Dict[str, Any] = {"file": stat}
    if not stat.get("exists") or not stat.get("is_file"):
        result["skipped"] = "file is not available on this host"
        return result

    result["native_jpeg_context"] = _native_jpeg_context(path)
    result["subprocess"] = {
        "metadata_context_with_xmp": _run_exiftool(
            exiftool,
            ["-j", "-n", "-XMP", "-ImageWidth", "-ImageHeight", "-Orientation"],
            path,
            timeout,
        ),
        "metadata_context_no_xmp": _run_exiftool(
            exiftool,
            ["-j", "-n", "-ImageWidth", "-ImageHeight", "-Orientation"],
            path,
            timeout,
        ),
        "metadata_context_no_xmp_fast2": _run_exiftool(
            exiftool,
            ["-fast2", "-j", "-n", "-ImageWidth", "-ImageHeight", "-Orientation"],
            path,
            timeout,
        ),
        "dimensions": _run_exiftool(
            exiftool,
            ["-s3", "-ImageWidth", "-ImageHeight"],
            path,
            timeout,
        ),
        "orientation": _run_exiftool(
            exiftool,
            ["-s3", "-n", "-Orientation"],
            path,
            timeout,
        ),
        "validate": _run_exiftool(
            exiftool,
            ["-validate", "-warning", "-error"],
            path,
            timeout,
        ),
    }
    result["stay_open"] = _run_stay_open_sequence(
        exiftool,
        [
            {
                "name": "metadata_context_no_xmp",
                "args": ["-j", "-n", "-ImageWidth", "-ImageHeight", "-Orientation"],
                "path": path,
            },
            {
                "name": "dimensions",
                "args": ["-s3", "-ImageWidth", "-ImageHeight"],
                "path": path,
            },
            {
                "name": "orientation",
                "args": ["-s3", "-n", "-Orientation"],
                "path": path,
            },
        ],
        timeout,
    )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose slow ExifTool reads for HAR problem files.",
    )
    parser.add_argument("paths", nargs="*", help="Image paths to diagnose.")
    parser.add_argument("--har", help="Extract slow exiftool_context_fallback paths from a HAR file.")
    parser.add_argument("--top", type=int, default=20, help="Number of HAR paths to inspect.")
    parser.add_argument("--timeout", type=float, default=35.0, help="Per ExifTool request timeout.")
    parser.add_argument("--exiftool", default="exiftool", help="ExifTool executable path.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    paths = list(args.paths)
    if args.har:
        paths.extend(_extract_paths_from_har(args.har, max(1, args.top)))

    deduplicated: List[str] = []
    seen = set()
    for path in paths:
        if path not in seen:
            deduplicated.append(path)
            seen.add(path)

    exiftool_version = _run_exiftool(args.exiftool, ["-ver"], "", args.timeout)
    report = {
        "tool": "diagnose-exiftool-problem-files",
        "cwd": os.getcwd(),
        "exiftool": args.exiftool,
        "timeout_seconds": args.timeout,
        "exiftool_version": exiftool_version,
        "path_count": len(deduplicated),
        "results": [_diagnose_file(args.exiftool, path, args.timeout) for path in deduplicated],
    }
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
