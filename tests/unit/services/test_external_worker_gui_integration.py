#!/usr/bin/env python3
from pathlib import Path
from unittest.mock import Mock

from services.external_worker_gui_integration import ExternalWorkerFaceDetectorAdapter


def test_face_frame_detector_prefers_compatible_external_worker():
    local_factory = Mock(side_effect=AssertionError("local detector must not be built"))
    processor = Mock()
    processor.execute_face_detect.return_value = {
        "execution_target": "external_worker",
        "job_id": "job-1",
        "faces": [{"bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, "score": 0.9}],
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor

    adapter = ExternalWorkerFaceDetectorAdapter(
        options={"det_size": [640, 640], "det_thresh": 0.5, "max_num": 0},
        local_detector_factory=local_factory,
        composition_factory=lambda: composition,
    )

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert faces[0]["score"] == 0.9
    composition.external_face_processor.assert_called_once_with(nas_root=Path("/volume1/photo"))
    kwargs = processor.execute_face_detect.call_args.kwargs
    assert kwargs["policy"] == "external_preferred"
    assert kwargs["operation"] == "cleanup"
    assert kwargs["action"] == "standardize_face_frames"
    local_factory.assert_not_called()


def test_face_frame_detector_keeps_local_fallback_when_worker_api_disabled():
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}]
    composition = Mock()
    composition.enabled.return_value = False
    adapter = ExternalWorkerFaceDetectorAdapter(
        options={},
        local_detector_factory=lambda: detector,
        composition_factory=lambda: composition,
    )

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert len(faces) == 1
    detector.detect.assert_called_once()
    composition.external_face_processor.assert_not_called()


def test_face_frame_detector_uses_local_path_for_unsupported_size_filters():
    detector = Mock()
    detector.detect.return_value = []
    composition_factory = Mock(side_effect=AssertionError("worker composition must not be built"))
    adapter = ExternalWorkerFaceDetectorAdapter(
        options={"min_width_ratio": 0.01},
        local_detector_factory=lambda: detector,
        composition_factory=composition_factory,
    )

    assert adapter.detect(Path("/volume1/photo/album/image.jpg")) == []
    composition_factory.assert_not_called()
