#!/usr/bin/env python3
import os
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from av_imgdata.db.connection import Database
from av_imgdata.db.migrations import migrate_runtime_persistence
from av_imgdata.db.repositories.app_state import AppStateRepository
from av_imgdata.db.repositories.persisted_findings import PersistedFindingsRepository


class FileAnalysisService:
    """SQLite persistence for analysis results, findings, and runtime state."""

    def __init__(self, result_path: Optional[str] = None):
        if result_path:
            self._result_path = Path(result_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._result_path = Path(package_var) / "file_analysis.json"
        self._runtime_dir = self._result_path.parent / "runtime_state"
        self._database = Database(str(self._result_path.parent / "imgdata.sqlite3"))
        self._app_state = AppStateRepository(self._database)
        self._findings = PersistedFindingsRepository(self._database)
        self._migration_checked = False
        self._finding_locks_guard = RLock()
        self._finding_locks: Dict[str, RLock] = {}

    @contextmanager
    def lockCheckFindings(self, finding_type: str):
        key = str(finding_type or "").strip().lower()
        with self._finding_locks_guard:
            lock = self._finding_locks.setdefault(key, RLock())
        with lock:
            yield

    def readLatestResult(self) -> Dict[str, Any]:
        self._ensure_migrated()
        data = self._app_state.get("file_analysis:latest", {})
        return data if isinstance(data, dict) else {}

    def writeLatestResult(self, result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        self._ensure_migrated()
        return self._app_state.set("file_analysis:latest", result)

    def readCheckFindings(self, finding_type: str) -> Dict[str, Any]:
        with self.lockCheckFindings(finding_type):
            self._ensure_migrated()
            return self._findings.read(finding_type)

    def readCheckFindingsWithoutKeys(
        self,
        finding_type: str,
        skip_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload = self.readCheckFindings(finding_type)
        for key in skip_keys or []:
            payload.pop(str(key or ""), None)
        return payload

    def readCheckFindingsEntries(self, finding_type: str) -> Dict[str, Any]:
        return self.readCheckFindingsWithoutKeys(finding_type, ["paths"])

    def readCheckFindingsStatus(self, finding_type: str) -> Dict[str, Any]:
        self._ensure_migrated()
        return self._findings.read(finding_type, include_entries=False)

    def writeCheckFindings(self, finding_type: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        with self.lockCheckFindings(finding_type):
            self._ensure_migrated()
            return self._findings.write(finding_type, payload)

    def appendCheckFindingEntries(self, finding_type: str, entries: List[Dict[str, Any]]) -> bool:
        if not isinstance(entries, list):
            return False
        with self.lockCheckFindings(finding_type):
            self._ensure_migrated()
            return self._findings.append(finding_type, entries)

    def deleteCheckFindings(self, finding_type: str) -> bool:
        with self.lockCheckFindings(finding_type):
            self._ensure_migrated()
            return self._findings.delete(finding_type)

    def readRuntimeState(self, state_type: str, state_key: str) -> Dict[str, Any]:
        self._ensure_migrated()
        data = self._app_state.get(self._runtime_state_db_key(state_type, state_key), {})
        return data if isinstance(data, dict) else {}

    def writeRuntimeState(self, state_type: str, state_key: str, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        self._ensure_migrated()
        return self._app_state.set(self._runtime_state_db_key(state_type, state_key), payload)

    def deleteRuntimeState(self, state_type: str, state_key: str) -> bool:
        self._ensure_migrated()
        self._app_state.delete(self._runtime_state_db_key(state_type, state_key))
        return True

    def _ensure_migrated(self) -> None:
        if self._migration_checked:
            return
        migrate_runtime_persistence(self._database, self._result_path.parent)
        self._migration_checked = True

    @staticmethod
    def _runtime_state_db_key(state_type: str, state_key: str) -> str:
        return f"runtime:{str(state_type or '').strip().lower()}:{str(state_key or '').strip().lower()}"

    def _runtime_state_path(self, state_type: str, state_key: str) -> Path:
        normalized_type = str(state_type or "").strip().lower()
        normalized_key = str(state_key or "").strip().lower()
        safe_key = "".join(char for char in normalized_key if char.isalnum() or char in {"-", "_"})
        if not normalized_type or not safe_key:
            raise ValueError("state_type and state_key are required")
        return self._runtime_dir / f"{normalized_type}_{safe_key}.json"
