from pathlib import Path


def test_checks_findings_processing_has_stop_state_and_button_label():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "checksStopRequested: false" in mixin
    assert "checksFindingsActionRunning: false" in mixin
    assert "isChecksFindingsActionRunning()" in mixin
    assert "this.isChecksScanRunning || this.isChecksFindingsActionRunning" in mixin
    assert "return this.$avt('checks:button_stop', 'Stop')" in mixin


def test_start_checks_review_dispatches_stop_when_findings_are_running():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("startChecksReview(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.isChecksFindingsActionRunning" in method
    assert "return this.stopChecksReview()" in method
    assert "this.checksStopRequested = false" in method


def test_stop_checks_review_sets_flag_and_calls_backend_stop():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "stopChecksReview()" in mixin
    assert "this.checksStopRequested = true" in mixin
    assert "this.checksFindingsActionRunning = false" in mixin
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_stop" in mixin


def test_checks_actions_respect_stop_requested_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "checksStopRequested" in mixin
    assert "this.checksStopRequested = true" in mixin
    assert "this.checksStopRequested = false" in mixin

    # The current optimizations branch does not contain an explicit auto-next
    # loop in checksMixin.js. If such a loop is introduced later, it must either
    # be guarded or call startChecksReview(), which already dispatches Stop.
    unguarded_auto_next = (
        "await this.nextChecksReview();" in mixin
        and "if (!this.checksStopRequested)" not in mixin
    )
    assert not unguarded_auto_next
