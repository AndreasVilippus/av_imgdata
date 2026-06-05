#!/usr/bin/env python3
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import RLock, local
from typing import Any, Dict, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Synology and the test environment provide fcntl.
    fcntl = None


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
        self._finding_locks_guard = RLock()
        self._finding_locks: Dict[str, RLock] = {}
        self._finding_lock_local = local()

    @contextmanager
    def lockCheckFindings(self, finding_type: str):
        candidate = self._finding_path(finding_type)
        key = str(candidate)
        with self._finding_locks_guard:
            thread_lock = self._finding_locks.setdefault(key, RLock())

        with thread_lock:
            depths = getattr(self._finding_lock_local, "depths", {})
            handles = getattr(self._finding_lock_local, "handles", {})
            depth = int(depths.get(key) or 0)
            if depth == 0:
                handle = None
                try:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    lock_path = candidate.parent / f".{candidate.name}.lock"
                    handle = lock_path.open("a+")
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                except OSError:
                    if handle is not None:
                        handle.close()
                    handle = None
                handles[key] = handle
            depths[key] = depth + 1
            self._finding_lock_local.depths = depths
            self._finding_lock_local.handles = handles
            try:
                yield
            finally:
                remaining_depth = int(depths.get(key) or 1) - 1
                if remaining_depth > 0:
                    depths[key] = remaining_depth
                else:
                    depths.pop(key, None)
                    handle = handles.pop(key, None)
                    if handle is not None:
                        if fcntl is not None:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        handle.close()

    @staticmethod
    def _normalize_findings_storage_format(value: str) -> str:
        normalized = str(value or "json").strip().lower()
        return normalized if normalized in {"json"} else "json"

    def _finding_status_path(self, finding_type: str) -> Path:
        candidate = self._finding_path(finding_type)
        return candidate.with_name(f"{candidate.stem}.status{candidate.suffix}")

    @staticmethod
    def _check_findings_status_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        status = {key: value for key, value in payload.items() if key not in {"entries", "paths"}}
        try:
            status["count"] = max(0, int(status.get("count") or 0))
        except (TypeError, ValueError):
            status["count"] = 0
        if "count" not in payload:
            entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
            paths = payload.get("paths") if isinstance(payload.get("paths"), list) else []
            status["count"] = len(entries) if entries else len(paths)
        return status

    @staticmethod
    def _skip_json_value(text: str, start: int) -> int:
        idx = start
        length = len(text)
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            return idx
        if text[idx] == '"':
            idx += 1
            escaped = False
            while idx < length:
                char = text[idx]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    return idx + 1
                idx += 1
            return idx
        if text[idx] in "[{":
            stack = ["]" if text[idx] == "[" else "}"]
            idx += 1
            in_string = False
            escaped = False
            while idx < length:
                char = text[idx]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                elif char == '"':
                    in_string = True
                elif char in "[{":
                    stack.append("]" if char == "[" else "}")
                elif stack and char == stack[-1]:
                    stack.pop()
                    if not stack:
                        return idx + 1
                idx += 1
            return idx
        while idx < length and text[idx] not in ",}]\r\n\t ":
            idx += 1
        return idx

    @classmethod
    def _read_check_findings_status_text(cls, text: str) -> Dict[str, Any]:
        decoder = json.JSONDecoder()
        idx = 0
        length = len(text)
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length or text[idx] != "{":
            return {}
        idx += 1
        status: Dict[str, Any] = {}
        while idx < length:
            while idx < length and text[idx].isspace():
                idx += 1
            if idx < length and text[idx] == "}":
                break
            try:
                key, idx = decoder.raw_decode(text, idx)
            except ValueError:
                return {}
            if not isinstance(key, str):
                return {}
            while idx < length and text[idx].isspace():
                idx += 1
            if idx >= length or text[idx] != ":":
                return {}
            idx += 1
            while idx < length and text[idx].isspace():
                idx += 1
            if key in {"entries", "paths"}:
                idx = cls._skip_json_value(text, idx)
            else:
                try:
                    value, idx = decoder.raw_decode(text, idx)
                except ValueError:
                    return {}
                status[key] = value
            while idx < length and text[idx].isspace():
                idx += 1
            if idx < length and text[idx] == ",":
                idx += 1
                continue
            if idx < length and text[idx] == "}":
                break
        return cls._check_findings_status_payload(status)

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
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(new_bytes)
            
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
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            if not candidate.exists() or not candidate.is_file():
                return {}
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}

    def readCheckFindingsStatus(self, finding_type: str) -> Dict[str, Any]:
        candidate = self._finding_path(finding_type)
        if not candidate.exists() or not candidate.is_file():
            return {}
        status_candidate = self._finding_status_path(finding_type)
        if status_candidate.exists() and status_candidate.is_file():
            try:
                with status_candidate.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                data = {}
            if isinstance(data, dict):
                return self._check_findings_status_payload(data)
        try:
            text = candidate.read_text(encoding="utf-8")
        except Exception:
            return {}
        return self._read_check_findings_status_text(text)

    def writeCheckFindings(self, finding_type: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            status_candidate = self._finding_status_path(finding_type)
            status_payload = self._check_findings_status_payload(payload)
            return (
                self._write_json_if_changed(candidate, payload, pretty=True)
                and self._write_json_if_changed(status_candidate, status_payload, pretty=True)
            )

    def appendCheckFindingEntries(self, finding_type: str, entries: List[Dict[str, Any]]) -> bool:
        if not isinstance(entries, list):
            return False

        with self.lockCheckFindings(finding_type):
            payload = self.readCheckFindings(finding_type)
            if not isinstance(payload, dict):
                payload = {}
            existing_entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
            payload["entries"] = list(existing_entries) + [dict(entry) for entry in entries if isinstance(entry, dict)]
            payload["count"] = len(payload["entries"])
            return self.writeCheckFindings(finding_type, payload)

    def deleteCheckFindings(self, finding_type: str) -> bool:
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            status_candidate = self._finding_status_path(finding_type)
            for path in (candidate, status_candidate):
                if not path.exists():
                    continue
                try:
                    path.unlink()
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
