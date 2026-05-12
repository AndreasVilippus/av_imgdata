from pathlib import Path


def test_checks_api_wrapper_applies_start_and_progress_responses():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async callChecksApi(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.callDsmApi(apiPath, body, options)" in method
    assert "apiPathText.includes('checks_start')" in method
    assert "apiPathText.includes('checks_progress')" in method
    assert "this.applyChecksProgressUpdate(root)" in method


def test_checks_progress_update_forces_running_scan_ui_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "applyChecksProgressUpdate(progress)" in mixin
    assert "this.checksProgress = {" in mixin
    assert "this.selectedChecksAction = 'scan'" in mixin
    assert "this.selectedChecksType = checkType" in mixin
    assert "this.startChecksProgressPolling()" in mixin


def test_checks_scan_running_accepts_backend_scan_progress_without_type_gate():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("isChecksScanRunning()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "!!progress.running" in method
    assert "String(progress.source_mode || '').trim().toLowerCase() === 'scan'" in method
    assert "selectedChecksAction === 'scan'" not in method
    assert "selectedChecksType" not in method


def test_checks_scan_progress_card_visible_for_running_backend_state():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert "vm.isChecksScanRunning ||" in view
    assert "ProgressOverviewCard" in view
