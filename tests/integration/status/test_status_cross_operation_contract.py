import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service() -> ImgDataService:
    return ImgDataService(SessionManager())


@pytest.mark.parametrize("requested_operation", ["checks", "face_match", "cleanup", "file_analysis"])
def test_cross_operation_block_payload_has_schema_status_without_foreign_progress(requested_operation):
    service = _service()

    payload = service._buildStartBlockedByRunningOperationPayload(
        {
            "operation": "face_match",
            "operation_id": "face-match-running",
            "running": True,
            "source_mode": "scan",
            "action": "search_photo_face_in_file",
            "findings_count": 9,
            "transferred_count": 7,
        },
        requested_operation=requested_operation,
    )

    assert payload["blocked"] is True
    assert payload["blocked_by_running_operation"] is True
    assert payload["requested_operation"] == requested_operation
    assert payload["running_operation"] == "face_match"
    assert payload["running_operation_id"] == "face-match-running"

    status = payload["status"]
    assert status["schema_version"] == 1
    assert status["operation"] == requested_operation
    assert status["mode"] == "none"
    assert status["phase"] == "blocked"
    assert status["progress"] == {}
    assert status["counters"] == []


def test_all_long_running_operation_starts_check_cross_operation_blocking():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")

    expectations = {
        "startChecksScanDiscovery": 'exclude_operation="checks"',
        "startFaceMatchingDiscovery": 'exclude_operation="face_match"',
        "startCleanupRun": 'exclude_operation="cleanup"',
        "startFileAnalysisDiscovery": 'exclude_operation="file_analysis"',
    }

    for method_name, exclude_call in expectations.items():
        start = source.find(f"def {method_name}(")
        assert start >= 0, f"Missing method: {method_name}"
        next_method = source.find("\n    def ", start + 1)
        body = source[start: next_method if next_method >= 0 else len(source)]

        assert "_runningOperationProgress" in body
        assert exclude_call in body
        assert "_buildStartBlockedByRunningOperationPayload" in body


def test_stale_stopping_progress_does_not_block_new_operations():
    service = _service()

    service.getFileAnalysisProgress = lambda: {}
    service.getFaceMatchingProgress = lambda _user_key: {}
    service._runningChecksScanProgress = lambda _user_key: {
        "operation": "checks",
        "operation_id": "checks-name_conflicts-stale",
        "running": True,
        "source_mode": "scan",
        "check_type": "name_conflicts",
        "message_key": "checks:progress_stopping",
        "last_updated_at": "2000-01-01T00:00:00+00:00",
    }
    service.getCleanupProgress = lambda _user_key, _action: {}

    assert service._runningOperationProgress("user", exclude_operation="face_match") is None
