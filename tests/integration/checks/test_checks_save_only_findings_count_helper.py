from pathlib import Path


def test_checks_save_only_findings_count_helper_method_exists():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "\t\tgetChecksSaveOnlyFindingsCount(" in mixin
    assert "this.getChecksSaveOnlyFindingsCount(progress)" in mixin


def test_checks_save_only_findings_count_helper_uses_flush_and_status_counts():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("\t\tgetChecksSaveOnlyFindingsCount(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "current.findings_count" in method
    assert "current.last_flush_count" in method
    assert "current.saved_findings_count" in method
    assert "this.checksStoredFindingsCount" in method
    assert "Math.max(0, ...values)" in method


def test_checks_progress_status_text_calls_existing_helper():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getChecksProgressStatusText()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.getChecksSaveOnlyFindingsCount(progress)" in method
