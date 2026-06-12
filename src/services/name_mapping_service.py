#!/usr/bin/env python3
import copy
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from av_imgdata.db.connection import Database, DatabaseError
from av_imgdata.db.migrations import migrate_legacy_name_mappings
from av_imgdata.db.repositories.name_mappings import NameMappingRepository, normalize_name


class NameMappingService:
    """SQLite-backed lookup for manual source-name to target-name mappings."""

    def __init__(self, mapping_path: Optional[str] = None, db_path: Optional[str] = None):
        self._last_read_error = ""
        if mapping_path:
            self._mapping_path = Path(mapping_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._mapping_path = Path(package_var) / "name_mappings.json"
        resolved_db_path = Path(db_path) if db_path else self._mapping_path.parent / "imgdata.sqlite3"
        self._database = Database(str(resolved_db_path))
        self._repository = NameMappingRepository(self._database)
        self._migration_checked = False
        self._cache_signature: Optional[Tuple[Any, ...]] = None
        self._cache_mappings: Optional[List[Dict[str, Any]]] = None
        self._cache_index: Optional[Dict[str, Dict[str, Any]]] = None

    @staticmethod
    def _normalize_name_value(name: Any) -> str:
        return normalize_name(name)

    def _ensure_migrated(self) -> bool:
        if self._migration_checked:
            return True
        try:
            migrate_legacy_name_mappings(self._database, self._mapping_path)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            return False
        self._migration_checked = True
        return True

    def _invalidate_cache(self) -> None:
        self._cache_signature = None
        self._cache_mappings = None
        self._cache_index = None

    def _load_cached(self) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        if self._cache_mappings is not None and self._cache_index is not None:
            return copy.deepcopy(self._cache_mappings), copy.deepcopy(self._cache_index)
        self._last_read_error = ""
        if not self._ensure_migrated():
            return [], {}
        try:
            mappings = self._repository.list_mappings()
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            return [], {}
        index = {
            self._normalize_name_value(item.get("source_name")): item
            for item in mappings
            if self._normalize_name_value(item.get("source_name"))
        }
        self._cache_signature = (str(self._database.path), len(mappings))
        self._cache_mappings = mappings
        self._cache_index = index
        return copy.deepcopy(mappings), copy.deepcopy(index)

    def readNameMappings(self) -> List[Dict[str, Any]]:
        mappings, _ = self._load_cached()
        return mappings

    def listNameMappingsPage(self, *, search: str = "", page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        if not self._ensure_migrated():
            return {"entries": [], "page": 1, "page_size": page_size, "total": 0}
        try:
            return self._repository.list_page(search=search, page=page, page_size=page_size)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            raise

    def deleteNameMapping(self, mapping_id: int) -> bool:
        if not self._ensure_migrated():
            return False
        try:
            deleted = self._repository.delete_mapping(mapping_id)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            raise
        if deleted:
            self._invalidate_cache()
        return deleted

    def updateNameMappingTarget(self, mapping_id: int, target_name: str) -> bool:
        if not self._ensure_migrated():
            return False
        try:
            updated = self._repository.update_mapping_target(mapping_id, target_name)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            raise
        if updated:
            self._invalidate_cache()
        return updated

    def getDebugInfo(self) -> Dict[str, Any]:
        mappings = self.readNameMappings()
        candidate = self._database.path
        return {
            "path": str(candidate),
            "legacy_path": str(self._mapping_path),
            "exists": candidate.exists() and candidate.is_file(),
            "readable": os.access(candidate, os.R_OK) if candidate.exists() else False,
            "count": len(mappings),
            "last_read_error": self._last_read_error,
            "storage": "sqlite",
        }

    def saveNameMapping(self, *, source_name: str, target_name: str) -> bool:
        if not self._ensure_migrated():
            return False
        try:
            saved = self._repository.upsert_mapping(source_name, target_name)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            return False
        if saved:
            self._invalidate_cache()
        return saved

    def findNameMapping(self, source_name: str) -> Optional[Dict[str, Any]]:
        source_key = self._normalize_name_value(source_name)
        if not source_key:
            return None
        _, index = self._load_cached()
        return copy.deepcopy(index.get(source_key))

    def saveNameMappingsBatch(self, mappings: List[Dict[str, str]]) -> bool:
        if not isinstance(mappings, list) or not self._ensure_migrated():
            return False
        try:
            self._repository.upsert_many(mappings)
        except DatabaseError as exc:
            self._last_read_error = str(exc)
            return False
        self._invalidate_cache()
        return True
