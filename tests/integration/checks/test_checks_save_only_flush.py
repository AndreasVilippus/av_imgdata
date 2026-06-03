from pathlib import Path


def _run_checks_scan_excerpt() -> str:
    source = Path("src/services/checks_workflow_service.py").read_text(encoding="utf-8")
    start = source.find("def search_next_item(")
    assert start >= 0
    end = source.find("def start_review(", start)
    assert end > start
    return source[start:end]


def test_save_only_checks_flushes_saved_entries_during_scan():
    excerpt = _run_checks_scan_excerpt()

    assert "def flush_saved_checks_findings" in excerpt
    assert "flush_saved_checks_findings(force=True" in excerpt
    assert "flush_saved_checks_findings(reason=" in excerpt
    assert "checks_findings_debouncer" in excerpt
    assert "self.write_findings(" in excerpt


def test_save_only_checks_flush_runs_after_entries_are_added():
    excerpt = _run_checks_scan_excerpt()

    assert "self.append_unique_findings(saved_entries, entries)" in excerpt
    assert "self.append_unique_findings(saved_entries, refreshed_entries)" in excerpt
    assert "reason=\"auto_apply_warning\"" in excerpt
    assert "reason=\"save_only_result\"" in excerpt


def test_save_only_checks_records_flush_progress_fields():
    excerpt = _run_checks_scan_excerpt()

    assert "last_flush_at" in excerpt
    assert "last_flush_count" in excerpt
    assert "flush=True" in excerpt
