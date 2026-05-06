from pathlib import Path


def test_name_conflicts_safe_refresh_uses_snapshot_without_reread():
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")

    assert "def _snapshot_name_conflicts_mutation_state" in api
    snapshot_start = api.find("def _snapshot_name_conflicts_mutation_state")
    safe_start = api.find("def _safe_refresh_checks_mutation_state")
    assert snapshot_start >= 0 and safe_start > snapshot_start
    snapshot_body = api[snapshot_start:safe_start]
    assert "refreshChecksFindingEntriesForImage" not in snapshot_body
    assert "refreshChecksScanProgressForImage" not in snapshot_body
    assert "if normalized_type == \"name_conflicts\":" in api
    assert "return _snapshot_name_conflicts_mutation_state(" in api


def test_name_conflicts_snapshot_update_removes_existing_entries_only():
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    snapshot_start = api.find("def _snapshot_name_conflicts_mutation_state")
    safe_start = api.find("def _safe_refresh_checks_mutation_state")
    snapshot_body = api[snapshot_start:safe_start]

    assert "readCheckFindings(normalized_type)" in snapshot_body
    assert "writeCheckFindings(normalized_type, updated_payload)" in snapshot_body
    assert "pending_entries" in snapshot_body
    assert "checks_mutation_snapshot_failed" in snapshot_body
