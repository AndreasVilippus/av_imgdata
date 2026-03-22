#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class NameMappingService:
    """Persistence and lookup for manual source-name to target-name mappings."""

    def __init__(self, mapping_path: Optional[str] = None):
        self._last_read_error = ""
        if mapping_path:
            self._mapping_path = Path(mapping_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._mapping_path = Path(package_var) / "name_mappings.json"

    @staticmethod
    def _normalize_name_value(name: Any) -> str:
        return " ".join(str(name or "").strip().casefold().split())

    def readNameMappings(self) -> List[Dict[str, Any]]:
        self._last_read_error = ""
        candidate = self._mapping_path
        if not candidate.exists() or not candidate.is_file():
            return []
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception as exc:
            self._last_read_error = str(exc)
            return []

        if isinstance(raw, dict):
            mappings = raw.get("name_mappings")
        else:
            mappings = raw
        if not isinstance(mappings, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for item in mappings:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or "").strip()
            target_name = str(item.get("target_name") or "").strip()
            if not source_name or not target_name:
                continue
            normalized.append(
                {
                    "source_name": source_name,
                    "target_name": target_name,
                }
            )
        return normalized

    def getDebugInfo(self) -> Dict[str, Any]:
        mappings = self.readNameMappings()
        candidate = self._mapping_path
        return {
            "path": str(candidate),
            "exists": candidate.exists() and candidate.is_file(),
            "readable": os.access(candidate, os.R_OK) if candidate.exists() else False,
            "count": len(mappings),
            "last_read_error": self._last_read_error,
        }

    def saveNameMapping(self, *, source_name: str, target_name: str) -> bool:
        source_value = str(source_name or "").strip()
        target_value = str(target_name or "").strip()
        if not source_value or not target_value:
            return False

        mappings = self.readNameMappings()
        source_key = self._normalize_name_value(source_value)
        updated = False
        for item in mappings:
            if self._normalize_name_value(item.get("source_name")) != source_key:
                continue
            item["source_name"] = source_value
            item["target_name"] = target_value
            updated = True
            break

        if not updated:
            mappings.append(
                {
                    "source_name": source_value,
                    "target_name": target_value,
                }
            )

        candidate = self._mapping_path
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                json.dump({"name_mappings": mappings}, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            return False
        return True

    def findNameMapping(self, source_name: str) -> Optional[Dict[str, Any]]:
        source_key = self._normalize_name_value(source_name)
        if not source_key:
            return None
        for item in self.readNameMappings():
            if self._normalize_name_value(item.get("source_name")) == source_key:
                return item
        return None
