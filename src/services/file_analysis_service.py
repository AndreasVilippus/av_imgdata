#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class FileAnalysisService:
    """Persistence for the latest file analysis result."""

    FINDING_FILES = {
        "dimension_issues": "dimension_issues.json",
        "duplicate_faces": "duplicate_faces.json",
        "position_deviations": "position_deviations.json",
        "name_conflicts": "name_conflicts.json",
        "face_match": "face_match.json",
    }

    def __init__(self, result_path: Optional[str] = None, mismatch_path: Optional[str] = None):
        if result_path:
            self._result_path = Path(result_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._result_path = Path(package_var) / "file_analysis.json"
        self._findings_dir = self._result_path.parent / "analysis_findings"
        if mismatch_path:
            self._mismatch_path = Path(mismatch_path)
        else:
            self._mismatch_path = self._findings_dir / self.FINDING_FILES["dimension_issues"]

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
        candidate = self._result_path
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            return False
        return True

    def readDimensionMismatchFindings(self) -> Dict[str, Any]:
        return self.readCheckFindings("dimension_issues")

    def writeDimensionMismatchFindings(self, payload: Dict[str, Any]) -> bool:
        return self.writeCheckFindings("dimension_issues", payload)

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
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            return False
        return True

    def _finding_path(self, finding_type: str) -> Path:
        normalized = str(finding_type or "").strip().lower()
        filename = self.FINDING_FILES.get(normalized)
        if not filename:
            raise ValueError(f"unknown_finding_type: {finding_type}")
        return self._findings_dir / filename
