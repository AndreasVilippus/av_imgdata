from pathlib import Path


def test_save_only_status_line_uses_findings_and_skipped_only():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getChecksProgressStatusText()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "checks:counter_findings" in method
    assert "checks:counter_skipped" in method
    assert "skipped_count" in method
    assert "parts.join(' | ')" in method
    assert " — " not in method
    assert "getChecksCountersStatusSuffix" not in method
    assert "counter_processed" not in method
    assert "counter_resolved" not in method
    assert "counter_ignored" not in method
    assert "counter_total" not in method


def test_checks_view_uses_filtered_status_text_without_separate_counter_block():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert ':status-text="vm.getChecksProgressStatusText()"' in view
    assert "face-match-status-counters" not in view
