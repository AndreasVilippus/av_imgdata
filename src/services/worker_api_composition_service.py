#!/usr/bin/env python3
"""Composition root for the DSM-side external Worker API."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from services.config_service import ConfigService
from services.external_worker_processor_service import ExternalWorkerProcessorService
from services.native_face_processor_service import NativeFaceProcessorService
from services.worker_api_service import WorkerApiService
from services.worker_provisioning_service import WorkerProvisioningService
from services.worker_runtime_service import WorkerRuntimePathService, WorkerStateStore


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class WorkerApiConfigurationService:
    """Read Worker API runtime configuration through one precedence contract."""

    def __init__(self, *, package_var: Optional[Path] = None, config_service: Optional[ConfigService] = None):
        self.package_var = Path(
            package_var if package_var is not None else os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
        ).resolve()
        self.config_service = config_service or ConfigService(str(self.package_var / "config.json"))
        self.paths = WorkerRuntimePathService(package_var=self.package_var, config_service=self.config_service)

    def worker_api_config(self) -> Dict[str, Any]:
        try:
            config = self.config_service.readMergedConfig()
        except Exception:
            return {}
        worker_api = config.get("worker_api") if isinstance(config, dict) else {}
        return worker_api if isinstance(worker_api, dict) else {}

    def enabled(self) -> bool:
        override = str(os.getenv("AV_IMGDATA_WORKER_API_ENABLED", "") or "").strip().lower()
        if override in _TRUE_VALUES:
            return True
        if override in _FALSE_VALUES:
            return False
        return bool(self.worker_api_config().get("ENABLED", False))

    def state_path(self, explicit: Optional[Path] = None) -> Path:
        return self.paths.state_path(explicit)


class WorkerApiCompositionService:
    """Own shared Worker API services for one package runtime."""

    def __init__(self, *, package_var: Optional[Path] = None, state_path: Optional[Path] = None):
        self.configuration = WorkerApiConfigurationService(package_var=package_var)
        self.package_var = self.configuration.package_var
        self.config_service = self.configuration.config_service
        self.state_store = WorkerStateStore(
            package_var=self.package_var,
            state_path=self.configuration.state_path(state_path),
            config_service=self.config_service,
        )
        self.worker_api = WorkerApiService(
            package_var=self.package_var,
            state_path=self.state_store.state_path,
            config_service=self.config_service,
            state_store=self.state_store,
        )
        self.provisioning = WorkerProvisioningService(
            package_var=self.package_var,
            state_path=self.state_store.state_path,
            config_service=self.config_service,
            state_store=self.state_store,
        )
        self.native_face_processor = NativeFaceProcessorService(self.config_service)

    def enabled(self) -> bool:
        return self.configuration.enabled()

    def external_face_processor(
        self,
        *,
        nas_root: Path,
        path_profile: str = "photos",
        stale_after_seconds: int = 30,
        wait_timeout_seconds: int = 300,
        poll_interval_seconds: float = 0.5,
    ) -> ExternalWorkerProcessorService:
        """Build the shared face dispatch/result service from the composition root."""

        return ExternalWorkerProcessorService(
            self.worker_api,
            self.native_face_processor,
            nas_root=nas_root,
            path_profile=path_profile,
            stale_after_seconds=stale_after_seconds,
            wait_timeout_seconds=wait_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


def worker_error_http_status(code: str) -> int:
    """Map stable Worker API error codes to one HTTP status contract."""

    value = str(code or "").strip()
    if value in {"unauthorized", "token_required"}:
        return 401
    if value in {"token_scope_missing", "token_worker_mismatch"}:
        return 403
    if value.endswith("_not_found") or value in {"model_file_not_allowed", "unknown_worker_api_action", "unknown_worker_api_route"}:
        return 404
    if value in {"worker_api_disabled"}:
        return 404
    if value in {"job_already_exists", "enrollment_code_used"}:
        return 409
    if value in {"state_read_failed", "state_write_failed"}:
        return 503
    if value in {"state_invalid"}:
        return 500
    if value.startswith("invalid_") or value.endswith("_required") or value in {
        "job_type_unsupported",
        "enrollment_code_expired",
        "token_scope_missing",
        "worker_not_registered",
    }:
        return 400
    return 400
