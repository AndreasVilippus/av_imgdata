from pathlib import Path


def test_save_only_status_line_shows_findings_and_skipped_only():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getChecksProgressStatusText()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "checks:counter_findings" in method
    assert "checks:counter_skipped" in method
    assert "skipped_count" in method
    assert "parts.push(`${skippedLabel}: ${skipped}`)" in method
    assert "counter_processed" not in method
    assert "counter_resolved" not in method
    assert "counter_ignored" not in method
    assert "counter_total" not in method
    assert " — " not in method
