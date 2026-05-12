from pathlib import Path


def test_checks_counters_are_integrated_into_progress_status_text():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "getChecksProgressStatusText()" in view
    assert "getChecksProgressStatusText()" in mixin
    assert "getChecksCountersStatusSuffix()" in mixin
    assert "face-match-status-counters" not in view



def test_save_only_counters_only_include_relevant_scan_values():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("\t\tgetRelevantChecksStatusCounters()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "status.schema_version === 1" in method
    assert "status.counters" in method
    assert "return []" in method
    assert "if (isScan && saveOnly)" not in method
    assert "counter_processed" not in method
    assert "counter_findings" not in method
    assert "counter_resolved" not in method
    assert "counter_ignored" not in method
    assert "counter_skipped" not in method

