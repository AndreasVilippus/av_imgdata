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
    source = Path("ui/src/App.vue").read_text(encoding="utf-8")
    start = source.index("startNamedPolling(timerKey, callback, interval = 1000, options = {})")
    end = source.index("\n\t\t\tstopNamedPolling(timerKey)", start)
    method_source = source[start:end]

    assert "if (skipIfPending && this.__namedPollingPending[timerKey])" in method_source
    assert "Promise.resolve()" in method_source
    assert ".then(() => callback())" in method_source
    assert ".catch(() => {})" in method_source
    assert ".finally(() =>" in method_source
    assert "this.__namedPollingPending[timerKey] = false" in method_source
