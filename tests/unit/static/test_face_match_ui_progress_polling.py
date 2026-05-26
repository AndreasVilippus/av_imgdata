from pathlib import Path


def test_face_match_progress_polling_error_does_not_end_backend_operation_locally():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    method_start = source.index("async fetchFaceMatchingProgress")
    method_end = source.index("startFaceMatchProgressPolling", method_start)
    method_source = source[method_start:method_end]
    catch_start = method_source.index("catch (err)")
    catch_source = method_source[catch_start:]

    assert "return this.runOperationPollRequest(" not in method_source
    assert "this.stopFaceMatchProgressPolling()" not in catch_source
    assert "this.faceMatchLoading = false" not in catch_source
    assert "message: `Error: ${err.message}`" in catch_source


def test_named_polling_guard_resets_after_callback_success_or_error():
    method_source = Path("ui/src/services/runtime-polling.js").read_text(encoding="utf-8")

    assert "if (skipIfPending && state.pending[timerKey])" in method_source
    assert "Promise.resolve()" in method_source
    assert ".then(() => callback())" in method_source
    assert ".catch(() => {})" in method_source
    assert ".finally(() =>" in method_source
    assert "state.pending[timerKey] = false" in method_source
