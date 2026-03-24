#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigService:
    """Runtime package configuration persistence."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self._config_path = Path(config_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._config_path = Path(package_var) / "config.json"

    @staticmethod
    def defaultConfig() -> Dict[str, Any]:
        return {
            "photos": {
                "MAX_PHOTOS_PERSONS": 5000,
            },
            "files": {
                "USE_EXIFTOOL": False,
                "PATHEXIFTOOL": "exiftool",
                "IMAGE_EXTENSIONS": ["jpg", "jpeg", "tif", "tiff", "png", "heic", "heif", "dng", "cr2", "cr3", "nef", "nrw", "arw", "orf", "rw2", "raf", "pef"],
            },
            "metadata": {
                "SCHEMAS": {
                    "ACD": True,
                    "MICROSOFT": True,
                    "MWG_REGIONS": True,
                },
            },
        }

    def readMergedConfig(self) -> Dict[str, Any]:
        return self._deep_merge_dict(self.defaultConfig(), self.readConfig())

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
        candidate = self._config_path
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            return False
        return True

    @staticmethod
    def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = ConfigService._deep_merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged
