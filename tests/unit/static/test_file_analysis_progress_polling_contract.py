from pathlib import Path


def test_file_analysis_progress_uses_shared_operation_polling_helper():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")

    assert "async fetchFileAnalysisProgress({ force = false } = {})" in source
    assert "return this.runOperationPollRequest(" in source
    assert "'file_analysis_progress'" in source
    assert "force," in source
    assert "maxErrors: 3" in source
    assert "onStopAfterErrors" in source


def test_file_analysis_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")

    callback_pos = source.index("return this.runOperationPollRequest(")
    request_id_pos = source.index("const requestId = this.fileAnalysisProgressRequestId + 1", callback_pos)
    api_call_pos = source.index("/api/file_analysis_progress", request_id_pos)

    assert request_id_pos < api_call_pos
    assert "this.fileAnalysisProgressRequestId !== requestId" in source[callback_pos:]


def test_file_analysis_progress_error_budget_stops_polling_and_records_error():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchFileAnalysisProgress")
    method_end = source.index("async fetchExiftoolStatus", method_start)
    method_source = source[method_start:method_end]

    assert "onStopAfterErrors: (err) =>" in method_source
    assert "this.stopFileAnalysisProgressPolling()" in method_source
    assert "message: `Error: ${err.message}`" in method_source


def test_file_analysis_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('fileAnalysisProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
