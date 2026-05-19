from pathlib import Path


def test_face_match_progress_polling_stops_after_repeated_errors_via_shared_helper():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async fetchFaceMatchingProgress({ applyRunningState = true, force = false } = {})" in source
    assert "return this.runOperationPollRequest(" in source
    assert "'face_match_progress'" in source
    assert "maxErrors: 3" in source
    assert "onStopAfterErrors: (err) =>" in source
    assert "this.stopFaceMatchProgressPolling()" in source
    assert "this.faceMatchLoading = false" in source
    assert "message: `Error: ${err.message}`" in source


def test_face_match_progress_polling_uses_shared_error_reset_after_success():
    source = Path("ui/src/mixins/runtimePollingMixin.js").read_text(encoding="utf-8")

    assert "async runOperationPollRequest(pollKey, callback, options = {})" in source
    assert "const result = await callback()" in source
    assert "state.errorCount = 0" in source
    assert "state.lastError = ''" in source
    assert "state.stoppedAfterErrors = false" in source
    assert "state.lastSuccessAt = new Date().toISOString()" in source
