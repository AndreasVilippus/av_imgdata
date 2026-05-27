from pathlib import Path


def test_face_match_progress_reads_backend_status_directly():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async fetchFaceMatchingProgress({ applyRunningState = true, allowConcurrent = false } = {})" in source
    assert "return this.runOperationPollRequest(" not in source
    assert "/api/face_matching_progress" in source
    assert "maxErrors" not in source
    assert "onStopAfterErrors" not in source


def test_face_match_progress_keeps_request_id_inside_poll_callback():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    method_pos = source.index("async fetchFaceMatchingProgress")
    request_id_pos = source.index("const requestId = this.faceMatchProgressRequestId + 1", method_pos)
    api_call_pos = source.index("face_matching_progress", method_pos)

    assert request_id_pos < api_call_pos
    assert "this.faceMatchProgressRequestId !== requestId" in source[method_pos:]


def test_face_match_progress_no_longer_uses_local_error_counter():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchFaceMatchingProgress")
    method_end = source.index("startFaceMatchProgressPolling", method_start)
    method_source = source[method_start:method_end]

    assert "faceMatchProgressErrorCount" not in method_source
    catch_start = method_source.index("catch (err)")
    catch_source = method_source[catch_start:]
    assert "this.stopFaceMatchProgressPolling()" not in catch_source
    assert "this.faceMatchLoading = false" not in catch_source


def test_face_match_interval_polling_does_not_force_progress_requests():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    marker = "startNamedPolling('faceMatchProgressTimer'"
    assert marker in source
    snippet = source[source.index(marker):source.index(marker) + 500]
    assert "force: true" not in snippet
