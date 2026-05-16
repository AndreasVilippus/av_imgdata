from pathlib import Path


def _method(source: str, name: str) -> str:
    start = source.find(f"\n\t\t{name}")
    if start >= 0:
        start += 1
    else:
        start = source.find(name)
    assert start >= 0
    end = source.find("\n\t\t},", start)
    assert end > start
    return source[start:end]


def test_checks_reconnect_does_not_apply_running_scan_over_active_findings_review():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    refresh = _method(source, "async refreshChecksSessionState()")
    fetch = _method(source, "async fetchChecksProgress(")

    assert "applyFinishedState: false" in refresh
    assert "applyRunningState: false" in refresh
    assert "adoptResultItem: false" in refresh
    assert "loadResultItem: false" in refresh
    assert "this.isChecksFindingsReviewActive() && progressSourceMode === 'scan'" in refresh
    assert refresh.index("this.isChecksFindingsReviewActive() && progressSourceMode === 'scan'") < refresh.index("this.applyChecksProgress(progress")
    assert "applyRunningState = true" in fetch
    assert "(progress.running && applyRunningState)" in fetch


def test_checks_findings_review_state_has_explicit_identity_inputs():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method = _method(source, "isChecksFindingsReviewActive()")

    for token in (
        "this.selectedChecksAction === 'findings'",
        "this.checksFindingsActionRunning",
        "this.checksLoading",
        "this.checksEntries.length",
        "this.checksCurrentItem",
    ):
        assert token in method


def test_face_match_reconnect_uses_persisted_runtime_progress_for_running_operation():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    method = _method(source, "async refreshFaceMatchSessionState()")

    assert "await this.fetchFaceMatchingProgress({ applyRunningState: false })" in method
    assert "const progress = await this.fetchFaceMatchingProgress({ applyRunningState: false })" in method
    assert "if (progress.running)" in method
    assert "this.startFaceMatchProgressPolling()" in method


def test_face_match_reconnect_does_not_apply_scan_progress_over_stored_findings_review():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    refresh = _method(source, "async refreshFaceMatchSessionState()")
    fetch = _method(source, "async fetchFaceMatchingProgress(")

    assert "await this.fetchFaceMatchingProgress({ applyRunningState: false })" in refresh
    assert "this.isFaceMatchFindingsReviewActive() && this.getFaceMatchProgressMode(progress) === 'scan'" in refresh
    assert refresh.index("this.isFaceMatchFindingsReviewActive()") < refresh.index("this.applyFaceMatchingProgress(progress)")
    assert "applyRunningState = true" in fetch
    assert "progress.running && !applyRunningState" in fetch
    assert "return progress;" in fetch


def test_face_match_progress_mode_uses_status_mode_before_legacy_action():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    method = _method(source, "getFaceMatchProgressMode(progress)")

    assert "status.schema_version === 1 && statusMode" in method
    assert "return statusMode;" in method
    assert "action === 'load_photo_face_match_findings'" in method
    assert "return 'findings';" in method
    assert "source.running || source.stop_requested" in method
    assert "return 'scan';" in method


def test_cleanup_reconnect_uses_its_own_runtime_progress_only():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    method = _method(source, "async refreshCleanupSessionState()")

    assert "const progress = await this.fetchCleanupProgress()" in method
    assert "if (progress && progress.running)" in method
    assert "this.startCleanupProgressPolling()" in method
    assert "fetchChecksProgress" not in method
    assert "fetchFaceMatchingProgress" not in method


def test_file_analysis_reconnect_uses_its_own_runtime_progress_only():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")
    method = _method(source, "async refreshFileAnalysisSessionState()")

    assert "await this.fetchFileAnalysisProgress()" in method
    assert "const progress = this.fileAnalysisProgress" in method
    assert "if (progress.running)" in method
    assert "this.startFileAnalysisProgressPolling()" in method
    assert "fetchChecksProgress" not in method
    assert "fetchFaceMatchingProgress" not in method
    assert "fetchCleanupProgress" not in method
