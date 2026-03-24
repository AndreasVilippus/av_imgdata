#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class FileAnalysisService:
    """Persistence for the latest file analysis result."""

    def __init__(self, result_path: Optional[str] = None):
        if result_path:
            self._result_path = Path(result_path)
        else:
            package_var = os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var")
            self._result_path = Path(package_var) / "file_analysis.json"

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
