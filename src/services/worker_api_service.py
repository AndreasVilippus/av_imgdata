#!/usr/bin/env python3
"""DSM-side service foundation for external AV ImgData workers."""

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.config_service import ConfigService
from services.worker_runtime_service import (
    WorkerApiError,
    WorkerCredentialService,
    WorkerProtocol,
    WorkerStateStore,
    iso_time,
    utc_now,
)


class WorkerApiService:
    DEFAULT_CAPABILITIES = WorkerProtocol.CAPABILITIES

    def __init__(
        self,
        *,
        package_var: Optional[Path] = None,
        state_path: Optional[Path] = None,
        clock: Optional[Callable[[], datetime]] = None,
        config_service: Optional[Any] = None,
        state_store: Optional[WorkerStateStore] = None,
    ):
        self.config_service = config_service or ConfigService(
            str(Path(package_var) / "config.json") if package_var is not None else None
        )
        self.store = state_store or WorkerStateStore(
            package_var=package_var,
            state_path=state_path,
            config_service=self.config_service,
        )
        self.package_var = self.store.package_var
        self.state_path = self.store.state_path
        self.credentials = WorkerCredentialService(self.store)
        self._clock = clock

    def create_token(self, *, token_id: str = "worker-default") -> Dict[str, Any]:
        return self.credentials.issue_token(
            token_id=token_id,
            scopes=WorkerProtocol.DEFAULT_TOKEN_SCOPES,
            issued_via="admin",
            created_at=self._now_iso(),
        )

    def register_worker(
        self,
        *,
        token: str,
        worker_id: str,
        version: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.credentials.authenticate(token=token, worker_id=worker_id, scope=WorkerProtocol.TOKEN_SCOPE_WORKER_API)
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")
        worker = self._upsert_worker(
            worker_id=worker_id,
            version=str(version or "unknown"),
            status="registered",
            capabilities=capabilities,
            metadata=metadata,
            require_existing=False,
        )
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
        self.credentials.authenticate(token=token, worker_id=worker_id, scope=WorkerProtocol.TOKEN_SCOPE_WORKER_API)
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")
        worker = self._upsert_worker(
            worker_id=worker_id,
            status=str(status or "ready"),
            capabilities=capabilities,
            metadata=metadata,
            require_existing=True,
        )
        return {"status": "ok", "worker": worker}

    def enqueue_job(self, *, job_id: str, job_type: str, payload: Dict[str, Any], priority: int = 100) -> Dict[str, Any]:
        job_id = self.credentials.require_value(job_id, "job_id_required")
        job_type = self.credentials.require_value(job_type, "job_type_required")
        if job_type not in WorkerProtocol.supported_job_types(WorkerProtocol.CAPABILITIES):
            raise WorkerApiError("job_type_unsupported")

        def mutate(state):
            jobs = state["jobs"]
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
            return jobs[job_id]

        job = self.store.update(mutate)
        return {"status": "queued", "job": job}

    def claim_job(self, *, token: str, worker_id: str, capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        self.credentials.authenticate(token=token, worker_id=worker_id, scope=WorkerProtocol.TOKEN_SCOPE_WORKER_API)
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")
        supported_types = WorkerProtocol.supported_job_types(capabilities)

        def mutate(state):
            queued = [job for job in state["jobs"].values() if job.get("status") == "queued"]
            queued.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("created_at", ""))))
            for job in queued:
                if job.get("type") not in supported_types:
                    continue
                now = self._now_iso()
                job.update({
                    "status": "claimed",
                    "claimed_by": worker_id,
                    "claimed_at": now,
                    "updated_at": now,
                    "attempts": int(job.get("attempts", 0)) + 1,
                })
                return job
            return None

        job = self.store.update(mutate)
        return {"status": "claimed", "job": job} if job is not None else {"status": "empty", "job": None}

    def record_result(self, *, token: str, worker_id: str, job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return self._finish_job(token=token, worker_id=worker_id, job_id=job_id, status="completed", payload_key="result", payload=result)

    def record_failure(self, *, token: str, worker_id: str, job_id: str, error: Dict[str, Any]) -> Dict[str, Any]:
        return self._finish_job(token=token, worker_id=worker_id, job_id=job_id, status="failed", payload_key="error", payload=error)

    def delete_worker(self, *, worker_id: str) -> Dict[str, Any]:
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")

        def mutate(state):
            workers = state["workers"]
            if worker_id not in workers:
                raise WorkerApiError("worker_not_found")
            deleted_worker = workers.pop(worker_id)
            deleted_tokens = []
            for token_id, entry in list(state["tokens"].items()):
                if isinstance(entry, dict) and str(entry.get("worker_id") or "").strip() == worker_id:
                    deleted_tokens.append(str(token_id))
                    del state["tokens"][token_id]
            requeued_jobs = []
            now = self._now_iso()
            for job_id, job in state["jobs"].items():
                if not isinstance(job, dict) or str(job.get("claimed_by") or "") != worker_id:
                    continue
                if job.get("status") == "claimed":
                    job.update({"status": "queued", "updated_at": now})
                    job.pop("claimed_by", None)
                    job.pop("claimed_at", None)
                    requeued_jobs.append(str(job_id))
            return {
                "worker": deleted_worker,
                "deleted_token_ids": deleted_tokens,
                "requeued_job_ids": requeued_jobs,
            }

        result = self.store.update(mutate)
        return {
            "status": "deleted",
            "worker_id": worker_id,
            "deleted_tokens": len(result["deleted_token_ids"]),
            "requeued_jobs": len(result["requeued_job_ids"]),
            **result,
        }

    def status(self) -> Dict[str, Any]:
        state = self.store.read()
        by_status: Dict[str, int] = {}
        for job in state["jobs"].values():
            value = str(job.get("status") or "unknown")
            by_status[value] = by_status.get(value, 0) + 1
        return {
            "schema_version": WorkerProtocol.SCHEMA_VERSION,
            "component": "external_worker",
            "phase": "ready",
            "workers": len(state["workers"]),
            "jobs": {"total": len(state["jobs"]), "by_status": by_status},
        }

    def admin_status(self) -> Dict[str, Any]:
        state = self.store.read()
        now = utc_now(self._clock)
        enrollments = []
        for enrollment_id, raw in state["enrollments"].items():
            entry = raw if isinstance(raw, dict) else {}
            if entry.get("used_at"):
                phase = "enrolled"
            elif self._parse_time(entry.get("expires_at")) <= now:
                phase = "expired"
            else:
                phase = "waiting"
            enrollments.append({
                "enrollment_id": str(enrollment_id),
                "created_at": entry.get("created_at"),
                "expires_at": entry.get("expires_at"),
                "used_at": entry.get("used_at"),
                "worker_id": entry.get("worker_id"),
                "status": phase,
            })
        enrollments.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        workers = [dict(raw, worker_id=str(worker_id)) for worker_id, raw in state["workers"].items() if isinstance(raw, dict)]
        workers.sort(key=lambda item: str(item.get("last_seen_at") or item.get("registered_at") or ""), reverse=True)
        return {"schema_version": WorkerProtocol.SCHEMA_VERSION, "component": "external_worker", "enrollments": enrollments, "workers": workers}

    def _upsert_worker(self, *, worker_id: str, version: Optional[str] = None, status: str, capabilities: Optional[List[str]], metadata: Optional[Dict[str, Any]], require_existing: bool) -> Dict[str, Any]:
        def mutate(state):
            workers = state["workers"]
            if require_existing and worker_id not in workers:
                raise WorkerApiError("worker_not_registered")
            worker = workers.setdefault(worker_id, {"worker_id": worker_id, "registered_at": self._now_iso()})
            now = self._now_iso()
            worker["last_seen_at"] = now
            worker["status"] = status
            if version is not None:
                worker["version"] = version
                worker["registered_at"] = worker.get("registered_at") or now
            if capabilities is not None or "capabilities" not in worker:
                worker["capabilities"] = WorkerProtocol.normalize_capabilities(capabilities)
            if isinstance(metadata, dict):
                worker["metadata"] = metadata
            else:
                worker.setdefault("metadata", {})
            return dict(worker)
        return self.store.update(mutate)

    def _finish_job(self, *, token: str, worker_id: str, job_id: str, status: str, payload_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.credentials.authenticate(token=token, worker_id=worker_id, scope=WorkerProtocol.TOKEN_SCOPE_WORKER_API)
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")
        job_id = self.credentials.require_value(job_id, "job_id_required")

        def mutate(state):
            if job_id not in state["jobs"]:
                raise WorkerApiError("job_not_found")
            job = state["jobs"][job_id]
            if job.get("claimed_by") and job.get("claimed_by") != worker_id:
                raise WorkerApiError("job_claimed_by_other_worker")
            now = self._now_iso()
            job.update({"status": status, payload_key: payload if isinstance(payload, dict) else {}, "finished_at": now, "updated_at": now})
            return job

        job = self.store.update(mutate)
        return {"status": status, "job": job}

    def _now_iso(self) -> str:
        return iso_time(utc_now(self._clock))

    @staticmethod
    def _parse_time(value: Any):
        from services.worker_runtime_service import parse_time
        return parse_time(value)
