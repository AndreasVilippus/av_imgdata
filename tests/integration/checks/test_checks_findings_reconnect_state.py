from pathlib import Path


def _method(source: str, name: str) -> str:
    start = source.find(name)
    assert start >= 0
    end = source.find("\n\t\t},", start)
    assert end > start
    return source[start:end]


def test_checks_session_refresh_reads_progress_without_applying_running_scan_first():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method = _method(source, "async refreshChecksSessionState()")

    assert "applyFinishedState: false" in method
    assert "applyRunningState: false" in method
    assert "adoptResultItem: false" in method
    assert "loadResultItem: false" in method
    assert "if (this.isChecksFindingsReviewActive() && progressSourceMode === 'scan')" in method
    assert method.index("applyRunningState: false") < method.index("if (this.isChecksFindingsReviewActive()")
    assert method.index("if (this.isChecksFindingsReviewActive()") < method.index("this.applyChecksProgress(progress")


def test_checks_findings_review_active_is_explicit_state():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method = _method(source, "isChecksFindingsReviewActive()")

    assert "this.selectedChecksAction === 'findings'" in method
    assert "this.checksFindingsActionRunning" in method
    assert "this.checksLoading" in method
    assert "this.checksEntries.length" in method
    assert "this.checksCurrentItem" in method


def test_fetch_checks_progress_can_skip_running_state_application():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method = _method(source, "async fetchChecksProgress(")

    assert "applyRunningState = true" in method
    assert "(progress.running && applyRunningState)" in method
    assert "(!progress.running && applyFinishedState)" in method
