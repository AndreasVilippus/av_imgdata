#!/usr/bin/env python3
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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

    def normalizeConfig(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return self._mergeDefaults(self.defaultConfig(), config if isinstance(config, dict) else {})

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

    def migrateLegacyChecksIgnoreLists(self, config: Dict[str, Any]) -> None:
        if not isinstance(config, dict):
            return
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
