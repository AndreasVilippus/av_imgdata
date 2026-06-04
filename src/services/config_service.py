#!/usr/bin/env python3
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

    @staticmethod
    def defaultConfig() -> Dict[str, Any]:
        return {
            "photos": {
                "MAX_PHOTOS_PERSONS": 5000,
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
                    "WHEELHOUSE_MANIFEST_URL": "https://github.com/AndreasVilippus/av_imgdata-wheelhouse/releases/download/dsm7-x86_64-python38-2026.04.23/wheelhouse-manifest.json",
                    "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                    "MODEL_ROOT": "",
                    "MODEL_NAME": "",
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
            "runtime": {
                "FINDINGS_STORAGE_FORMAT": "json",
            },
            "debug": {
                "IO_METRICS_ENABLED": False,
                "BACKEND_DEBUG_ENABLED": False,
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

    @classmethod
    def normalizeConfig(cls, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = cls._mergeDefaults(cls.defaultConfig(), config if isinstance(config, dict) else {})
        cls._normalizeConfigValues(normalized)
        return normalized

    def _config_signature(self) -> Tuple[Any, ...]:
        ignore_signature: List[Tuple[str, Optional[int], Optional[int]]] = []
        for spec in self.CHECKS_IGNORE_LISTS.values():
            path = self._checks_ignore_list_path_for_spec(spec)
            try:
                stat = path.stat()
                ignore_signature.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                ignore_signature.append((str(path), None, None))
        try:
            stat = self._config_path.stat()
            return (str(self._config_path), stat.st_mtime_ns, stat.st_size, tuple(ignore_signature))
        except OSError:
            return (str(self._config_path), None, None, tuple(ignore_signature))

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

        runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
        storage_format = str(runtime.get("FINDINGS_STORAGE_FORMAT") or "").strip().lower()
        runtime["FINDINGS_STORAGE_FORMAT"] = storage_format if storage_format in {"json"} else "json"

        debug = config.get("debug", {}) if isinstance(config.get("debug"), dict) else {}
        debug["BACKEND_DEBUG_ENABLED"] = bool(debug.get("BACKEND_DEBUG_ENABLED"))
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
        path = self._checks_ignore_list_path_for_spec(spec)
        try:
            with path.open("r", encoding="utf-8") as handle:
                return self._normalize_ignore_tokens(handle.readlines())
        except OSError:
            return []

    def writeChecksIgnoreList(self, review_type: Any, tokens: Any) -> bool:
        spec = self._checks_ignore_list_spec(review_type)
        if not spec:
            return False
        path = self._checks_ignore_list_path_for_spec(spec)
        normalized = self._normalize_ignore_tokens(tokens if isinstance(tokens, list) else [])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                for token in normalized:
                    handle.write(f"{token}\n")
        except OSError:
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
