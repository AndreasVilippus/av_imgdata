from pathlib import Path


def read_ui_sources():
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("ui/src").rglob("*.js")
    )


def test_runtime_polling_uses_central_polling_helper():
    source = read_ui_sources()

    assert "runOperationPollRequest" in source
    assert "getOperationPollState" in source


def test_runtime_polling_has_in_flight_guard_per_poll_key():
    source = read_ui_sources()

    assert "pollKey" in source
    assert "inFlight" in source
    assert "if (state.inFlight && !force)" in source
    assert "state.inFlight = true" in source
    assert "finally" in source
    assert "state.inFlight = false" in source


def test_runtime_polling_has_error_budget_per_poll_key():
    source = read_ui_sources()

    assert "errorCount" in source
    assert "maxErrors" in source
    assert "onStopAfterErrors" in source
    assert "state.errorCount += 1" in source
    assert "state.errorCount = 0" in source


def test_runtime_polling_records_last_error_and_stop_state():
    source = read_ui_sources()

    assert "lastError" in source
    assert "stoppedAfterErrors" in source
    assert "lastErrorAt" in source
    assert "lastSuccessAt" in source


def test_interval_polling_does_not_force_runtime_requests():
    source = read_ui_sources()

    for marker in [
        "startNamedPolling('faceMatchProgressTimer'",
        "startNamedPolling('checksProgressTimer'",
        "startNamedPolling('fileAnalysisProgressTimer'",
        "startNamedPolling('cleanupProgressTimer'",
    ]:
        if marker not in source:
            continue
        snippet = source[source.index(marker):source.index(marker) + 500]
        assert "force: true" not in snippet
