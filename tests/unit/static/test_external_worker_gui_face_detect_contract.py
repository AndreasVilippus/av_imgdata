from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_external_worker_gui_no_longer_exposes_manual_face_detect_diagnostic():
    api = (ROOT / "src/api/worker_admin_api.py").read_text(encoding="utf-8")
    view = (ROOT / "ui/src/views/ExternalWorkerView.vue").read_text(encoding="utf-8")

    assert "external_worker_face_detect" not in api
    assert "external_worker_face_detect" not in view
    assert "runFaceDetect" not in view
    assert "faceDetectResult" not in view
    assert "faceDetectForm" not in view
    assert "faceDetectRunning" not in view


def test_external_worker_gui_flow_does_not_replace_local_processor_default():
    service = (ROOT / "src/services/external_worker_processor_service.py").read_text(encoding="utf-8")

    assert 'policy: str = "local_preferred"' in service
    assert 'selected_policy in {"local_only", "local_preferred"}' in service
    assert '"execution_target": "local_native"' in service
