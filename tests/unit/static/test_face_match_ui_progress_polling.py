from pathlib import Path


def test_face_match_progress_polling_stops_after_repeated_errors():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async fetchFaceMatchingProgress({ applyRunningState = true } = {})" in source
    assert "this.faceMatchProgressErrorCount = (Number(this.faceMatchProgressErrorCount) || 0) + 1" in source
    assert "if (this.faceMatchProgressErrorCount >= 3)" in source
    assert "this.stopFaceMatchProgressPolling()" in source
    assert "this.faceMatchLoading = false" in source
    assert "message: `Error: ${err.message}`" in source


def test_face_match_progress_polling_resets_error_count_after_success():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    success_marker = "const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_progress'"
    reset_marker = "this.faceMatchProgressErrorCount = 0"
    assert success_marker in source
    assert reset_marker in source
    assert source.index(reset_marker) > source.index(success_marker)
