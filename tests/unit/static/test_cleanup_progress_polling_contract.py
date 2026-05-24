from pathlib import Path


def test_cleanup_progress_reads_backend_status_directly():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "async fetchCleanupProgress()" in source
    assert "return this.runOperationPollRequest(" not in source
    assert "/api/cleanup_progress" in source
    assert "maxErrors" not in source
    assert "onStopAfterErrors" not in source


def test_cleanup_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    callback_pos = source.index("async fetchCleanupProgress")
    request_id_pos = source.index("const requestId = this.cleanupProgressRequestId + 1", callback_pos)
    api_call_pos = source.index("/api/cleanup_progress", request_id_pos)

    assert request_id_pos < api_call_pos
    assert "this.cleanupProgressRequestId !== requestId" in source[callback_pos:]


def test_cleanup_progress_polling_error_preserves_backend_owned_state():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchCleanupProgress")
    method_end = source.index("startCleanupProgressPolling", method_start)
    method_source = source[method_start:method_end]

    catch_start = method_source.index("catch (err)")
    catch_source = method_source[catch_start:]
    assert "this.stopCleanupProgressPolling()" not in catch_source
    assert "this.cleanupLoading = false" not in catch_source
    assert "this.cleanupStatusMessage = `Error: ${err.message}`" in method_source
    assert "message: `Error: ${err.message}`" in method_source


def test_cleanup_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('cleanupProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
