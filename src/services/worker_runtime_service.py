#!/usr/bin/env python3
"""Canonical runtime infrastructure for external AV ImgData workers."""

import hashlib
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence


class WorkerApiError(RuntimeError):
    def __init__(self, code: str, message: Optional[str] = None):
        self.code = str(code)
        super().__init__(message or self.code)


class WorkerProtocol:
    SCHEMA_VERSION = 2
    TOKEN_SCOPE_WORKER_API = "worker_api"
    TOKEN_SCOPE_MODELS_READ = "models_read"
    DEFAULT_TOKEN_SCOPES = (TOKEN_SCOPE_WORKER_API, TOKEN_SCOPE_MODELS_READ)
    CAPABILITIES = (
        "face_native_detect",
        "face_native_embed",
        "face_native_detect_batch",
        "face_native_embed_batch",
        "face_native_rank_embeddings",
        "face_native_profile_math",
        "warm_processor_worker",
    )
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
    def supported_job_types(cls, capabilities: Optional[Sequence[str]]) -> set:
        result = set()
        for capability in cls.normalize_capabilities(capabilities):
            result.update(cls.JOB_TYPES_BY_CAPABILITY.get(capability, ()))
        return result


class WorkerRuntimePathService:
    """Resolve package and worker state paths using one documented priority."""

    def __init__(self, *, package_var: Optional[Path] = None, config_service: Optional[Any] = None):
        self.package_var = Path(
            package_var if package_var is not None else os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
        ).resolve()
        self.config_service = config_service

    def state_path(self, explicit: Optional[Path] = None) -> Path:
        if explicit is not None and str(explicit).strip():
            return self._resolve(explicit)
        configured = self._configured_state_path()
        if configured:
            return self._resolve(configured)
        environment = os.getenv("AV_IMGDATA_WORKER_API_STATE_PATH", "").strip()
        if environment:
            return self._resolve(environment)
        return (self.package_var / "worker-api-state.json").resolve()

    def _configured_state_path(self) -> str:
        if self.config_service is None:
            return ""
        try:
            config = self.config_service.readMergedConfig()
        except Exception:
            return ""
        worker_api = config.get("worker_api") if isinstance(config, dict) and isinstance(config.get("worker_api"), dict) else {}
        return str(worker_api.get("STATE_PATH") or "").strip()

    def _resolve(self, value: Any) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.package_var / path).resolve()


class WorkerStateStore:
    """Single authority for worker runtime JSON state, migration and permissions."""

    _locks_guard = threading.Lock()
    _locks: Dict[str, threading.RLock] = {}

    def __init__(self, *, package_var: Optional[Path] = None, state_path: Optional[Path] = None, config_service: Optional[Any] = None):
        self.paths = WorkerRuntimePathService(package_var=package_var, config_service=config_service)
        self.package_var = self.paths.package_var
        self.state_path = self.paths.state_path(state_path)
        key = str(self.state_path)
        with self._locks_guard:
            self._lock = self._locks.setdefault(key, threading.RLock())

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
        with self._lock:
            if not self.state_path.is_file():
                return self.default_state()
            try:
                with self.state_path.open("r", encoding="utf-8") as handle:
                    state = json.load(handle)
            except json.JSONDecodeError as exc:
                raise WorkerApiError("state_invalid", str(exc))
            except OSError as exc:
                raise WorkerApiError("state_read_failed", str(exc))
            if not isinstance(state, dict):
                raise WorkerApiError("state_invalid")
            return self.migrate(state)

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
        with self._lock:
            normalized = self.migrate(state)
            tmp_name = ""
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(prefix=self.state_path.name + ".", suffix=".tmp", dir=str(self.state_path.parent))
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(normalized, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                self._apply_runtime_permissions(Path(tmp_name))
                os.replace(tmp_name, str(self.state_path))
                self._apply_runtime_permissions(self.state_path)
            except OSError as exc:
                raise WorkerApiError("state_write_failed", str(exc))
            finally:
                if tmp_name:
                    try:
                        os.unlink(tmp_name)
                    except FileNotFoundError:
                        pass

    def update(self, mutator: Callable[[Dict[str, Any]], Any]) -> Any:
        with self._lock:
            state = self.read()
            result = mutator(state)
            self.write(state)
            return result

    def _apply_runtime_permissions(self, path: Path) -> None:
        if os.name != "posix":
            return
        try:
            owner = self.package_var.stat()
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                os.chown(str(path), owner.st_uid, owner.st_gid)
            os.chmod(str(path), 0o600)
        except OSError:
            return


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
        token = self.require_value(token, "token_required")
        requested_worker = str(worker_id or "").strip()
        digest = self.hash_value(token)
        for token_id, entry in self.store.read().get("tokens", {}).items():
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
