from pathlib import Path


def test_checks_stop_backend_is_wired():
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    service = Path("src/imgdata.py").read_text(encoding="utf-8")
    assert '@router.post("/checks_stop")' in api
    assert "requestStopChecks" in api
    assert "def requestStopChecks" in service
    assert "stop_requested" in service
    assert "_raiseIfChecksStopRequested" in service
    assert "_updateChecksProgressHeartbeat" in service


def test_checks_stop_ui_is_wired():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    assert "async stopChecksReview()" in mixin
    assert "/api/checks_stop" in mixin
    assert "if (this.isChecksScanRunning)" in mixin
    assert "stop_requested" in mixin


def test_checks_stop_translations_exist():
    enu = Path("ui/texts/enu/strings").read_text(encoding="utf-8")
    ger = Path("ui/texts/ger/strings").read_text(encoding="utf-8")
    assert "status_stop_requested=" in enu
    assert "status_stop_requested=" in ger
