from pathlib import Path


def test_file_analysis_status_message_translates_backend_message_key():
    mixin = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")
    start = mixin.find("getFileAnalysisStatusMessage(progress)")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "current.message_key" in method
    assert "this.$avt(" in method
    assert "current.message_params" in method
