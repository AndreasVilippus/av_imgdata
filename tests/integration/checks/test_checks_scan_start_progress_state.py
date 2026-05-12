from pathlib import Path


def test_checks_scan_running_does_not_depend_on_selected_action():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("isChecksScanRunning()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "!!progress.running" in method
    assert "String(progress.source_mode || '').trim().toLowerCase() === 'scan'" in method
    assert "selectedChecksAction === 'scan'" not in method


def test_checks_start_response_is_applied_to_progress_immediately():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("startChecksReview(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "applyChecksStartProgress(root)" in method


def test_apply_checks_start_progress_sets_progress_and_polling_for_preparing_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "applyChecksStartProgress(progress)" in mixin
    assert "this.checksProgress = {" in mixin
    assert "this.startChecksProgressPolling()" in mixin
    assert "progress.running" in mixin
    assert "total_files" in mixin or "total_files" in Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")
