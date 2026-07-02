#!/usr/bin/env python3
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from av_imgdata.db.connection import Database
from av_imgdata.db.migrations import migrate_runtime_persistence
from av_imgdata.db.repositories.check_suppressions import CheckSuppressionRepository


class ConfigService:
    """Runtime package configuration persistence."""

    CHECKS_IGNORE_LISTS = {
        "duplicate_faces": {
            "legacy_key": "IGNORE_LIST_DUPLICATE_FACES",
            "enabled_key": "DUPLICATE_FACES_ENABLED",
            "filename": "checks_ignore_duplicate_faces.txt",
        },
        "position_deviations": {
            "legacy_key": "IGNORE_LIST_POSITION_DEVIATIONS",
            "enabled_key": "POSITION_DEVIATIONS_ENABLED",
            "filename": "checks_ignore_position_deviations.txt",
        },
        "name_conflicts": {
            "legacy_key": "IGNORE_LIST_NAME_CONFLICTS",
            "enabled_key": "NAME_CONFLICTS_ENABLED",
            "filename": "checks_ignore_name_conflicts.txt",
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self._config_path = Path(config_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._config_path = Path(package_var) / "config.json"

        self._merged_config_cache: Optional[Dict[str, Any]] = None
        self._merged_config_cache_signature: Optional[Tuple[Any, ...]] = None
        self._database = Database(str(self._config_path.parent / "imgdata.sqlite3"))
        self._check_suppressions = CheckSuppressionRepository(self._database)
        self._runtime_migration_checked = False

    @staticmethod
    def defaultConfig() -> Dict[str, Any]:
        return {
            "photos": {
                "MAX_PHOTOS_PERSONS": 5000,
                "REINDEX_MISSING_ITEMS": False,
            },
            "face_match": {
                "FILE_MATCH_SOURCE_SCOPE": "both",
                "PERSON_SORT_ORDER": "id_desc",
            },
            "pip_packages": {
                "INSIGHTFACE": {
                    "ENABLED": False,
                    "INSTALL_ON_START": False,
                    "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                    "WHEELHOUSE_ENABLED": True,
                    "WHEELHOUSE_MANIFEST_URL": "https://github.com/AndreasVilippus/av_imgdata-wheelhouse/releases/download/dsm7-x86_64-python38-2026.06.22/wheelhouse-manifest.json",
                    "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                    "MODEL_ROOT": "",
                    "MODEL_NAME": "",
                },
            },
            "native_processors": {
                "FACE_PROCESSOR": {
                    "ENABLED": True,
                    "PATH": "bin/av-imgdata-face-processor",
                    "MODEL_ROOT": "",
                    "MODEL_NAME": "",
                    "TIMEOUT_SECONDS": 120,
                    "MAX_IMAGE_BYTES": 67108864,
                    "ORT_INTRA_THREADS": 0,
                    "ORT_GRAPH_OPT_LEVEL": "all",
                    "INSIGHTFACE_LICENSE_ACKNOWLEDGED": False,
                },
            },
            "files": {
                "USE_EXIFTOOL": False,
                "CHECK_EXIFTOOL_UPDATES": True,
                "USE_EXIFTOOL_FOR_SIDECARS": False,
                "PREFER_EXIFTOOL_FOR_CONTEXT": False,
                "PATHEXIFTOOL": "exiftool",
                "USE_MANUAL_PATHEXIFTOOL": False,
                "MANUAL_PATHEXIFTOOL": "",
                "IMAGE_EXTENSIONS_NATIVE_ONLY": True,
                "IMAGE_EXTENSIONS": ["jpg", "jpeg", "tif", "tiff", "png", "heic", "heif", "dng", "cr2", "cr3", "nef", "nrw", "arw", "orf", "rw2", "raf", "pef"],
                "EXIFTOOL_IMAGE_EXTENSIONS": [],
                "SIDECAR_LOOKUP_VARIANTS": [
                    "same_dir_stem",
                    "same_dir_filename",
                    "xmp_dir_stem",
                    "xmp_dir_filename",
                ],
                "SIDECAR_READ_MODE": "direct_first",
                "SIDECAR_EXIFTOOL_FALLBACK_ENABLED": False,
                "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
                "EMBEDDED_XMP_FULL_SCAN_MAX_BYTES": 67108864,
                "EXIFTOOL_PERSISTENT_ENABLED": True,
                "EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS": 30,
                "IMAGE_DECODER_ENABLED": True,
                "IMAGE_DECODER_EXTENSIONS": ["heic", "heif"],
                "IMAGE_DECODER_ORDER": ["pillow-heif", "heif-convert", "magick", "ffmpeg", "convert"],
                "IMAGE_DECODER_MAX_EDGE": 4096,
                "RECOGNITION_IMAGE_MAX_EDGE": 4096,
                "IMAGE_DECODER_TIMEOUT_SECONDS": 30,
                "PATH_HEIF_CONVERT": "heif-convert",
                "PATH_IMAGEMAGICK": "magick",
                "PATH_FFMPEG": "ffmpeg",
                "PATH_CONVERT": "convert",
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": True,
                    "MICROSOFT": True,
                    "MWG_REGIONS": True,
                    "IPTC_EXT_REGIONS": True,
                },
            },
            "analysis": {
                "CHECKS": {
                    "DUPLICATE_FACES": True,
                    "POSITION_DEVIATIONS": True,
                    "POSITION_DEVIATIONS_INCLUDE_PHOTOS": True,
                    "DIMENSION_ISSUES": True,
                    "NAME_CONFLICTS": True,
                    "NAME_CONFLICTS_INCLUDE_PHOTOS": True,
                    "NAME_CONFLICT_OVERLAP_THRESHOLD": 0.75,
                    "NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH": True,
                    "NAME_CONFLICT_MIN_BEST_MATCH_MARGIN": 0.05,
                    "SINGLE_SOURCE_OF_TRUTH": "",
                },
            },
            "debug": {
                "IO_METRICS_ENABLED": False,
                "BACKEND_DEBUG_ENABLED": False,
                "BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED": False,
                "BACKEND_DEBUG_LOG_PATH": "",
                "BACKEND_DEBUG_LOG_MAX_BYTES": 1048576,
                "BACKEND_DEBUG_LOG_BACKUPS": 3,
            },
            "review": {
                "OPTIONS": {
                    "DUPLICATE_FACE_SUGGESTIONS": True,
                },
                "CHECKS_IGNORE_LISTS": {
                    "DUPLICATE_FACES_ENABLED": True,
                    "POSITION_DEVIATIONS_ENABLED": True,
                    "NAME_CONFLICTS_ENABLED": True,
                },
            },
        }

    def readMergedConfig(self) -> Dict[str, Any]:
        signature = self._config_signature()
        if self._merged_config_cache is not None and signature == self._merged_config_cache_signature:
            return copy.deepcopy(self._merged_config_cache)

        config = self.readConfig()
        self.migrateLegacyChecksIgnoreLists(config)
        merged = self.normalizeConfig(config)

        self._merged_config_cache = merged
        self._merged_config_cache_signature = signature
        return copy.deepcopy(merged)

    def readConfig(self) -> Dict[str, Any]:
        candidate = self._config_path
        if not candidate.exists() or not candidate.is_file():
            return {}
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        except Exception:
            return {}
        return config if isinstance(config, dict) else {}

    def writeConfig(self, config: Dict[str, Any]) -> bool:
        if not isinstance(config, dict):
            return False
        self.migrateLegacyChecksIgnoreLists(config)
        config = self.normalizeConfig(config)
        candidate = self._config_path
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            return False

        self._merged_config_cache = None
        self._merged_config_cache_signature = None
        return True

    def ensureInstallOnStartConfig(self) -> bool:
        config = self.readConfig()
        if not isinstance(config, dict):
            return False
        pip_packages = config.get("pip_packages") if isinstance(config.get("pip_packages"), dict) else {}
        insightface = pip_packages.get("INSIGHTFACE") if isinstance(pip_packages.get("INSIGHTFACE"), dict) else {}
        if not bool(insightface.get("INSTALL_ON_START", False)):
            return False

        defaults = self.defaultConfig()["pip_packages"]["INSIGHTFACE"]
        changed = False
        for key in ("WHEELHOUSE_ENABLED", "WHEELHOUSE_MANIFEST_URL", "WHEELHOUSE_TARGET", "REQUIREMENTS_FILE"):
            default_value = defaults.get(key)
            if insightface.get(key) != default_value:
                insightface[key] = default_value
                changed = True

        if not changed:
            return False

        pip_packages["INSIGHTFACE"] = insightface
        config["pip_packages"] = pip_packages
        return self.writeConfig(config)

    @classmethod
    def normalizeConfig(cls, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = cls._mergeDefaults(cls.defaultConfig(), config if isinstance(config, dict) else {})
        normalized.pop("runtime", None)
        cls._normalizeConfigValues(normalized)
        return normalized

    def _config_signature(self) -> Tuple[Any, ...]:
        try:
            stat = self._config_path.stat()
            return (str(self._config_path), stat.st_mtime_ns, stat.st_size)
        except OSError:
            return (str(self._config_path), None, None)

    @classmethod
    def _mergeDefaults(cls, defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(defaults)
        cls._deepUpdateKnownKeys(result, current)
        return result

    @classmethod
    def _deepUpdateKnownKeys(cls, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if key not in target:
                continue
            if isinstance(target[key], dict) and isinstance(value, dict):
                cls._deepUpdateKnownKeys(target[key], value)
            else:
                target[key] = value

    @classmethod
    def _normalizeConfigValues(cls, config: Dict[str, Any]) -> None:
        files = config.get("files", {}) if isinstance(config.get("files"), dict) else {}
        sidecar_mode = str(files.get("SIDECAR_READ_MODE") or "").strip().lower()
        if sidecar_mode not in {"direct_first", "direct_only", "exiftool_first", "exiftool_only"}:
            sidecar_mode = "direct_first"
        files["SIDECAR_READ_MODE"] = sidecar_mode
        files["EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS"] = cls._clamp_int(
            files.get("EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS"),
            default=30,
            minimum=1,
            maximum=300,
        )
        files["IMAGE_DECODER_ENABLED"] = bool(files.get("IMAGE_DECODER_ENABLED", True))
        files["IMAGE_DECODER_TIMEOUT_SECONDS"] = cls._clamp_int(
            files.get("IMAGE_DECODER_TIMEOUT_SECONDS"),
            default=30,
            minimum=1,
            maximum=300,
        )
        files["IMAGE_DECODER_MAX_EDGE"] = cls._clamp_int(
            files.get("IMAGE_DECODER_MAX_EDGE"),
            default=4096,
            minimum=0,
            maximum=20000,
        )
        files["RECOGNITION_IMAGE_MAX_EDGE"] = cls._clamp_int(
            files.get("RECOGNITION_IMAGE_MAX_EDGE"),
            default=4096,
            minimum=0,
            maximum=20000,
        )
        files["IMAGE_DECODER_EXTENSIONS"] = cls._normalizeStringList(
            files.get("IMAGE_DECODER_EXTENSIONS"),
            default=["heic", "heif"],
            lowercase=True,
            strip_prefix=".",
        )
        decoder_order = cls._normalizeStringList(
            files.get("IMAGE_DECODER_ORDER"),
            default=["pillow-heif", "heif-convert", "magick", "ffmpeg", "convert"],
            lowercase=True,
        )
        allowed_decoders = {"pillow-heif", "heif-convert", "magick", "ffmpeg", "convert"}
        files["IMAGE_DECODER_ORDER"] = [decoder for decoder in decoder_order if decoder in allowed_decoders]

        photos = config.get("photos", {}) if isinstance(config.get("photos"), dict) else {}
        photos["REINDEX_MISSING_ITEMS"] = bool(photos.get("REINDEX_MISSING_ITEMS", False))

        native_processors = config.get("native_processors", {}) if isinstance(config.get("native_processors"), dict) else {}
        face_processor = native_processors.get("FACE_PROCESSOR", {}) if isinstance(native_processors.get("FACE_PROCESSOR"), dict) else {}
        face_processor["ENABLED"] = bool(face_processor.get("ENABLED", False))
        face_processor["TIMEOUT_SECONDS"] = cls._clamp_int(
            face_processor.get("TIMEOUT_SECONDS"),
            default=120,
            minimum=1,
            maximum=3600,
        )
        face_processor["MAX_IMAGE_BYTES"] = cls._clamp_int(
            face_processor.get("MAX_IMAGE_BYTES"),
            default=67108864,
            minimum=1048576,
            maximum=1073741824,
        )
        face_processor["ORT_INTRA_THREADS"] = cls._clamp_int(
            face_processor.get("ORT_INTRA_THREADS"),
            default=0,
            minimum=0,
            maximum=64,
        )
        graph_opt_level = str(face_processor.get("ORT_GRAPH_OPT_LEVEL") or "all").strip().lower()
        if graph_opt_level not in {"disable", "basic", "extended", "all"}:
            graph_opt_level = "all"
        face_processor["ORT_GRAPH_OPT_LEVEL"] = graph_opt_level
        face_processor["INSIGHTFACE_LICENSE_ACKNOWLEDGED"] = bool(face_processor.get("INSIGHTFACE_LICENSE_ACKNOWLEDGED", False))
        native_processors["FACE_PROCESSOR"] = face_processor
        config["native_processors"] = native_processors

        debug = config.get("debug", {}) if isinstance(config.get("debug"), dict) else {}
        debug["BACKEND_DEBUG_ENABLED"] = bool(debug.get("BACKEND_DEBUG_ENABLED"))
        debug["BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED"] = bool(debug.get("BACKEND_DEBUG_PYTHON_BRIDGE_ENABLED"))
        debug["IO_METRICS_ENABLED"] = bool(debug.get("IO_METRICS_ENABLED"))
        debug["BACKEND_DEBUG_LOG_MAX_BYTES"] = cls._clamp_int(
            debug.get("BACKEND_DEBUG_LOG_MAX_BYTES"),
            default=1048576,
            minimum=65536,
            maximum=10485760,
        )
        debug["BACKEND_DEBUG_LOG_BACKUPS"] = cls._clamp_int(
            debug.get("BACKEND_DEBUG_LOG_BACKUPS"),
            default=3,
            minimum=0,
            maximum=10,
        )

        checks = config.get("analysis", {}).get("CHECKS", {}) if isinstance(config.get("analysis"), dict) else {}
        if isinstance(checks, dict):
            checks["NAME_CONFLICT_OVERLAP_THRESHOLD"] = cls._clamp_float(
                checks.get("NAME_CONFLICT_OVERLAP_THRESHOLD"),
                default=0.75,
                minimum=0.0,
                maximum=1.0,
            )
            checks["NAME_CONFLICT_MIN_BEST_MATCH_MARGIN"] = cls._clamp_float(
                checks.get("NAME_CONFLICT_MIN_BEST_MATCH_MARGIN"),
                default=0.05,
                minimum=0.0,
                maximum=1.0,
            )
            checks["NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"] = bool(checks.get("NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"))

    @staticmethod
    def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    @staticmethod
    def _normalizeStringList(
        value: Any,
        *,
        default: List[str],
        lowercase: bool = False,
        strip_prefix: str = "",
    ) -> List[str]:
        source = value if isinstance(value, list) else default
        normalized: List[str] = []
        for item in source:
            text = str(item or "").strip()
            if not text:
                continue
            if strip_prefix:
                text = text.lstrip(strip_prefix)
            if lowercase:
                text = text.lower()
            if text and text not in normalized:
                normalized.append(text)
        return normalized or list(default)

    @staticmethod
    def _clamp_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def migrateLegacyChecksIgnoreLists(self, config: Dict[str, Any]) -> None:
        if not isinstance(config, dict):
            return
        analysis = config.get("analysis")
        checks = analysis.get("CHECKS") if isinstance(analysis, dict) else None
        if isinstance(checks, dict):
            for review_type, spec in self.CHECKS_IGNORE_LISTS.items():
                legacy_key = spec["legacy_key"]
                legacy_tokens = checks.pop(legacy_key, None)
                if isinstance(legacy_tokens, list):
                    existing = self.readChecksIgnoreList(review_type)
                    self.writeChecksIgnoreList(review_type, existing + legacy_tokens)
        review = config.setdefault("review", {})
        if not isinstance(review, dict):
            return
        ignore_lists = review.setdefault("CHECKS_IGNORE_LISTS", {})
        if not isinstance(ignore_lists, dict):
            return
        for spec in self.CHECKS_IGNORE_LISTS.values():
            legacy_key = spec["legacy_key"]
            enabled_key = spec["enabled_key"]
            if legacy_key not in review:
                continue
            ignore_lists[enabled_key] = bool(review.pop(legacy_key))

    def readChecksIgnoreList(self, review_type: Any) -> List[str]:
        spec = self._checks_ignore_list_spec(review_type)
        if not spec:
            return []
        self._ensure_runtime_migrated()
        return self._check_suppressions.list_tokens(str(review_type or ""))

    def writeChecksIgnoreList(self, review_type: Any, tokens: Any) -> bool:
        spec = self._checks_ignore_list_spec(review_type)
        if not spec:
            return False
        normalized = self._normalize_ignore_tokens(tokens if isinstance(tokens, list) else [])
        self._ensure_runtime_migrated()
        if not self._check_suppressions.replace(str(review_type or ""), normalized):
            return False
        self._invalidate_cache()
        return True

    def appendChecksIgnoreToken(self, review_type: Any, token: Any) -> Dict[str, Any]:
        normalized_token = str(token or "").strip()
        if not normalized_token:
            return {"saved": False, "token": "", "count": len(self.readChecksIgnoreList(review_type))}
        tokens = self.readChecksIgnoreList(review_type)
        if normalized_token not in tokens:
            tokens.append(normalized_token)
            saved = self.writeChecksIgnoreList(review_type, tokens)
        else:
            saved = True
        return {"saved": bool(saved), "token": normalized_token, "count": len(tokens)}

    def clearChecksIgnoreList(self, review_type: Any) -> bool:
        return self.writeChecksIgnoreList(review_type, [])

    def getChecksIgnoreListsStatus(self) -> Dict[str, Dict[str, Any]]:
        statuses: Dict[str, Dict[str, Any]] = {}
        for review_type, spec in self.CHECKS_IGNORE_LISTS.items():
            statuses[review_type] = {
                "count": len(self.readChecksIgnoreList(review_type)),
                "path": str(self._database.path),
                "storage": "sqlite",
            }
        return statuses

    @classmethod
    def checksIgnoreEnabledKey(cls, review_type: Any) -> str:
        spec = cls.CHECKS_IGNORE_LISTS.get(str(review_type or "").strip().lower())
        return spec["enabled_key"] if spec else ""

    def _checks_ignore_list_spec(self, review_type: Any) -> Optional[Dict[str, str]]:
        normalized = str(review_type or "").strip().lower()
        return self.CHECKS_IGNORE_LISTS.get(normalized)

    def _checks_ignore_list_path_for_spec(self, spec: Dict[str, str]) -> Path:
        return self._config_path.parent / "ignore_lists" / spec["filename"]

    @staticmethod
    def _normalize_ignore_tokens(tokens: Any) -> List[str]:
        result: List[str] = []
        for token in tokens if isinstance(tokens, list) else []:
            normalized = str(token or "").strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _invalidate_cache(self) -> None:
        self._merged_config_cache = None
        self._merged_config_cache_signature = None

    def _ensure_runtime_migrated(self) -> None:
        if self._runtime_migration_checked:
            return
        migrate_runtime_persistence(self._database, self._config_path.parent)
        self._runtime_migration_checked = True
