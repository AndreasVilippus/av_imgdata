from pathlib import Path


def test_save_only_scan_findings_count_does_not_use_stored_findings_count_while_running():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("\t\tgetChecksSaveOnlyFindingsCount(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "isRunningSaveOnlyScan" in method
    assert "scanValues" in method
    assert "this.checksStoredFindingsCount" in method
    assert "if (isRunningSaveOnlyScan)" in method

    running_block = method.split("if (isRunningSaveOnlyScan)", 1)[1].split("const values", 1)[0]
    assert "this.checksStoredFindingsCount" not in running_block


def test_save_only_status_text_still_uses_findings_helper():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getChecksProgressStatusText()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.getChecksSaveOnlyFindingsCount(progress)" in method
    assert "sourceMode === 'scan'" in method


def test_relevant_save_only_counter_does_not_fallback_to_stored_count():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getRelevantChecksStatusCounters()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "checksStoredFindingsCount" not in method
