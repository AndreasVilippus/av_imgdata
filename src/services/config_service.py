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
        
        # Cache für readMergedConfig()
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
                    "INSTALL_ON_START": True,
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
                "EXIFTOOL_BATCH_READ_ENABLED": False,
                "EXIFTOOL_BATCH_SIZE": 100,
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": True,
                    "MICROSOFT": True,
                    "MWG_REGIONS": True,
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
        
        # Cache nutzen wenn Signatur identisch ist
        if self._merged_config_cache is not None and signature == self._merged_config_cache_signature:
            return copy.deepcopy(self._merged_config_cache)
        
        # Cache ungültig - neu laden und cachen
        config = self.readConfig()
        self.migrateLegacyChecksIgnoreLists(config)
        merged = self._deep_merge_dict(self.defaultConfig(), self.normalizeConfig(config))
        
        # Cache aktualisieren
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
        
        # Cache invalidieren
        self._merged_config_cache = None
        self._merged_config_cache_signature = None
        return True

    @staticmethod
    def _normalize_checks_ignore_list(values: Any) -> list:
        source = values if isinstance(values, list) else []
        normalized = []
        seen = set()
        for value in source:
            token = str(value or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized

    @classmethod
    def checksIgnoreListDefinition(cls, review_type: Any) -> Dict[str, str]:
        normalized_type = str(review_type or "").strip().lower()
        return dict(cls.CHECKS_IGNORE_LISTS.get(normalized_type, {}))

    @classmethod
    def checksIgnoreEnabledKey(cls, review_type: Any) -> str:
        return cls.checksIgnoreListDefinition(review_type).get("enabled_key", "")

    def checksIgnoreListPath(self, review_type: Any) -> Optional[Path]:
        definition = self.checksIgnoreListDefinition(review_type)
        filename = definition.get("filename", "")
        if not filename:
            return None
        return self._config_path.parent / "ignore_lists" / filename

    def readChecksIgnoreList(self, review_type: Any) -> list:
        candidate = self.checksIgnoreListPath(review_type)
        if candidate is None or not candidate.exists() or not candidate.is_file():
            return []
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                values = [line.rstrip("\r\n") for line in handle]
        except Exception:
            return []
        return self._normalize_checks_ignore_list(values)

    def writeChecksIgnoreList(self, review_type: Any, values: Any) -> bool:
        candidate = self.checksIgnoreListPath(review_type)
        if candidate is None:
            return False
        normalized = self._normalize_checks_ignore_list(values)
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                for token in normalized:
                    handle.write(token)
                    handle.write("\n")
        except Exception:
            return False
        
        # Cache invalidieren
        self._merged_config_cache = None
        self._merged_config_cache_signature = None
        return True

    def appendChecksIgnoreToken(self, review_type: Any, token: Any) -> Dict[str, Any]:
        normalized_type = str(review_type or "").strip().lower()
        normalized_token = str(token or "").strip()
        if not normalized_type or not normalized_token:
            return {"saved": False, "reason": "invalid_ignore_entry"}
        current = self.readChecksIgnoreList(normalized_type)
        updated = self._normalize_checks_ignore_list([*current, normalized_token])
        saved = self.writeChecksIgnoreList(normalized_type, updated)
        return {
            "saved": bool(saved),
            "count": len(updated),
            "token": normalized_token,
            "path": str(self.checksIgnoreListPath(normalized_type) or ""),
        }

    def clearChecksIgnoreList(self, review_type: Any) -> bool:
        result = self.writeChecksIgnoreList(review_type, [])
        return result

    def getChecksIgnoreListsStatus(self) -> Dict[str, Dict[str, Any]]:
        status: Dict[str, Dict[str, Any]] = {}
        for review_type in self.CHECKS_IGNORE_LISTS:
            candidate = self.checksIgnoreListPath(review_type)
            entries = self.readChecksIgnoreList(review_type)
            status[review_type] = {
                "count": len(entries),
                "path": str(candidate) if candidate is not None else "",
            }
        return status

    def migrateLegacyChecksIgnoreLists(self, config: Dict[str, Any]) -> None:
        if not isinstance(config, dict):
            return
        analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks = analysis.get("CHECKS") if isinstance(analysis.get("CHECKS"), dict) else {}
        for review_type, definition in self.CHECKS_IGNORE_LISTS.items():
            legacy_values = self._normalize_checks_ignore_list(checks.get(definition["legacy_key"]))
            if not legacy_values:
                continue
            current_values = self.readChecksIgnoreList(review_type)
            merged_values = self._normalize_checks_ignore_list([*current_values, *legacy_values])
            self.writeChecksIgnoreList(review_type, merged_values)

    def _config_signature(self) -> Tuple[Any, ...]:
        """
        Berechne eine Signatur aller relevanten Config-Dateien.
        Enthält mtime und Größe der Hauptconfig-Datei sowie aller Ignore-List-Dateien.
        """
        signature_parts: list[Any] = [
            str(self._config_path),
        ]
        
        # Hauptconfig-Datei
        try:
            stat = self._config_path.stat()
            signature_parts.append((stat.st_mtime_ns, stat.st_size))
        except (FileNotFoundError, OSError):
            signature_parts.append((0, 0))
        
        # Ignore-List-Dateien
        for review_type in sorted(self.CHECKS_IGNORE_LISTS.keys()):
            candidate = self.checksIgnoreListPath(review_type)
            try:
                stat = candidate.stat()
                signature_parts.append((review_type, stat.st_mtime_ns, stat.st_size))
            except (FileNotFoundError, OSError, AttributeError):
                signature_parts.append((review_type, 0, 0))
        
        return tuple(signature_parts)

    @classmethod
    def normalizeConfig(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        root = cls._deep_merge_dict(cls.defaultConfig(), config if isinstance(config, dict) else {})
        analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
        checks = analysis.get("CHECKS") if isinstance(analysis.get("CHECKS"), dict) else {}
        analysis["CHECKS"] = {
            "DUPLICATE_FACES": bool(checks.get("DUPLICATE_FACES", True)),
            "POSITION_DEVIATIONS": bool(checks.get("POSITION_DEVIATIONS", True)),
            "POSITION_DEVIATIONS_INCLUDE_PHOTOS": bool(checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS", True)),
            "DIMENSION_ISSUES": bool(checks.get("DIMENSION_ISSUES", True)),
            "NAME_CONFLICTS": bool(checks.get("NAME_CONFLICTS", True)),
            "NAME_CONFLICTS_INCLUDE_PHOTOS": bool(checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS", True)),
            "NAME_CONFLICT_OVERLAP_THRESHOLD": cls._clamp_float(checks.get("NAME_CONFLICT_OVERLAP_THRESHOLD", 0.75), 0.0, 1.0, 0.75),
            "NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH": bool(checks.get("NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH", True)),
            "NAME_CONFLICT_MIN_BEST_MATCH_MARGIN": cls._clamp_float(checks.get("NAME_CONFLICT_MIN_BEST_MATCH_MARGIN", 0.05), 0.0, 1.0, 0.05),
            "SINGLE_SOURCE_OF_TRUTH": str(checks.get("SINGLE_SOURCE_OF_TRUTH", "")),
        }
        root["analysis"] = analysis

        runtime = root.get("runtime") if isinstance(root.get("runtime"), dict) else {}
        findings_storage_format = str(runtime.get("FINDINGS_STORAGE_FORMAT", "json") or "").strip().lower()
        if findings_storage_format not in {"json"}:
            findings_storage_format = "json"
        runtime["FINDINGS_STORAGE_FORMAT"] = findings_storage_format
        root["runtime"] = runtime

        debug = root.get("debug") if isinstance(root.get("debug"), dict) else {}
        debug["IO_METRICS_ENABLED"] = bool(debug.get("IO_METRICS_ENABLED", False))
        root["debug"] = debug

        review = root.get("review") if isinstance(root.get("review"), dict) else {}
        review_options = review.get("OPTIONS") if isinstance(review.get("OPTIONS"), dict) else {}
        review_ignore = review.get("CHECKS_IGNORE_LISTS") if isinstance(review.get("CHECKS_IGNORE_LISTS"), dict) else {}
        review["OPTIONS"] = {
            **review_options,
            "DUPLICATE_FACE_SUGGESTIONS": bool(review_options.get("DUPLICATE_FACE_SUGGESTIONS", True)),
        }
        review["CHECKS_IGNORE_LISTS"] = {
            **review_ignore,
            "DUPLICATE_FACES_ENABLED": bool(review_ignore.get("DUPLICATE_FACES_ENABLED", True)),
            "POSITION_DEVIATIONS_ENABLED": bool(review_ignore.get("POSITION_DEVIATIONS_ENABLED", True)),
            "NAME_CONFLICTS_ENABLED": bool(review_ignore.get("NAME_CONFLICTS_ENABLED", True)),
        }
        root["review"] = review

        files = root.get("files") if isinstance(root.get("files"), dict) else {}
        use_exiftool_for_sidecars = bool(files.get("USE_EXIFTOOL_FOR_SIDECARS", files.get("USE_EXIFTOOL_FOR_SIDECARDS", False)))
        sidecar_exiftool_fallback_enabled = bool(files.get("SIDECAR_EXIFTOOL_FALLBACK_ENABLED", False))
        files["USE_EXIFTOOL_FOR_SIDECARS"] = use_exiftool_for_sidecars
        files["SIDECAR_EXIFTOOL_FALLBACK_ENABLED"] = sidecar_exiftool_fallback_enabled
        sidcar_read_mode = str(files.get("SIDECAR_READ_MODE", "") or "").strip().lower()
        if sidcar_read_mode not in {"direct_first", "direct_only", "exiftool_first", "exiftool_only"}:
            sidcar_read_mode = "direct_first" if (use_exiftool_for_sidecars or sidecar_exiftool_fallback_enabled) else "direct_only"
        files["SIDECAR_READ_MODE"] = sidcar_read_mode
        files["EMBEDDED_XMP_FULL_SCAN_ENABLED"] = bool(files.get("EMBEDDED_XMP_FULL_SCAN_ENABLED", False))
        files["EMBEDDED_XMP_FULL_SCAN_MAX_BYTES"] = cls._clamp_int(files.get("EMBEDDED_XMP_FULL_SCAN_MAX_BYTES", 67108864), 1048576, 536870912, 67108864)
        root["files"] = files

        return root

    @staticmethod
    def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return int(default)
        if numeric < minimum:
            return int(minimum)
        if numeric > maximum:
            return int(maximum)
        return numeric

    @staticmethod
    def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return float(default)
        if numeric < minimum:
            return float(minimum)
        if numeric > maximum:
            return float(maximum)
        return numeric

    @staticmethod
    def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = ConfigService._deep_merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged
