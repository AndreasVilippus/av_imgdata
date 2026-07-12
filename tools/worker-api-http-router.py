#!/usr/bin/env python3
"""Local/DSM-compatible HTTP router for the AV ImgData worker API."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.worker_api_composition_service import WorkerApiCompositionService  # noqa: E402
from services.worker_api_endpoints import handle_worker_api_request  # noqa: E402


ROUTE_PREFIX = "/worker-api"
VALID_POST_ACTIONS = {"register", "heartbeat", "claim", "result", "fail"}


def parse_headers(handler: BaseHTTPRequestHandler) -> Dict[str, str]:
    return {key: value for key, value in handler.headers.items()}


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json_body") from exc
    if not isinstance(parsed, dict):
        raise ValueError("json_body_must_be_object")
    return parsed


def action_from_path(path: str) -> str:
    clean = path.split("?", 1)[0].rstrip("/")
    if clean == ROUTE_PREFIX:
        return ""
    prefix = ROUTE_PREFIX + "/"
    if not clean.startswith(prefix):
        return ""
    action = clean[len(prefix):]
    return "" if "/" in action else action


class WorkerApiHttpHandler(BaseHTTPRequestHandler):
    server_version = "AVImgDataWorkerApi/1.0"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        action = action_from_path(self.path)
        if action in ("", "status"):
            composition = self.server.composition  # type: ignore[attr-defined]
            self._send_json(200, {"status": "ok", "service": composition.worker_api.status()})
            return
        self._send_json(404, {"status": "error", "code": "unknown_worker_api_route"})

    def do_POST(self) -> None:  # noqa: N802
        action = action_from_path(self.path)
        if action not in VALID_POST_ACTIONS:
            self._send_json(404, {"status": "error", "code": "unknown_worker_api_route"})
            return
        try:
            body = read_json_body(self)
        except ValueError as exc:
            self._send_json(400, {"status": "error", "code": str(exc)})
            return
        composition = self.server.composition  # type: ignore[attr-defined]
        status, payload = handle_worker_api_request(
            action,
            headers=parse_headers(self),
            body=body,
            service=composition.worker_api,
        )
        self._send_json(status, payload)

    def log_message(self, fmt: str, *args: object) -> None:
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        super().log_message(fmt, *args)


class WorkerApiHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: Tuple[str, int],
        package_var: Path,
        state_path: Optional[Path],
        quiet: bool,
    ):
        super().__init__(server_address, WorkerApiHttpHandler)
        self.composition = WorkerApiCompositionService(
            package_var=package_var,
            state_path=state_path,
        )
        self.quiet = quiet


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the AV ImgData worker API over local HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--package-var", default=str(PROJECT_DIR))
    parser.add_argument("--state-path", default="")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    package_var = Path(args.package_var).resolve()
    state_path = Path(args.state_path) if args.state_path else None
    server = WorkerApiHttpServer((args.host, args.port), package_var, state_path, args.quiet)
    print(json.dumps({
        "status": "listening",
        "base_url": f"http://{args.host}:{args.port}{ROUTE_PREFIX}",
        "package_var": str(server.composition.package_var),
        "state_path": str(server.composition.state_store.state_path),
    }, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
