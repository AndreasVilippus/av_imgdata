from pathlib import Path


def test_main_checks_start_response_is_applied_to_progress_immediately():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("startChecksReview(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "applyChecksStartProgress(root)" in method


def test_main_apply_checks_start_progress_handles_preparing_scan_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "applyChecksStartProgress(progress)" in mixin
    assert "this.checksProgress = {" in mixin
    assert "this.startChecksProgressPolling()" in mixin
    assert "progress.running" in mixin
    assert "this.checksLoading = false" in mixin
    assert "this.checksStartRequestInFlight = false" in mixin


def test_main_scan_running_uses_backend_progress():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("isChecksScanRunning()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "!!progress.running" in method
    assert "source_mode" in method
    assert "check_type" in method
    assert "selectedChecksAction === 'scan'" not in method
