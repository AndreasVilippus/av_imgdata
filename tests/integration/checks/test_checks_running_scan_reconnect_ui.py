from pathlib import Path


def test_checks_scan_running_accepts_any_active_scan_progress():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("isChecksScanRunning()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "!!progress.running" in method
    assert "String(progress.source_mode || '').trim().toLowerCase() === 'scan'" in method
    assert "String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType" not in method
    assert "selectedChecksAction === 'scan'" not in method


def test_checks_scan_progress_card_is_visible_for_active_scan_progress():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")
    start = mixin.find("shouldShowChecksScanProgressCard()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.isChecksScanRunning" in method
    assert "this.selectedChecksAction === 'scan'" in method
    assert "&& this.checksLoading" in method
    assert "Object.keys(this.checksProgress)" not in method
    assert "ProgressOverviewCard" in view


def test_checks_status_text_uses_progress_source_mode_for_save_only_scan():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getChecksProgressStatusText()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "sourceMode === 'scan'" in method
    assert "this.getChecksSaveOnlyFindingsCount(progress)" in method
