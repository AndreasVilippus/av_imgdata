from pathlib import Path


def test_face_match_progress_uses_shared_operation_polling_helper():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async fetchFaceMatchingProgress({ applyRunningState = true, force = false } = {})" in source
    assert "return this.runOperationPollRequest(" in source
    assert "'face_match_progress'" in source
    assert "force," in source
    assert "maxErrors: 3" in source
    assert "onStopAfterErrors" in source


def test_face_match_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    callback_pos = source.index("return this.runOperationPollRequest(")
    request_id_pos = source.index("const requestId = this.faceMatchProgressRequestId + 1", callback_pos)
    api_call_pos = source.index("face_matching_progress", callback_pos)

    assert request_id_pos < api_call_pos
    assert "this.faceMatchProgressRequestId !== requestId" in source[callback_pos:]


def test_face_match_progress_no_longer_uses_local_error_counter():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchFaceMatchingProgress")
    method_end = source.index("startFaceMatchProgressPolling", method_start)
    method_source = source[method_start:method_end]

    assert "faceMatchProgressErrorCount" not in method_source
    assert "catch (err)" not in method_source


def test_face_match_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('faceMatchProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
