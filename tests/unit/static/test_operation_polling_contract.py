from pathlib import Path


def read_ui_sources():
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("ui/src").rglob("*.js")
    )


def test_polling_overlap_guard_is_opt_in_for_named_polling():
    method = Path("ui/src/services/runtime-polling.js").read_text(encoding="utf-8")

    assert "const skipIfPending = options && options.skipIfPending === true" in method
    assert "state.pending" in method
    assert "if (skipIfPending && state.pending[timerKey])" in method
    assert "return;" in method
    assert "state.pending[timerKey] = true" in method
    assert "finally" in method
    assert "state.pending[timerKey] = false" in method


def test_runtime_polling_mixin_was_removed_from_app():
    source = read_ui_sources()
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")

    assert "runOperationPollRequest" not in source
    assert "getOperationPollState" not in source
    assert "runtimePollingMixin" not in app


def test_named_polling_errors_do_not_stop_backend_operations_locally():
    method = Path("ui/src/services/runtime-polling.js").read_text(encoding="utf-8")

    assert ".catch(() => {})" in method
    assert "maxErrors" not in method
    assert "stoppedAfterErrors" not in method


def test_progress_polling_errors_do_not_clear_loading_or_stop_timers():
    source = read_ui_sources()

    for marker, stop_call, loading_assignment in (
        ("async fetchFaceMatchingProgress", "this.stopFaceMatchProgressPolling()", "this.faceMatchLoading = false"),
        ("async fetchChecksProgress", "this.stopChecksProgressPolling()", "this.checksLoading = false"),
        ("async fetchCleanupProgress", "this.stopCleanupProgressPolling()", "this.cleanupLoading = false"),
        ("async fetchFileAnalysisProgress", "this.stopFileAnalysisProgressPolling()", ""),
    ):
        start = source.index(marker)
        catch_start = source.index("catch (err)", start)
        next_method = source.find("\n\t\t", catch_start + 1)
        snippet = source[catch_start:catch_start + 500 if next_method < 0 else next_method]
        assert stop_call not in snippet
        if loading_assignment:
            assert loading_assignment not in snippet


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


def test_only_runtime_progress_polling_opts_into_overlap_skipping():
    source = read_ui_sources()

    assert source.count("skipIfPending: true") == 4
    for marker in [
        "startNamedPolling('faceMatchProgressTimer'",
        "startNamedPolling('checksProgressTimer'",
        "startNamedPolling('fileAnalysisProgressTimer'",
        "startNamedPolling('cleanupProgressTimer'",
    ]:
        snippet = source[source.index(marker):source.index(marker) + 250]
        assert "skipIfPending: true" in snippet

    for marker in [
        "getStatus({ auto: true })",
        "fetchExiftoolStatus()",
        "fetchInsightFaceStatus()",
        "loadExternalLibrariesConfig()",
    ]:
        assert marker in source


def test_stopping_polling_releases_in_flight_latches_for_next_user_action():
    source = read_ui_sources()
    polling = Path("ui/src/services/runtime-polling.js").read_text(encoding="utf-8")

    for timer_key in (
        "faceMatchProgressTimer",
        "checksProgressTimer",
        "fileAnalysisProgressTimer",
        "cleanupProgressTimer",
    ):
        stop_pos = source.index(f"this.stopNamedPolling('{timer_key}')")
        assert stop_pos >= 0
        assert "state.pending[timerKey] = false" in polling
