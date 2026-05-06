#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FileAnalysisService:
    """Persistence for the latest file analysis result."""

    FINDING_FILES = {
        "dimension_issues": "dimension_issues.json",
        "duplicate_faces": "duplicate_faces.json",
        "position_deviations": "position_deviations.json",
        "name_conflicts": "name_conflicts.json",
        "face_match": "face_match.json",
        "face_match_candidates": "face_match_candidates.json",
    }

    def __init__(self, result_path: Optional[str] = None, findings_storage_format: str = "json"):
        if result_path:
            self._result_path = Path(result_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._result_path = Path(package_var) / "file_analysis.json"
        self._findings_dir = self._result_path.parent / "analysis_findings"
        self._runtime_dir = self._result_path.parent / "runtime_state"
        self._findings_storage_format = self._normalize_findings_storage_format(findings_storage_format)

    @staticmethod
    def _normalize_findings_storage_format(value: str) -> str:
        normalized = str(value or "json").strip().lower()
        return normalized if normalized in {"json"} else "json"

    def _json_bytes(self, payload: Dict[str, Any], *, pretty: bool = True) -> bytes:
        """
        Serialisiere Payload zu JSON-Bytes.
        """
        if pretty:
            json_str = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        return (json_str + "\n").encode("utf-8")

    def _write_json_if_changed(self, path: Path, payload: Dict[str, Any], *, pretty: bool = True) -> bool:
        """
        Schreibe JSON-Datei nur wenn Inhalt sich ändert.
        Atomar mit temporärer Datei.
        
        Returns:
            True wenn erfolgreich (geschrieben oder unverändert), False bei Fehler
        """
        if not isinstance(payload, dict):
            return False
        
        new_bytes = self._json_bytes(payload, pretty=pretty)
        
        # Prüfe ob Datei existiert und unverändert ist
        if path.exists() and path.is_file():
            try:
                existing_bytes = path.read_bytes()
                if existing_bytes == new_bytes:
                    # Inhalt unverändert - nicht schreiben
                    return True
            except (FileNotFoundError, OSError):
                pass
        
        # Atomar schreiben: temporäre Datei dann replace
        temp_path = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.parent / f"{path.name}.tmp"
            
            # Schreibe in temporäre Datei (atomar durch write_bytes)
            temp_path.write_bytes(new_bytes)
            
            # Ersetze original
            temp_path.replace(path)
        except Exception:
            # Cleanup temporäre Datei falls sie noch existiert
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False
        
        return True

    def readLatestResult(self) -> Dict[str, Any]:
        candidate = self._result_path
        if not candidate.exists() or not candidate.is_file():
            return {}
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def writeLatestResult(self, result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        return self._write_json_if_changed(self._result_path, result, pretty=True)

    def readCheckFindings(self, finding_type: str) -> Dict[str, Any]:
        candidate = self._finding_path(finding_type)
        if not candidate.exists() or not candidate.is_file():
            return {}
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def writeCheckFindings(self, finding_type: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        candidate = self._finding_path(finding_type)
        return self._write_json_if_changed(candidate, payload, pretty=True)

    def appendCheckFindingEntries(self, finding_type: str, entries: List[Dict[str, Any]]) -> bool:
        if not isinstance(entries, list):
            return False

        payload = self.readCheckFindings(finding_type)
        if not isinstance(payload, dict):
            payload = {}
        existing_entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        payload["entries"] = list(existing_entries) + [dict(entry) for entry in entries if isinstance(entry, dict)]
        payload["count"] = len(payload["entries"])
        return self.writeCheckFindings(finding_type, payload)

    def deleteCheckFindings(self, finding_type: str) -> bool:
        candidate = self._finding_path(finding_type)
        if not candidate.exists():
            return True
        try:
            candidate.unlink()
        except Exception:
            return False
        return True

    def readRuntimeState(self, state_type: str, state_key: str) -> Dict[str, Any]:
        candidate = self._runtime_state_path(state_type, state_key)
        if not candidate.exists() or not candidate.is_file():
            return {}
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def writeRuntimeState(self, state_type: str, state_key: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        candidate = self._runtime_state_path(state_type, state_key)
        return self._write_json_if_changed(candidate, payload, pretty=True)

    def deleteRuntimeState(self, state_type: str, state_key: str) -> bool:
        candidate = self._runtime_state_path(state_type, state_key)
        if not candidate.exists():
            return True
        try:
            candidate.unlink()
        except Exception:
            return False
        return True

    def _finding_path(self, finding_type: str) -> Path:
        normalized = str(finding_type or "").strip().lower()
        filename = self.FINDING_FILES.get(normalized)
        if not filename:
            raise ValueError(f"unknown_finding_type: {finding_type}")
        return self._findings_dir / filename

    def _runtime_state_path(self, state_type: str, state_key: str) -> Path:
        normalized_type = str(state_type or "").strip().lower()
        normalized_key = str(state_key or "").strip().lower()
        if not normalized_type or not normalized_key:
            raise ValueError("state_type and state_key are required")
        safe_key = "".join(char for char in normalized_key if char.isalnum() or char in {"-", "_"})
        if not safe_key:
            raise ValueError("invalid_state_key")
        return self._runtime_dir / f"{normalized_type}_{safe_key}.json"
