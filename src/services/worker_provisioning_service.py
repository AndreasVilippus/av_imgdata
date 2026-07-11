#!/usr/bin/env python3
"""Secure external-worker enrollment and licensed model distribution."""

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from services.config_service import ConfigService
from services.face_model_store_service import FaceModelStoreService
from services.worker_api_service import WorkerApiError


class WorkerProvisioningService:
    DEFAULT_SCOPES = ("worker_api", "models_read")

    def __init__(self, *, package_var: Optional[Path] = None, state_path: Optional[Path] = None,
                 clock: Optional[Callable[[], datetime]] = None):
        self.package_var = Path(package_var) if package_var else Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
        self.state_path = Path(state_path) if state_path else self.package_var / "worker-api-state.json"
        self._clock = clock if callable(clock) else lambda: datetime.now(timezone.utc)

    def create_enrollment(self, *, enrollment_id: str, expires_minutes: int = 15) -> Dict[str, Any]:
        enrollment_id = self._required(enrollment_id, "enrollment_id_required")
        expires_minutes = max(1, min(int(expires_minutes), 1440))
        code = secrets.token_urlsafe(24)
        state = self._read_state()
        entry = {
            "code_hash": self._hash(code),
            "created_at": self._iso(self._now()),
            "expires_at": self._iso(self._now() + timedelta(minutes=expires_minutes)),
            "used_at": None,
            "worker_id": None,
        }
        state.setdefault("enrollments", {})[enrollment_id] = entry
        self._write_state(state)
        return {"enrollment_id": enrollment_id, "enrollment_code": code, "expires_at": entry["expires_at"]}

    def redeem_enrollment(self, *, enrollment_code: str, worker_id: str) -> Dict[str, Any]:
        enrollment_code = self._required(enrollment_code, "enrollment_code_required")
        worker_id = self._required(worker_id, "worker_id_required")
        state = self._read_state()
        digest = self._hash(enrollment_code)
        match_id = None
        match = None
        for enrollment_id, entry in state.setdefault("enrollments", {}).items():
            if entry.get("code_hash") == digest:
                match_id, match = enrollment_id, entry
                break
        if match is None:
            raise WorkerApiError("invalid_enrollment_code")
        if match.get("used_at"):
            raise WorkerApiError("enrollment_code_used")
        if self._parse_iso(match.get("expires_at")) <= self._now():
            raise WorkerApiError("enrollment_code_expired")

        token = secrets.token_urlsafe(32)
        token_id = "worker-%s-%s" % (worker_id, secrets.token_hex(4))
        now = self._iso(self._now())
        state.setdefault("tokens", {})[token_id] = {
            "token_hash": self._hash(token),
            "created_at": now,
            "revoked": False,
            "worker_id": worker_id,
            "scopes": list(self.DEFAULT_SCOPES),
            "issued_via": "enrollment",
            "enrollment_id": match_id,
        }
        match["used_at"] = now
        match["worker_id"] = worker_id
        self._write_state(state)
        return {"status": "enrolled", "worker_id": worker_id, "token_id": token_id, "token": token,
                "scopes": list(self.DEFAULT_SCOPES)}

    def require_token(self, *, token: str, worker_id: str, scope: str) -> Dict[str, Any]:
        token = self._required(token, "token_required")
        worker_id = self._required(worker_id, "worker_id_required")
        digest = self._hash(token)
        state = self._read_state()
        for token_id, entry in state.get("tokens", {}).items():
            if entry.get("token_hash") != digest or entry.get("revoked"):
                continue
            bound_worker = str(entry.get("worker_id") or "").strip()
            if bound_worker and bound_worker != worker_id:
                raise WorkerApiError("token_worker_mismatch")
            scopes = entry.get("scopes") if isinstance(entry.get("scopes"), list) else ["worker_api", "models_read"]
            if scope not in scopes:
                raise WorkerApiError("token_scope_missing")
            return {"token_id": token_id, "worker_id": bound_worker or worker_id, "scopes": scopes}
        raise WorkerApiError("unauthorized")

    def model_manifest(self, *, token: str, worker_id: str, model_pack: str = "buffalo_l") -> Dict[str, Any]:
        self.require_token(token=token, worker_id=worker_id, scope="models_read")
        store = self._model_store()
        status = store.status(model_pack)

        # Existing installations may have accepted the license before LICENSE_ACK.json
        # was introduced. Preserve that valid consent by materializing the new audit
        # file in the configured model directory, but only when the required models
        # are already present and the legacy config flag is explicitly true.
        if not status.get("models_present"):
            raise WorkerApiError("model_files_missing")
        if not status.get("license_ack_present") and self._legacy_license_acknowledged():
            store.acknowledge_usage(
                model_pack=model_pack,
                accepted_by="existing_package_configuration",
                package_version="migration",
                source="legacy_config_migration",
            )
            status = store.status(model_pack)
        if not status.get("license_ack_present"):
            raise WorkerApiError("model_license_not_acknowledged")

        manifest_path = Path(status["manifest_path"])
        if not manifest_path.is_file():
            store.write_manifest(model_pack=model_pack, source="worker_distribution")
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["download_base"] = "/worker-api/models/%s/files" % model_pack
        manifest["license_acknowledged"] = True
        return manifest

    def model_file(self, *, token: str, worker_id: str, model_pack: str, filename: str) -> Path:
        manifest = self.model_manifest(token=token, worker_id=worker_id, model_pack=model_pack)
        allowed = {str(item.get("name")) for item in manifest.get("files", []) if item.get("present")}
        if filename not in allowed:
            raise WorkerApiError("model_file_not_allowed")
        path = self._model_store().model_dir(model_pack) / filename
        if not path.is_file():
            raise WorkerApiError("model_file_not_found")
        return path

    def _config_service(self) -> ConfigService:
        return ConfigService(str(self.package_var / "config.json"))

    def _model_store(self) -> FaceModelStoreService:
        return FaceModelStoreService(self._config_service(), package_var=self.package_var)

    def _legacy_license_acknowledged(self) -> bool:
        try:
            config = self._config_service().readMergedConfig()
        except Exception:
            return False
        if not isinstance(config, dict):
            return False
        native = config.get("native_processors") if isinstance(config.get("native_processors"), dict) else {}
        face = native.get("FACE_PROCESSOR") if isinstance(native.get("FACE_PROCESSOR"), dict) else {}
        return face.get("INSIGHTFACE_LICENSE_ACKNOWLEDGED") is True

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_path.is_file():
            return {"schema_version": 2, "tokens": {}, "workers": {}, "jobs": {}, "enrollments": {}}
        with self.state_path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            raise WorkerApiError("state_invalid")
        state.setdefault("tokens", {})
        state.setdefault("workers", {})
        state.setdefault("jobs", {})
        state.setdefault("enrollments", {})
        state["schema_version"] = max(2, int(state.get("schema_version", 1)))
        return state

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.state_path.name + ".", suffix=".tmp", dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, str(self.state_path))
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def _now(self) -> datetime:
        value = self._clock()
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_iso(value: Any) -> datetime:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return datetime.fromtimestamp(0, tz=timezone.utc)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _required(value: Any, code: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise WorkerApiError(code)
        return text
