#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.face_model_path_service import FaceModelPathService


class FaceModelStoreError(RuntimeError):
    pass


class FaceModelStoreService:
    """DSM-side model store and consent metadata for face models.

    Path resolution is delegated to :class:`FaceModelPathService`, the same
    resolver used by the local native processor and external-worker model
    distribution. This service owns only file operations, manifests, and
    acknowledgement metadata.
    """

    DEFAULT_MODEL_PACK = "buffalo_l"
    REQUIRED_FILES = ("det_10g.onnx", "w600k_r50.onnx")
    USAGE_NOTICE = (
        "Face recognition model files are not distributed with AV ImgData. "
        "Administrators are responsible for obtaining and using them under the applicable license."
    )

    def __init__(
        self,
        config_service: Optional[Any] = None,
        *,
        package_var: Optional[Path] = None,
        clock: Optional[Callable[[], datetime]] = None,
        path_service: Optional[FaceModelPathService] = None,
    ):
        self.config_service = config_service
        self.package_var = Path(package_var) if package_var else Path(
            os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
        )
        self.path_service = path_service or FaceModelPathService(
            config_service,
            package_var=self.package_var,
        )
        # Retained as a public compatibility field. It now means the canonical
        # default model store, not an independently selected fallback.
        self.fallback_root = self.path_service.model_store()
        self._clock = clock if callable(clock) else lambda: datetime.now(timezone.utc)

    def model_root(self) -> Path:
        """Return the canonical directory containing model-pack directories."""
        return self.path_service.model_store()

    def model_dir(self, model_pack: str = DEFAULT_MODEL_PACK) -> Path:
        return self.path_service.model_dir(self._normalize_model_pack(model_pack))

    def required_paths(self, model_pack: str = DEFAULT_MODEL_PACK) -> Dict[str, Path]:
        directory = self.model_dir(model_pack)
        return {
            "detector": directory / "det_10g.onnx",
            "recognizer": directory / "w600k_r50.onnx",
            "manifest": directory / "manifest.json",
            "license_ack": directory / "LICENSE_ACK.json",
        }

    def status(self, model_pack: str = DEFAULT_MODEL_PACK) -> Dict[str, Any]:
        model_pack = self._normalize_model_pack(model_pack)
        resolved = self.path_service.resolve(model_pack)
        root = resolved["model_store"]
        paths = self.required_paths(model_pack)
        required = {name: paths[name].is_file() for name in ("detector", "recognizer")}
        status = {
            "model_pack": model_pack,
            "root": str(root),
            "root_source": resolved["model_root_source"],
            "fallback_root": str(self.fallback_root),
            "insightface_root": str(resolved["model_root"]),
            "model_dir": str(resolved["model_dir"]),
            "distributed_with_package": False,
            "usage_ack_required": True,
            "files": {
                "det_10g.onnx": {"path": str(paths["detector"]), "present": required["detector"]},
                "w600k_r50.onnx": {"path": str(paths["recognizer"]), "present": required["recognizer"]},
            },
            "models_present": all(required.values()),
            "manifest_path": str(paths["manifest"]),
            "manifest_present": paths["manifest"].is_file(),
            "license_ack_path": str(paths["license_ack"]),
            "license_ack_present": paths["license_ack"].is_file(),
            "ready": False,
        }
        status["ready"] = bool(status["models_present"] and status["license_ack_present"])
        return status

    def acknowledge_usage(
        self,
        *,
        model_pack: str = DEFAULT_MODEL_PACK,
        accepted_by: str = "admin",
        package_version: str = "unknown",
        source: str = "manual",
        usage_notice: Optional[str] = None,
    ) -> Dict[str, Any]:
        model_pack = self._normalize_model_pack(model_pack)
        resolved = self.path_service.resolve(model_pack)
        directory = resolved["model_dir"]
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_pack": model_pack,
            "source": str(source or "manual"),
            "usage_notice_shown": True,
            "usage_notice": str(usage_notice or self.USAGE_NOTICE),
            "accepted_by": str(accepted_by or "admin"),
            "accepted_at": self._now_iso(),
            "package_version": str(package_version or "unknown"),
            "model_root": str(resolved["model_root"]),
            "model_store": str(resolved["model_store"]),
            "model_root_source": resolved["model_root_source"],
        }
        self._write_json_atomic(directory / "LICENSE_ACK.json", payload)
        manifest = None
        if self._required_files_present(model_pack):
            manifest = self.write_manifest(model_pack=model_pack, source=source)
        self._set_legacy_config_ack(True)
        if manifest is not None:
            payload["manifest_written"] = True
            payload["manifest_path"] = str(directory / "manifest.json")
        else:
            payload["manifest_written"] = False
            payload["manifest_skipped_reason"] = "required_model_files_missing"
        return payload

    def clear_acknowledgement(self, model_pack: str = DEFAULT_MODEL_PACK) -> bool:
        ack_path = self.required_paths(model_pack)["license_ack"]
        try:
            ack_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        self._set_legacy_config_ack(False)
        return True

    def import_model_files(
        self,
        source_dir: Path,
        *,
        model_pack: str = DEFAULT_MODEL_PACK,
        source: str = "manual",
        create_manifest: bool = True,
    ) -> Dict[str, Any]:
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise FaceModelStoreError("source_dir_not_found")
        model_pack = self._normalize_model_pack(model_pack)
        directory = self.model_dir(model_pack)
        directory.mkdir(parents=True, exist_ok=True)
        copied: List[str] = []
        for filename in self.REQUIRED_FILES:
            src = source_dir / filename
            if not src.is_file():
                raise FaceModelStoreError("required_model_file_missing:%s" % filename)
            shutil.copy2(str(src), str(directory / filename))
            copied.append(filename)
        manifest: Optional[Dict[str, Any]] = None
        if create_manifest:
            manifest = self.write_manifest(model_pack=model_pack, source=source, files=copied)
        result = self.status(model_pack)
        result["imported_files"] = copied
        if manifest is not None:
            result["manifest"] = manifest
        return result

    def write_manifest(
        self,
        *,
        model_pack: str = DEFAULT_MODEL_PACK,
        source: str = "manual",
        files: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        model_pack = self._normalize_model_pack(model_pack)
        resolved = self.path_service.resolve(model_pack)
        directory = resolved["model_dir"]
        directory.mkdir(parents=True, exist_ok=True)
        file_names = files if isinstance(files, list) else list(self.REQUIRED_FILES)
        entries = []
        for filename in file_names:
            path = directory / str(filename)
            entry = {"name": str(filename), "path": str(path), "present": path.is_file()}
            if path.is_file():
                entry["size"] = path.stat().st_size
                entry["sha256"] = self._sha256(path)
            entries.append(entry)
        payload: Dict[str, Any] = {
            "model_pack": model_pack,
            "source": str(source or "manual"),
            "distributed_with_package": False,
            "model_root": str(resolved["model_root"]),
            "model_store": str(resolved["model_store"]),
            "model_root_source": resolved["model_root_source"],
            "generated_at": self._now_iso(),
            "files": entries,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        self._write_json_atomic(directory / "manifest.json", payload)
        return payload

    def _required_files_present(self, model_pack: str = DEFAULT_MODEL_PACK) -> bool:
        paths = self.required_paths(model_pack)
        return bool(paths["detector"].is_file() and paths["recognizer"].is_file())

    def _configured_model_root(self) -> Optional[Path]:
        """Compatibility wrapper for callers that inspect configured root state."""
        return self.path_service.configured_model_root()

    def _set_legacy_config_ack(self, acknowledged: bool) -> None:
        config_service = self.config_service
        if config_service is None or not hasattr(config_service, "readConfig") or not hasattr(config_service, "writeConfig"):
            return
        try:
            config = config_service.readConfig()
            if not isinstance(config, dict):
                config = {}
            native = config.setdefault("native_processors", {})
            if not isinstance(native, dict):
                native = {}
                config["native_processors"] = native
            face = native.setdefault("FACE_PROCESSOR", {})
            if not isinstance(face, dict):
                face = {}
                native["FACE_PROCESSOR"] = face
            face["INSIGHTFACE_LICENSE_ACKNOWLEDGED"] = bool(acknowledged)
            if not str(face.get("MODEL_NAME") or "").strip():
                face["MODEL_NAME"] = self.path_service.model_name()
            # Persist the InsightFace root, never its ``models`` child. This
            # prevents a later resolver pass from producing ``models/models``.
            if not str(face.get("MODEL_ROOT") or "").strip():
                face["MODEL_ROOT"] = str(self.path_service.model_root())
            config_service.writeConfig(config)
        except Exception:
            return

    @staticmethod
    def _normalize_model_pack(model_pack: str) -> str:
        value = str(model_pack or "").strip()
        if not value:
            value = FaceModelStoreService.DEFAULT_MODEL_PACK
        value = value.replace("/", "_").replace("\\", "_").replace("..", "_")
        return value

    def _now_iso(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, str(path))
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
