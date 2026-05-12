from pathlib import Path


def _method(source: str, name: str) -> str:
    start = source.find(name)
    assert start >= 0, name
    end = source.find("\n\t\t},", start)
    assert end > start, name
    return source[start:end]


def test_checks_item_api_tolerates_empty_resolver_result():
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")

    assert "resolved = resolved if isinstance(resolved, dict) else {}" in api
    response_start = api.find('"entry": resolved.get("entry")')
    guard_start = api.find("resolved = resolved if isinstance(resolved, dict) else {}")
    assert guard_start >= 0
    assert response_start > guard_start


def test_cleanup_start_invalidates_stale_progress_before_starting():
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    method = _method(mixin, "async startCleanupRun()")

    assert "this.stopCleanupProgressPolling()" in method
    assert "this.cleanupProgressRequestId += 1" in method
    assert "this.cleanupLoading = true" in method


def test_face_match_start_invalidates_stale_progress_before_starting():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    method = _method(mixin, "async startFaceMatchingAction(options = {})")

    assert "this.stopFaceMatchProgressPolling()" in method
    assert "this.faceMatchProgressRequestId += 1" in method
    assert "this.faceMatchLoading = true" in method


def test_file_analysis_start_invalidates_stale_progress_before_starting():
    mixin = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")
    method = _method(mixin, "async handleFilesAnalyze()")

    assert "this.stopFileAnalysisProgressPolling()" in method
    assert "this.fileAnalysisProgressRequestId += 1" in method
    assert "running: true" in method
    assert "phase: 'discovery'" in method
