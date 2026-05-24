from pathlib import Path


def test_checks_progress_reads_backend_status_directly():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "async fetchChecksProgress({ applyFinishedState = true, applyRunningState = true, adoptResultItem = true, loadResultItem = true } = {})" in source
    assert "return this.runOperationPollRequest(" not in source
    assert "/api/checks_progress" in source
    assert "maxErrors" not in source
    assert "onStopAfterErrors" not in source


def test_checks_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    callback_pos = source.index("async fetchChecksProgress")
    request_id_pos = source.index("const requestId = this.checksProgressRequestId + 1", callback_pos)
    api_call_pos = source.index("/api/checks_progress", request_id_pos)

    assert request_id_pos < api_call_pos
    assert "this.checksProgressRequestId !== requestId" in source[callback_pos:]


def test_checks_progress_polling_error_preserves_backend_owned_state():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchChecksProgress")
    method_end = source.index("startChecksProgressPolling", method_start)
    method_source = source[method_start:method_end]

    catch_start = method_source.index("catch (err)")
    catch_source = method_source[catch_start:]
    assert "this.stopChecksProgressPolling()" not in catch_source
    assert "this.checksLoading = false" not in catch_source
    assert "this.checksFindingsActionRunning = false" not in catch_source
    assert "this.checksStatusMessage = `Error: ${err.message}`" in method_source


def test_checks_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('checksProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
