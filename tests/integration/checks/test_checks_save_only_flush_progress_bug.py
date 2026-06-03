from pathlib import Path


def test_save_only_flush_does_not_use_undefined_state_key():
    source = Path("src/services/checks_workflow_service.py").read_text(encoding="utf-8")
    start = source.find("def flush_saved_checks_findings")
    assert start >= 0
    end = source.find("return True", start)
    assert end > start
    helper = source[start:end]

    assert "state_key" not in helper
    assert "backend._checksStateKey(user_key, check_type)" in helper


def test_save_only_flush_updates_progress_count_after_write():
    source = Path("src/services/checks_workflow_service.py").read_text(encoding="utf-8")
    start = source.find("def flush_saved_checks_findings")
    assert start >= 0
    end = source.find("return True", start)
    assert end > start
    helper = source[start:end]

    assert 'progress["findings_count"] = len(saved_entries)' in helper
    assert 'progress["last_flush_count"] = len(saved_entries)' in helper
    assert 'progress["last_flush_reason"]' in helper
