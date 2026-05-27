from pathlib import Path


def test_save_only_status_line_uses_backend_schema_counters():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("\t\tgetChecksStatusHeadline()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "status.schema_version === 1" in method
    assert "getChecksCountersStatusSuffix()" in method
    assert "schemaCounterSuffix" in method
    assert " — " not in method
    assert "counter_processed" not in method
    assert "counter_ignored" not in method
    assert "counter_total" not in method


def test_checks_view_uses_filtered_status_text_without_separate_counter_block():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert ':status-text="vm.getChecksProgressStatusText()"' in view
    assert "face-match-status-counters" not in view
