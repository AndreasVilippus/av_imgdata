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

    save_only_block_start = mixin.find("if (isScan && saveOnly)")
    save_only_block_end = mixin.find("if (isScan)", save_only_block_start + 1)
    assert save_only_block_start >= 0
    assert save_only_block_end > save_only_block_start
    save_only_block = mixin[save_only_block_start:save_only_block_end]

    assert "counter_processed" in save_only_block
    assert "counter_findings" in save_only_block
    assert "counter_resolved" not in save_only_block
    assert "counter_ignored" not in save_only_block
    assert "counter_total" not in save_only_block
