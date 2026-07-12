#!/usr/bin/env python3
"""Secure external-worker enrollment and licensed model distribution."""

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from services.config_service import ConfigService
from services.face_model_store_service import FaceModelStoreService
from services.worker_runtime_service import (
    WorkerApiError,
    WorkerCredentialService,
    WorkerProtocol,
    WorkerStateStore,
    iso_time,
    parse_time,
    utc_now,
)


class WorkerProvisioningService:
    DEFAULT_SCOPES = WorkerProtocol.DEFAULT_TOKEN_SCOPES

    def __init__(self, *, package_var: Optional[Path] = None, state_path: Optional[Path] = None, clock: Optional[Callable[[], datetime]] = None, config_service: Optional[ConfigService] = None, state_store: Optional[WorkerStateStore] = None):
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

    def create_enrollment(self, *, enrollment_id: str, expires_minutes: int = 15) -> Dict[str, Any]:
        enrollment_id = self.credentials.require_value(enrollment_id, "enrollment_id_required")
        expires_minutes = max(1, min(int(expires_minutes), 1440))
        code = secrets.token_urlsafe(24)
        now = utc_now(self._clock)
        entry = {
            "code_hash": self.credentials.hash_value(code),
            "created_at": iso_time(now),
            "expires_at": iso_time(now + timedelta(minutes=expires_minutes)),
            "used_at": None,
            "worker_id": None,
        }
        self.store.update(lambda state: state["enrollments"].__setitem__(enrollment_id, entry))
        return {"enrollment_id": enrollment_id, "enrollment_code": code, "expires_at": entry["expires_at"]}

    def redeem_enrollment(self, *, enrollment_code: str, worker_id: str) -> Dict[str, Any]:
        enrollment_code = self.credentials.require_value(enrollment_code, "enrollment_code_required")
        worker_id = self.credentials.require_value(worker_id, "worker_id_required")
        digest = self.credentials.hash_value(enrollment_code)
        now = iso_time(utc_now(self._clock))
        token_id = "worker-%s-%s" % (worker_id, secrets.token_hex(4))
        token = secrets.token_urlsafe(32)
        token_entry = self.credentials.create_token_entry(
            token=token,
            worker_id=worker_id,
            scopes=self.DEFAULT_SCOPES,
            issued_via="enrollment",
            enrollment_id="",
            created_at=now,
        )

        def mutate(state):
            match_id = ""
            match = None
            for enrollment_id, entry in state["enrollments"].items():
                if isinstance(entry, dict) and entry.get("code_hash") == digest:
                    match_id, match = str(enrollment_id), entry
                    break
            if match is None:
                raise WorkerApiError("invalid_enrollment_code")
            if match.get("used_at"):
                raise WorkerApiError("enrollment_code_used")
            if parse_time(match.get("expires_at")) <= utc_now(self._clock):
                raise WorkerApiError("enrollment_code_expired")
            token_entry["enrollment_id"] = match_id
            state["tokens"][token_id] = token_entry
            match["used_at"] = now
            match["worker_id"] = worker_id
            return match_id

        self.store.update(mutate)
        return {
            "status": "enrolled",
            "worker_id": worker_id,
            "token_id": token_id,
            "token": token,
            "scopes": list(token_entry["scopes"]),
        }

    def require_token(self, *, token: str, worker_id: str, scope: str) -> Dict[str, Any]:
        return self.credentials.authenticate(token=token, worker_id=worker_id, scope=scope)

    def model_manifest(self, *, token: str, worker_id: str, model_pack: str = "buffalo_l") -> Dict[str, Any]:
        self.require_token(token=token, worker_id=worker_id, scope=WorkerProtocol.TOKEN_SCOPE_MODELS_READ)
        store = self._model_store()
        status = store.status(model_pack)
        if not status.get("models_present"):
            raise WorkerApiError("model_files_missing")
        if not status.get("license_ack_present") and self._legacy_license_acknowledged():
            store.acknowledge_usage(model_pack=model_pack, accepted_by="existing_package_configuration", package_version="migration", source="legacy_config_migration")
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

    def _model_store(self) -> FaceModelStoreService:
        return FaceModelStoreService(self.config_service, package_var=self.package_var)

    def _legacy_license_acknowledged(self) -> bool:
        try:
            config = self.config_service.readMergedConfig()
        except Exception:
            return False
        native = config.get("native_processors") if isinstance(config, dict) and isinstance(config.get("native_processors"), dict) else {}
        face = native.get("FACE_PROCESSOR") if isinstance(native.get("FACE_PROCESSOR"), dict) else {}
        return face.get("INSIGHTFACE_LICENSE_ACKNOWLEDGED") is True
