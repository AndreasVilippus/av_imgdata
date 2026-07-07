#!/usr/bin/env python3
"""DSM-side service foundation for external AV ImgData workers.

The external worker is intentionally not authoritative for package state. This
service owns worker identity, heartbeats, job claims, and result/failure
recording in package-local JSON state. HTTP routing can wrap these methods
without changing the persistence contract.
"""

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class WorkerApiError(RuntimeError):
    def __init__(self, code: str, message: Optional[str] = None):
        self.code = code
        super().__init__(message or code)


class WorkerApiService:
    DEFAULT_CAPABILITIES = (
        "face_native_detect",
        "face_native_embed",
        "face_native_detect_batch",
        "face_native_embed_batch",
        "face_native_rank_embeddings",
        "face_native_profile_math",
        "warm_processor_worker",
    )

    def __init__(
        self,
        *,
        package_var: Optional[Path] = None,
        state_path: Optional[Path] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.package_var = Path(package_var) if package_var else Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
        self.state_path = Path(state_path) if state_path else self.package_var / "worker-api-state.json"
        self._clock = clock if callable(clock) else lambda: datetime.now(timezone.utc)

    def create_token(self, *, token_id: str = "worker-default") -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        state = self._read_state()
        tokens = state.setdefault("tokens", {})
        tokens[str(token_id)] = {
            "token_hash": self._hash_token(token),
            "created_at": self._now_iso(),
            "revoked": False,
        }
        self._write_state(state)
        return {"token_id": str(token_id), "token": token, "created_at": tokens[str(token_id)]["created_at"]}

    def register_worker(
        self,
        *,
        token: str,
        worker_id: str,
        version: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._require_token(token)
        worker_id = self._require_value(worker_id, "worker_id_required")
        state = self._read_state()
        worker = state.setdefault("workers", {}).setdefault(worker_id, {})
        now = self._now_iso()
        worker.update({
            "worker_id": worker_id,
            "version": str(version or "unknown"),
            "capabilities": self._normalize_capabilities(capabilities),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "registered_at": worker.get("registered_at") or now,
            "last_seen_at": now,
            "status": "registered",
        })
        self._write_state(state)
        return {"status": "registered", "worker": worker}

    def heartbeat(
        self,
        *,
        token: str,
        worker_id: str,
        status: str = "ready",
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._require_token(token)
        worker_id = self._require_value(worker_id, "worker_id_required")
        state = self._read_state()
        workers = state.setdefault("workers", {})
        if worker_id not in workers:
            workers[worker_id] = {"worker_id": worker_id, "registered_at": self._now_iso()}
        worker = workers[worker_id]
        worker["last_seen_at"] = self._now_iso()
        worker["status"] = str(status or "ready")
        if capabilities is not None:
            worker["capabilities"] = self._normalize_capabilities(capabilities)
        if isinstance(metadata, dict):
            worker["metadata"] = metadata
        self._write_state(state)
        return {"status": "ok", "worker": worker}

    def enqueue_job(
        self,
        *,
        job_id: str,
        job_type: str,
        payload: Dict[str, Any],
        priority: int = 100,
    ) -> Dict[str, Any]:
        job_id = self._require_value(job_id, "job_id_required")
        job_type = self._require_value(job_type, "job_type_required")
        state = self._read_state()
        jobs = state.setdefault("jobs", {})
        if job_id in jobs and jobs[job_id].get("status") not in ("failed", "completed"):
            raise WorkerApiError("job_already_exists")
        now = self._now_iso()
        jobs[job_id] = {
            "job_id": job_id,
            "type": job_type,
            "payload": payload if isinstance(payload, dict) else {},
            "priority": int(priority),
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "attempts": 0,
        }
        self._write_state(state)
        return {"status": "queued", "job": jobs[job_id]}

    def claim_job(self, *, token: str, worker_id: str, capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        self._require_token(token)
        worker_id = self._require_value(worker_id, "worker_id_required")
        requested = set(self._normalize_capabilities(capabilities))
        state = self._read_state()
        jobs = state.setdefault("jobs", {})
        queued = [job for job in jobs.values() if job.get("status") == "queued"]
        queued.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("created_at", ""))))
        for job in queued:
            if requested and job.get("type") not in requested:
                continue
            now = self._now_iso()
            job["status"] = "claimed"
            job["claimed_by"] = worker_id
            job["claimed_at"] = now
            job["updated_at"] = now
            job["attempts"] = int(job.get("attempts", 0)) + 1
            self._write_state(state)
            return {"status": "claimed", "job": job}
        return {"status": "empty", "job": None}

    def record_result(self, *, token: str, worker_id: str, job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return self._finish_job(token=token, worker_id=worker_id, job_id=job_id, status="completed", payload_key="result", payload=result)

    def record_failure(self, *, token: str, worker_id: str, job_id: str, error: Dict[str, Any]) -> Dict[str, Any]:
        return self._finish_job(token=token, worker_id=worker_id, job_id=job_id, status="failed", payload_key="error", payload=error)

    def status(self) -> Dict[str, Any]:
        state = self._read_state()
        jobs = state.get("jobs", {}) if isinstance(state.get("jobs"), dict) else {}
        workers = state.get("workers", {}) if isinstance(state.get("workers"), dict) else {}
        by_status: Dict[str, int] = {}
        for job in jobs.values():
            value = str(job.get("status") or "unknown")
            by_status[value] = by_status.get(value, 0) + 1
        return {"workers": len(workers), "jobs": {"total": len(jobs), "by_status": by_status}}

    def _finish_job(
        self,
        *,
        token: str,
        worker_id: str,
        job_id: str,
        status: str,
        payload_key: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._require_token(token)
        worker_id = self._require_value(worker_id, "worker_id_required")
        job_id = self._require_value(job_id, "job_id_required")
        state = self._read_state()
        jobs = state.setdefault("jobs", {})
        if job_id not in jobs:
            raise WorkerApiError("job_not_found")
        job = jobs[job_id]
        if job.get("claimed_by") and job.get("claimed_by") != worker_id:
            raise WorkerApiError("job_claimed_by_other_worker")
        now = self._now_iso()
        job["status"] = status
        job[payload_key] = payload if isinstance(payload, dict) else {}
        job["finished_at"] = now
        job["updated_at"] = now
        self._write_state(state)
        return {"status": status, "job": job}

    def _require_token(self, token: str) -> str:
        token = self._require_value(token, "token_required")
        state = self._read_state()
        tokens = state.get("tokens", {}) if isinstance(state.get("tokens"), dict) else {}
        digest = self._hash_token(token)
        for entry in tokens.values():
            if entry.get("token_hash") == digest and not entry.get("revoked"):
                return token
        raise WorkerApiError("unauthorized")

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    @staticmethod
    def _require_value(value: Any, code: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise WorkerApiError(code)
        return text

    def _normalize_capabilities(self, capabilities: Optional[List[str]]) -> List[str]:
        if not capabilities:
            return list(self.DEFAULT_CAPABILITIES)
        seen = set()
        result = []
        for item in capabilities:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def _now_iso(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_path.is_file():
            return {"schema_version": 1, "tokens": {}, "workers": {}, "jobs": {}}
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except Exception:
            raise WorkerApiError("state_read_failed")
        if not isinstance(state, dict):
            raise WorkerApiError("state_invalid")
        state.setdefault("schema_version", 1)
        state.setdefault("tokens", {})
        state.setdefault("workers", {})
        state.setdefault("jobs", {})
        return state

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=self.state_path.name + ".", suffix=".tmp", dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, str(self.state_path))
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
