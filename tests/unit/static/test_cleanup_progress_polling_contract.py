from pathlib import Path


def test_cleanup_progress_uses_shared_operation_polling_helper():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "async fetchCleanupProgress({ force = false } = {})" in source
    assert "return this.runOperationPollRequest(" in source
    assert "'cleanup_progress'" in source
    assert "force," in source
    assert "maxErrors: 3" in source
    assert "onStopAfterErrors" in source


def test_cleanup_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    callback_pos = source.index("return this.runOperationPollRequest(")
    request_id_pos = source.index("const requestId = this.cleanupProgressRequestId + 1", callback_pos)
    api_call_pos = source.index("/api/cleanup_progress", request_id_pos)

    assert request_id_pos < api_call_pos
    assert "this.cleanupProgressRequestId !== requestId" in source[callback_pos:]


def test_cleanup_progress_error_budget_stops_polling_and_releases_loading_state():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchCleanupProgress")
    method_end = source.index("startCleanupProgressPolling", method_start)
    method_source = source[method_start:method_end]

    assert "onStopAfterErrors: (err) =>" in method_source
    assert "this.stopCleanupProgressPolling()" in method_source
    assert "this.cleanupLoading = false" in method_source
    assert "this.cleanupStatusMessage = `Error: ${err.message}`" in method_source
    assert "message: `Error: ${err.message}`" in method_source


def test_cleanup_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('cleanupProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
