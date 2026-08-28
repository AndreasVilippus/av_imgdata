#!/usr/bin/env python3
"""Canonical runtime infrastructure for external AV ImgData workers."""

import hashlib
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from av_imgdata.db.connection import Database, DatabaseError

from services.worker_protocol_generated import (
    CAPABILITIES,
    CONFIG_SCHEMA_VERSION,
    INPUT_MODES,
    PROTOCOL_VERSION,
    STATE_SCHEMA_VERSION,
    TOKEN_SCOPES,
    WORKER_VERSION,
)


class WorkerApiError(RuntimeError):
    def __init__(self, code: str, message: Optional[str] = None):
        self.code = str(code)
        detail = str(message or "").strip()
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


class WorkerProtocol:
    PROTOCOL_VERSION = PROTOCOL_VERSION
    WORKER_VERSION = WORKER_VERSION
    CONFIG_SCHEMA_VERSION = CONFIG_SCHEMA_VERSION
    SCHEMA_VERSION = STATE_SCHEMA_VERSION
    TOKEN_SCOPE_WORKER_API = "worker_api"
    TOKEN_SCOPE_MODELS_READ = "models_read"
    DEFAULT_TOKEN_SCOPES = TOKEN_SCOPES
    CAPABILITIES = CAPABILITIES
    INPUT_MODES = INPUT_MODES
    JOB_TYPES_BY_CAPABILITY = {capability: (capability,) for capability in CAPABILITIES}

    @classmethod
    def normalize_capabilities(cls, capabilities: Optional[Sequence[str]]) -> List[str]:
        if not capabilities:
            return list(cls.CAPABILITIES)
        seen = set()
        result = []
        for item in capabilities:
            value = str(item or "").strip()
            if value and value in cls.JOB_TYPES_BY_CAPABILITY and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @classmethod
    def normalize_input_modes(cls, input_modes: Optional[Sequence[str]]) -> List[str]:
        values = input_modes or cls.INPUT_MODES
        seen = set()
        result = []
        for item in values:
            value = str(item or "").strip()
            if value and value in cls.INPUT_MODES and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @classmethod
    def supported_job_types(cls, capabilities: Optional[Sequence[str]]) -> set:
        result = set()
        for capability in cls.normalize_capabilities(capabilities):
            result.update(cls.JOB_TYPES_BY_CAPABILITY.get(capability, ()))
        return result


class WorkerRuntimePathService:
    """Resolve the package-local SQLite runtime database path."""

    DEFAULT_PACKAGE_VAR = Path("/var/packages/AV_ImgData/var")

    def __init__(self, *, package_var: Optional[Path] = None, config_service: Optional[Any] = None):
        self.package_var = self.resolve_package_var(package_var)
        self.config_service = config_service

    @classmethod
    def resolve_package_var(cls, package_var: Optional[Path] = None, *, fallback: Optional[Path] = None) -> Path:
        if package_var is not None:
            return Path(package_var).resolve()
        configured = str(os.getenv("SYNOPKG_PKGVAR") or "").strip()
        if configured:
            return Path(configured).resolve()
        return Path(fallback if fallback is not None else cls.DEFAULT_PACKAGE_VAR).resolve()

    def database_path(self) -> Path:
        return (self.package_var / "imgdata.sqlite3").resolve()


class WorkerStateStore:
    """Single authority for worker runtime state and locking."""

    _locks_guard = threading.Lock()
    _locks: Dict[str, threading.RLock] = {}

    def __init__(self, *, package_var: Optional[Path] = None, config_service: Optional[Any] = None):
        self.paths = WorkerRuntimePathService(package_var=package_var, config_service=config_service)
        self.package_var = self.paths.package_var
        self.database_path = self.paths.database_path()
        self.database = Database(str(self.database_path))
        key = str(self.database.path.resolve())
        with self._locks_guard:
            self._lock = self._locks.setdefault(key, threading.RLock())

    def _debug_log(self, event: str, **fields: Any) -> None:
        module = sys.modules.get("api.imgdata_api")
        logger = getattr(module, "backend_debug_log", None) if module is not None else None
        if not callable(logger):
            return
        try:
            logger(event, **fields)
        except Exception:
            pass

    def _state_file_size(self) -> int:
        try:
            return int(self.database_path.stat().st_size)
        except OSError:
            return 0

    @staticmethod
    def _state_counts(state: Dict[str, Any]) -> Dict[str, int]:
        return {
            "tokens_count": len(state.get("tokens", {})) if isinstance(state.get("tokens"), dict) else 0,
            "workers_count": len(state.get("workers", {})) if isinstance(state.get("workers"), dict) else 0,
            "jobs_count": len(state.get("jobs", {})) if isinstance(state.get("jobs"), dict) else 0,
            "enrollments_count": len(state.get("enrollments", {})) if isinstance(state.get("enrollments"), dict) else 0,
        }

    @staticmethod
    def default_state() -> Dict[str, Any]:
        return {
            "schema_version": WorkerProtocol.SCHEMA_VERSION,
            "tokens": {},
            "workers": {},
            "jobs": {},
            "enrollments": {},
        }

    def read(self) -> Dict[str, Any]:
        started = time.monotonic()
        with self._lock:
            try:
                state = self._read_sqlite_state()
            except DatabaseError as exc:
                raise WorkerApiError("state_read_failed", str(exc)) from exc
            except json.JSONDecodeError as exc:
                raise WorkerApiError("state_invalid", str(exc)) from exc
            if not any(state.get(key) for key in ("tokens", "workers", "jobs", "enrollments")):
                self._debug_log(
                    "worker_state_read",
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    bytes=self._state_file_size(),
                    missing=True,
                )
                return self.default_state()
            if not isinstance(state, dict):
                raise WorkerApiError("state_invalid")
            migrated = self.migrate(state)
            self._debug_log(
                "worker_state_read",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                bytes=self._state_file_size(),
                missing=False,
                **self._state_counts(migrated),
            )
            return migrated

    def migrate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(state)
        for key in ("tokens", "workers", "jobs", "enrollments"):
            if not isinstance(result.get(key), dict):
                result[key] = {}
        result["schema_version"] = WorkerProtocol.SCHEMA_VERSION
        for token in result["tokens"].values():
            if isinstance(token, dict):
                token.setdefault("revoked", False)
                token.setdefault("scopes", list(WorkerProtocol.DEFAULT_TOKEN_SCOPES))
        return result

    def write(self, state: Dict[str, Any]) -> None:
        started = time.monotonic()
        with self._lock:
            normalized = self.migrate(state)
            try:
                self._write_sqlite_state(normalized)
                self._debug_log(
                    "worker_state_write",
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    bytes=self._state_file_size(),
                    **self._state_counts(normalized),
                )
            except DatabaseError as exc:
                raise WorkerApiError("state_write_failed", str(exc))

    def update(self, mutator: Callable[[Dict[str, Any]], Any]) -> Any:
        started = time.monotonic()
        with self._lock:
            state = self.read()
            result = mutator(state)
            self.write(state)
            self._debug_log(
                "worker_state_update",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                changed=True,
                **self._state_counts(state),
            )
            return result

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _json_loads(value: Any, default: Any) -> Any:
        if value is None:
            return default
        return json.loads(str(value))

    @staticmethod
    def _job_origin_fields(job: Dict[str, Any]) -> Dict[str, str]:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}
        return {
            "operation_id": str(origin.get("operation_id") or ""),
            "action": str(origin.get("action") or ""),
        }

    def _read_sqlite_state(self) -> Dict[str, Any]:
        with self.database.read() as connection:
            extra_row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?",
                ("worker_runtime:extra",),
            ).fetchone()
            extra = self._json_loads(extra_row["value"], {}) if extra_row else {}
            tokens = {}
            for row in connection.execute("SELECT * FROM worker_tokens"):
                token = {
                    "token_hash": row["token_hash"],
                    "created_at": row["created_at"],
                    "revoked": bool(row["revoked"]),
                    "worker_id": row["worker_id"] or "",
                    "scopes": self._json_loads(row["scopes_json"], []),
                    "issued_via": row["issued_via"] or "admin",
                    "enrollment_id": row["enrollment_id"] or "",
                }
                tokens[str(row["token_id"])] = token
            workers = {
                str(row["worker_id"]): self._json_loads(row["worker_json"], {})
                for row in connection.execute("SELECT worker_id, worker_json FROM worker_workers")
            }
            jobs = {
                str(row["job_id"]): self._json_loads(row["job_json"], {})
                for row in connection.execute("SELECT job_id, job_json FROM worker_jobs")
            }
            enrollments = {
                str(row["enrollment_id"]): self._json_loads(row["enrollment_json"], {})
                for row in connection.execute("SELECT enrollment_id, enrollment_json FROM worker_enrollments")
            }
        state = extra if isinstance(extra, dict) else {}
        state.update({
            "schema_version": WorkerProtocol.SCHEMA_VERSION,
            "tokens": tokens,
            "workers": workers,
            "jobs": jobs,
            "enrollments": enrollments,
        })
        return state

    def _write_sqlite_state(self, state: Dict[str, Any]) -> None:
        extra = {
            key: value
            for key, value in state.items()
            if key not in {"schema_version", "tokens", "workers", "jobs", "enrollments"}
        }
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM worker_tokens")
            connection.execute("DELETE FROM worker_workers")
            connection.execute("DELETE FROM worker_jobs")
            connection.execute("DELETE FROM worker_enrollments")
            connection.execute(
                """
                INSERT INTO app_state(key, value, value_type)
                VALUES (?, ?, 'json')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, value_type = excluded.value_type
                """,
                ("worker_runtime:extra", self._json_dumps(extra)),
            )
            for token_id, raw in state.get("tokens", {}).items():
                entry = raw if isinstance(raw, dict) else {}
                connection.execute(
                    """
                    INSERT INTO worker_tokens(token_id, token_hash, created_at, revoked, worker_id, scopes_json, issued_via, enrollment_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(token_id),
                        str(entry.get("token_hash") or ""),
                        str(entry.get("created_at") or ""),
                        1 if entry.get("revoked") else 0,
                        str(entry.get("worker_id") or ""),
                        self._json_dumps(entry.get("scopes") if isinstance(entry.get("scopes"), list) else []),
                        str(entry.get("issued_via") or "admin"),
                        str(entry.get("enrollment_id") or ""),
                    ),
                )
            for worker_id, raw in state.get("workers", {}).items():
                worker = raw if isinstance(raw, dict) else {}
                connection.execute(
                    """
                    INSERT INTO worker_workers(worker_id, worker_json, status, version, registered_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(worker_id),
                        self._json_dumps(worker),
                        str(worker.get("status") or ""),
                        str(worker.get("version") or ""),
                        str(worker.get("registered_at") or ""),
                        str(worker.get("last_seen_at") or ""),
                    ),
                )
            for job_id, raw in state.get("jobs", {}).items():
                job = raw if isinstance(raw, dict) else {}
                origin = self._job_origin_fields(job)
                connection.execute(
                    """
                    INSERT INTO worker_jobs(job_id, job_json, type, status, priority, created_at, updated_at, claimed_by, operation_id, action)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(job_id),
                        self._json_dumps(job),
                        str(job.get("type") or ""),
                        str(job.get("status") or "unknown"),
                        int(job.get("priority", 100) or 100),
                        str(job.get("created_at") or ""),
                        str(job.get("updated_at") or ""),
                        str(job.get("claimed_by") or ""),
                        origin["operation_id"],
                        origin["action"],
                    ),
                )
            for enrollment_id, raw in state.get("enrollments", {}).items():
                enrollment = raw if isinstance(raw, dict) else {}
                connection.execute(
                    """
                    INSERT INTO worker_enrollments(enrollment_id, enrollment_json, created_at, expires_at, used_at, worker_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(enrollment_id),
                        self._json_dumps(enrollment),
                        str(enrollment.get("created_at") or ""),
                        str(enrollment.get("expires_at") or ""),
                        str(enrollment.get("used_at") or ""),
                        str(enrollment.get("worker_id") or ""),
                    ),
                )

    def update_if_changed(self, mutator: Callable[[Dict[str, Any]], Any]) -> Any:
        started = time.monotonic()
        with self._lock:
            state = self.read()
            result, changed = mutator(state)
            if changed:
                self.write(state)
            self._debug_log(
                "worker_state_update",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                changed=bool(changed),
                **self._state_counts(state),
            )
            return result

class WorkerCredentialService:
    """Issue and validate all worker tokens with one security contract."""

    def __init__(self, store: WorkerStateStore):
        self.store = store

    def create_token_entry(self, *, token: str, worker_id: str = "", scopes: Optional[Sequence[str]] = None, issued_via: str = "admin", enrollment_id: str = "", created_at: str) -> Dict[str, Any]:
        return {
            "token_hash": self.hash_value(token),
            "created_at": created_at,
            "revoked": False,
            "worker_id": str(worker_id or "").strip(),
            "scopes": self.normalize_scopes(scopes),
            "issued_via": str(issued_via or "admin"),
            "enrollment_id": str(enrollment_id or "").strip(),
        }

    def issue_token(self, *, token_id: str, worker_id: str = "", scopes: Optional[Sequence[str]] = None, issued_via: str = "admin", enrollment_id: str = "", created_at: str) -> Dict[str, Any]:
        token_id = self.require_value(token_id, "token_id_required")
        token = secrets.token_urlsafe(32)
        entry = self.create_token_entry(token=token, worker_id=worker_id, scopes=scopes, issued_via=issued_via, enrollment_id=enrollment_id, created_at=created_at)
        self.store.update(lambda state: state["tokens"].__setitem__(token_id, entry))
        return {"token_id": token_id, "token": token, "created_at": created_at, "scopes": list(entry["scopes"])}

    def authenticate(self, *, token: str, worker_id: str = "", scope: str = WorkerProtocol.TOKEN_SCOPE_WORKER_API) -> Dict[str, Any]:
        return self.authenticate_state(
            self.store.read(),
            token=token,
            worker_id=worker_id,
            scope=scope,
        )

    def authenticate_state(self, state: Dict[str, Any], *, token: str, worker_id: str = "", scope: str = WorkerProtocol.TOKEN_SCOPE_WORKER_API) -> Dict[str, Any]:
        token = self.require_value(token, "token_required")
        requested_worker = str(worker_id or "").strip()
        digest = self.hash_value(token)
        for token_id, entry in state.get("tokens", {}).items():
            if not isinstance(entry, dict) or entry.get("token_hash") != digest or entry.get("revoked"):
                continue
            bound_worker = str(entry.get("worker_id") or "").strip()
            if bound_worker and requested_worker and bound_worker != requested_worker:
                raise WorkerApiError("token_worker_mismatch")
            scopes = self.normalize_scopes(entry.get("scopes"))
            if scope and scope not in scopes:
                raise WorkerApiError("token_scope_missing")
            return {"token_id": token_id, "worker_id": bound_worker or requested_worker, "scopes": scopes}
        raise WorkerApiError("unauthorized")

    @staticmethod
    def normalize_scopes(scopes: Optional[Sequence[str]]) -> List[str]:
        values = scopes or WorkerProtocol.DEFAULT_TOKEN_SCOPES
        seen = set()
        result = []
        for scope in values:
            value = str(scope or "").strip()
            if value and value in WorkerProtocol.DEFAULT_TOKEN_SCOPES and value not in seen:
                seen.add(value)
                result.append(value)
        return result or list(WorkerProtocol.DEFAULT_TOKEN_SCOPES)

    @staticmethod
    def hash_value(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def require_value(value: Any, code: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise WorkerApiError(code)
        return text


def utc_now(clock: Optional[Callable[[], datetime]] = None) -> datetime:
    value = clock() if callable(clock) else datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)
