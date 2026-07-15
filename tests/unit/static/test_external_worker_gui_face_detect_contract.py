from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_external_worker_gui_starts_real_face_detect_job():
    api = (ROOT / "src/api/worker_admin_api.py").read_text(encoding="utf-8")
    view = (ROOT / "ui/src/views/ExternalWorkerView.vue").read_text(encoding="utf-8")

    assert '@router.post("/external_worker_face_detect")' in api
    assert "processor.execute_face_detect" in api
    assert 'policy="external_required"' in api
    assert 'operation="cleanup"' in api
    assert 'action="external_worker_face_detect"' in api
    assert "source.relative_to(root)" in api
    assert '"faces": faces' in api

    assert "external_worker_face_detect" in view
    assert "runFaceDetect" in view
    assert "faceDetectResult.faces_count" in view
    assert "formatFaceDetectResult(faceDetectResult.faces)" in view


def test_external_worker_gui_flow_does_not_replace_local_processor_default():
    service = (ROOT / "src/services/external_worker_processor_service.py").read_text(encoding="utf-8")

    assert 'policy: str = "local_preferred"' in service
    assert 'selected_policy in {"local_only", "local_preferred"}' in service
    assert '"execution_target": "local_native"' in service
