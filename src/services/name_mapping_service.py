#!/usr/bin/env python3
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class NameMappingService:
    """Persistence and lookup for manual source-name to target-name mappings."""

    def __init__(self, mapping_path: Optional[str] = None):
        self._last_read_error = ""
        if mapping_path:
            self._mapping_path = Path(mapping_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._mapping_path = Path(package_var) / "name_mappings.json"
        
        # Cache für Mappings und Lookup-Index
        self._cache_signature: Optional[Tuple[Any, ...]] = None
        self._cache_mappings: Optional[List[Dict[str, Any]]] = None
        self._cache_index: Optional[Dict[str, Dict[str, Any]]] = None

    @staticmethod
    def _normalize_name_value(name: Any) -> str:
        return " ".join(str(name or "").strip().casefold().split())

    def _mapping_signature(self) -> Tuple[Any, ...]:
        """
        Berechne eine Signatur der Mapping-Datei.
        Enthält Pfad, mtime_ns und Größe.
        """
        try:
            stat = self._mapping_path.stat()
            return (str(self._mapping_path), stat.st_mtime_ns, stat.st_size)
        except (FileNotFoundError, OSError):
            return (str(self._mapping_path), 0, 0)

    def _load_cached(self) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """
        Lade Mappings mit Cache.
        Rückgabe: (mappings_list, lookup_index)
        """
        signature = self._mapping_signature()
        
        # Cache nutzen wenn Signatur identisch
        if (self._cache_mappings is not None and 
            self._cache_index is not None and 
            signature == self._cache_signature):
            return (copy.deepcopy(self._cache_mappings), copy.deepcopy(self._cache_index))
        
        # Cache ungültig - neu laden
        self._last_read_error = ""
        candidate = self._mapping_path
        
        mappings: List[Dict[str, Any]] = []
        
        if candidate.exists() and candidate.is_file():
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception as exc:
                self._last_read_error = str(exc)
                # Fallback: leere Liste
                mappings = []
            else:
                if isinstance(raw, dict):
                    raw_mappings = raw.get("name_mappings")
                else:
                    raw_mappings = raw
                if isinstance(raw_mappings, list):
                    for item in raw_mappings:
                        if not isinstance(item, dict):
                            continue
                        source_name = str(item.get("source_name") or "").strip()
                        target_name = str(item.get("target_name") or "").strip()
                        if not source_name or not target_name:
                            continue
                        mappings.append({
                            "source_name": source_name,
                            "target_name": target_name,
                        })
        
        # Build index für schnelle Lookups
        index: Dict[str, Dict[str, Any]] = {}
        for item in mappings:
            source_key = self._normalize_name_value(item.get("source_name"))
            if source_key:
                index[source_key] = item
        
        # Cache aktualisieren
        self._cache_signature = signature
        self._cache_mappings = mappings
        self._cache_index = index
        
        return (copy.deepcopy(mappings), copy.deepcopy(index))

    def readNameMappings(self) -> List[Dict[str, Any]]:
        mappings, _ = self._load_cached()
        return mappings

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
            # Atomar schreiben: temporäre Datei dann replace
            temp_path = candidate.parent / f"{candidate.name}.tmp"
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump({"name_mappings": mappings}, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
            temp_path.replace(candidate)
        except Exception:
            return False
        
        # Cache invalidieren damit nächster Load neu liest
        self._cache_signature = None
        self._cache_mappings = None
        self._cache_index = None
        return True

    def findNameMapping(self, source_name: str) -> Optional[Dict[str, Any]]:
        source_key = self._normalize_name_value(source_name)
        if not source_key:
            return None
        _, index = self._load_cached()
        return copy.deepcopy(index.get(source_key))

    def saveNameMappingsBatch(self, mappings: List[Dict[str, str]]) -> bool:
        """
        Speichere mehrere Name-Mappings auf einmal.
        Nützlich für Batch-Operationen während Scanläufen.
        
        Args:
            mappings: Liste von {"source_name": str, "target_name": str} Dicts
        
        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        if not isinstance(mappings, list):
            return False
        
        # Aktuellen Cache laden
        current_mappings = self.readNameMappings()
        source_key_to_idx: Dict[str, int] = {}
        
        # Bestehende Mappings indexieren
        for idx, item in enumerate(current_mappings):
            source_key = self._normalize_name_value(item.get("source_name"))
            if source_key:
                source_key_to_idx[source_key] = idx
        
        # Neue Mappings aktualisieren oder hinzufügen
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            source_value = str(mapping.get("source_name") or "").strip()
            target_value = str(mapping.get("target_name") or "").strip()
            if not source_value or not target_value:
                continue
            
            source_key = self._normalize_name_value(source_value)
            if source_key in source_key_to_idx:
                # Update existierendes Mapping
                idx = source_key_to_idx[source_key]
                current_mappings[idx]["source_name"] = source_value
                current_mappings[idx]["target_name"] = target_value
            else:
                # Neues Mapping hinzufügen
                current_mappings.append({
                    "source_name": source_value,
                    "target_name": target_value,
                })
                source_key_to_idx[source_key] = len(current_mappings) - 1
        
        # Atomar schreiben
        candidate = self._mapping_path
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            temp_path = candidate.parent / f"{candidate.name}.tmp"
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump({"name_mappings": current_mappings}, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
            temp_path.replace(candidate)
        except Exception:
            return False
        
        # Cache invalidieren
        self._cache_signature = None
        self._cache_mappings = None
        self._cache_index = None
        return True
