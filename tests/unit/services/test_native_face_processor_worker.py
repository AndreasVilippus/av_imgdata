import json
from pathlib import Path
from unittest.mock import patch

from services import native_face_processor_worker as worker


def test_worker_version_reports_python_bridge(capsys):
    assert worker.main(["version"]) == 0

    captured = capsys.readouterr()

    assert "av-imgdata-face-processor" in captured.out
    assert "python-bridge" in captured.out


def test_worker_detect_writes_failure_contract(tmp_path):
    input_path = tmp_path / "job-input.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps({
            "contract_version": "1.0",
            "job_id": "job-test",
            "type": "face_native_detect",
            "input": {"image_path": str(tmp_path / "missing.jpg")},
            "options": {"model_name": "buffalo_l", "model_root": str(tmp_path / "models")},
        }),
        encoding="utf-8",
    )

    with patch.object(worker.InsightFaceDetector, "detect", side_effect=ValueError("image could not be read")):
        assert worker.main(["detect", "--input", str(input_path), "--output", str(output_path)]) == 1

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert payload["processor"]["backend"] == "python_bridge"
    assert payload["result"]["faces"] == []
    assert payload["error"]["code"] == "ValueError"
