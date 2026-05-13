from pathlib import Path


def test_checks_view_mount_refreshes_running_session_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("mounted()")
    assert start >= 0
    end = mixin.find("\n\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.fetchChecksFindingsStatus()" in method
    assert "this.refreshChecksSessionState()" in method


def test_checks_reconnect_scans_all_types_after_selected_type_fallback():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("async refreshChecksSessionState()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert ": await this.findRunningChecksScanProgress();" in method
    assert "findRunningChecksScanProgress(String(this.selectedChecksType" not in method
