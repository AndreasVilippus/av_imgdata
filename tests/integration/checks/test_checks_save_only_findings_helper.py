from pathlib import Path


def test_checks_progress_status_helper_exists_when_status_text_uses_it():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "getChecksProgressStatusText()" in mixin
    assert "getChecksSaveOnlyFindingsCount(" in mixin

    status_start = mixin.find("getChecksProgressStatusText()")
    status_end = mixin.find("\n\t\t},", status_start)
    assert status_start >= 0
    assert status_end > status_start
    status_method = mixin[status_start:status_end]

    assert "this.getChecksSaveOnlyFindingsCount(progress)" in status_method
