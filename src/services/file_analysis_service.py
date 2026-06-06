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


class _JsonCharReader:
    def __init__(self, handle):
        self._handle = handle
        self._buffer: List[str] = []

    def read(self) -> str:
        if self._buffer:
            return self._buffer.pop()
        return self._handle.read(1)

    def unread(self, char: str) -> None:
        if char:
            self._buffer.append(char)


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
    def _read_json_non_whitespace(reader: _JsonCharReader) -> str:
        while True:
            char = reader.read()
            if not char or not char.isspace():
                return char

    @staticmethod
    def _read_json_string_after_quote(reader: _JsonCharReader) -> str:
        buffer = ['"']
        escaped = False
        while True:
            char = reader.read()
            if not char:
                raise ValueError("unterminated JSON string")
            buffer.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                return json.loads("".join(buffer))

    @classmethod
    def _skip_json_stream_value(cls, reader: _JsonCharReader, first_char: str) -> None:
        if not first_char:
            return
        if first_char == '"':
            escaped = False
            while True:
                char = reader.read()
                if not char:
                    return
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    return
        if first_char in "[{":
            stack = ["]" if first_char == "[" else "}"]
            in_string = False
            escaped = False
            while stack:
                char = reader.read()
                if not char:
                    return
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
            return
        while True:
            char = reader.read()
            if not char or char in ",}]":
                if char:
                    reader.unread(char)
                return
            if char.isspace():
                return

    @classmethod
    def _read_json_stream_simple_value(cls, reader: _JsonCharReader, first_char: str) -> Any:
        if first_char == '"':
            return cls._read_json_string_after_quote(reader)
        buffer = [first_char]
        while True:
            char = reader.read()
            if not char or char in ",}]":
                if char:
                    reader.unread(char)
                break
            if char.isspace():
                break
            buffer.append(char)
        return json.loads("".join(buffer))

    @classmethod
    def _read_json_stream_value(cls, reader: _JsonCharReader, first_char: str) -> Any:
        if not first_char:
            raise ValueError("missing JSON value")
        if first_char == '"':
            return cls._read_json_string_after_quote(reader)
        buffer = [first_char]
        if first_char in "[{":
            stack = ["]" if first_char == "[" else "}"]
            in_string = False
            escaped = False
            while stack:
                char = reader.read()
                if not char:
                    raise ValueError("unterminated JSON value")
                buffer.append(char)
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
                elif char == stack[-1]:
                    stack.pop()
            return json.loads("".join(buffer))
        while True:
            char = reader.read()
            if not char or char in ",}]":
                if char:
                    reader.unread(char)
                break
            if char.isspace():
                break
            buffer.append(char)
        return json.loads("".join(buffer))

    @classmethod
    def _read_json_stream_object_without_keys(
        cls,
        reader: _JsonCharReader,
        skip_keys: set,
        skipped_marker: Optional[List[bool]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        normalized_skip_keys = {str(key or "") for key in skip_keys}
        while True:
            key_start = cls._read_json_non_whitespace(reader)
            if not key_start or key_start == "}":
                break
            if key_start != '"':
                raise ValueError("invalid JSON object key")
            key = cls._read_json_string_after_quote(reader)
            if cls._read_json_non_whitespace(reader) != ":":
                raise ValueError("missing JSON object separator")
            value_start = cls._read_json_non_whitespace(reader)
            if not value_start:
                raise ValueError("missing JSON object value")
            if key in normalized_skip_keys:
                if skipped_marker is not None:
                    skipped_marker.append(True)
                cls._skip_json_stream_value(reader, value_start)
            else:
                payload[key] = cls._read_json_stream_value(reader, value_start)
            separator = cls._read_json_non_whitespace(reader)
            if separator == ",":
                continue
            if separator == "}":
                break
            raise ValueError("invalid JSON object terminator")
        return payload

    @classmethod
    def _read_json_stream_array_of_objects_without_keys(
        cls,
        reader: _JsonCharReader,
        first_char: str,
        skip_keys: set,
        skipped_marker: Optional[List[bool]] = None,
    ) -> List[Any]:
        if first_char != "[":
            return cls._read_json_stream_value(reader, first_char)
        entries: List[Any] = []
        while True:
            value_start = cls._read_json_non_whitespace(reader)
            if not value_start:
                raise ValueError("unterminated JSON array")
            if value_start == "]":
                break
            if value_start == "{":
                entries.append(cls._read_json_stream_object_without_keys(reader, skip_keys, skipped_marker))
            else:
                entries.append(cls._read_json_stream_value(reader, value_start))
            separator = cls._read_json_non_whitespace(reader)
            if separator == ",":
                continue
            if separator == "]":
                break
            raise ValueError("invalid JSON array terminator")
        return entries

    @classmethod
    def _read_check_findings_without_keys_stream(
        cls,
        handle,
        skip_keys: set,
        stop_after_keys: Optional[set] = None,
        entry_skip_keys: Optional[set] = None,
    ) -> Dict[str, Any]:
        reader = _JsonCharReader(handle)
        first = cls._read_json_non_whitespace(reader)
        if first != "{":
            return {}
        payload: Dict[str, Any] = {}
        normalized_skip_keys = {str(key or "") for key in skip_keys}
        normalized_stop_after_keys = {str(key or "") for key in (stop_after_keys or set())}
        skipped_marker: List[bool] = []
        while True:
            key_start = cls._read_json_non_whitespace(reader)
            if not key_start or key_start == "}":
                break
            if key_start != '"':
                return {}
            try:
                key = cls._read_json_string_after_quote(reader)
            except ValueError:
                return {}
            if cls._read_json_non_whitespace(reader) != ":":
                return {}
            value_start = cls._read_json_non_whitespace(reader)
            if not value_start:
                return {}
            try:
                if key in normalized_skip_keys:
                    cls._skip_json_stream_value(reader, value_start)
                elif key == "entries" and entry_skip_keys:
                    payload[key] = cls._read_json_stream_array_of_objects_without_keys(
                        reader,
                        value_start,
                        entry_skip_keys,
                        skipped_marker,
                    )
                else:
                    payload[key] = cls._read_json_stream_value(reader, value_start)
            except ValueError:
                return {}
            if key in normalized_stop_after_keys:
                break
            separator = cls._read_json_non_whitespace(reader)
            if separator == ",":
                continue
            if separator == "}":
                break
            return {}
        if skipped_marker:
            payload["_stream_compacted"] = True
        return payload

    @classmethod
    def _read_check_findings_status_stream(cls, handle) -> Dict[str, Any]:
        reader = _JsonCharReader(handle)
        first = cls._read_json_non_whitespace(reader)
        if first != "{":
            return {}
        status: Dict[str, Any] = {}
        while True:
            key_start = cls._read_json_non_whitespace(reader)
            if not key_start or key_start == "}":
                break
            if key_start != '"':
                return {}
            try:
                key = cls._read_json_string_after_quote(reader)
            except ValueError:
                return {}
            if cls._read_json_non_whitespace(reader) != ":":
                return {}
            value_start = cls._read_json_non_whitespace(reader)
            if not value_start:
                return {}
            if key in {"entries", "paths"}:
                break
            if value_start in "[{":
                cls._skip_json_stream_value(reader, value_start)
            elif key in {"job_id", "started_at", "finished_at", "last_updated_at", "status", "shared_folder", "action", "auto", "save_only", "transferred_count", "count", "check_type", "source_mode", "resolved_count", "ignored_count", "skipped_count"}:
                try:
                    status[key] = cls._read_json_stream_simple_value(reader, value_start)
                except ValueError:
                    return {}
            else:
                cls._skip_json_stream_value(reader, value_start)
            separator = cls._read_json_non_whitespace(reader)
            if separator == ",":
                continue
            if separator == "}":
                break
            if not separator:
                break
            return {}
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

    def readCheckFindingsWithoutKeys(self, finding_type: str, skip_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        normalized_skip_keys = {str(key or "") for key in (skip_keys or []) if str(key or "")}
        if not normalized_skip_keys:
            return self.readCheckFindings(finding_type)
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            if not candidate.exists() or not candidate.is_file():
                return {}
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    data = self._read_check_findings_without_keys_stream(handle, normalized_skip_keys)
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}

    def readCheckFindingsEntries(self, finding_type: str) -> Dict[str, Any]:
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            if not candidate.exists() or not candidate.is_file():
                return {}
            try:
                with candidate.open("r", encoding="utf-8") as handle:
                    data = self._read_check_findings_without_keys_stream(
                        handle,
                        {"paths"},
                        entry_skip_keys={
                            "lookup_debug",
                            "debug",
                            "resume_cursor",
                            "candidate_persons",
                            "known_persons",
                            "person_candidates",
                        },
                    )
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}

    def readCheckFindingsStatus(self, finding_type: str) -> Dict[str, Any]:
        candidate = self._finding_path(finding_type)
        if not candidate.exists() or not candidate.is_file():
            return {}
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                return self._read_check_findings_status_stream(handle)
        except Exception:
            return {}

    def writeCheckFindings(self, finding_type: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        with self.lockCheckFindings(finding_type):
            candidate = self._finding_path(finding_type)
            return self._write_json_if_changed(candidate, payload, pretty=True)

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
