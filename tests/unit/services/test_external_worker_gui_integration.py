#!/usr/bin/env python3
from pathlib import Path
from unittest.mock import Mock

from services.external_worker_gui_integration import (
    ExternalWorkerFaceDetectorAdapter,
    ExternalWorkerFaceEmbedderAdapter,
)


def test_face_frame_detector_prefers_compatible_external_worker():
    local_factory = Mock(side_effect=AssertionError("local detector must not be built"))
    processor = Mock()
    processor.execute_face_detect.return_value = {
        "execution_target": "external_worker",
        "job_id": "job-1",
        "faces": [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}, "score": 0.9}],
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
    detector.detect.return_value = [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}}]
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


def test_face_frame_detector_applies_size_filters_to_external_result():
    processor = Mock()
    processor.execute_face_detect.return_value = {
        "faces": [
            {"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.11, "y2": 0.11}},
            {"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}},
        ]
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceDetectorAdapter(
        options={"min_width_ratio": 0.05, "min_height_ratio": 0.05},
        local_detector_factory=Mock(side_effect=AssertionError("local detector must not be built")),
        composition_factory=lambda: composition,
    )

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert len(faces) == 1
    assert faces[0]["bbox"]["x2"] == 0.3


def test_recognition_embedder_uses_face_native_embed_and_keeps_embeddings():
    processor = Mock()
    processor.execute_face_embed.return_value = {
        "execution_target": "external_worker",
        "job_id": "embed-1",
        "faces": [
            {
                "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4},
                "score": 0.9,
                "embedding": [0.1, 0.2, 0.3],
            }
        ],
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceEmbedderAdapter(
        options={"det_size": [640, 640], "det_thresh": 0.5, "max_num": 0},
        action="recognition_build_profiles",
        local_processor_factory=Mock(side_effect=AssertionError("local embedder must not be built")),
        composition_factory=lambda: composition,
    )

    faces = adapter.detect_and_embed(Path("/volume1/photo/album/image.jpg"))

    assert faces[0]["embedding"] == [0.1, 0.2, 0.3]
    kwargs = processor.execute_face_embed.call_args.kwargs
    assert kwargs["action"] == "recognition_build_profiles"
    assert kwargs["policy"] == "external_preferred"


def test_recognition_preview_bytes_remain_local():
    embedder = Mock()
    embedder.detect_and_embed_bytes.return_value = [{"embedding": [1.0]}]
    adapter = ExternalWorkerFaceEmbedderAdapter(
        options={},
        action="recognition_build_profiles",
        local_processor_factory=lambda: embedder,
        composition_factory=Mock(side_effect=AssertionError("composition must not be used for bytes")),
    )

    assert adapter.detect_and_embed_bytes(b"preview") == [{"embedding": [1.0]}]
    embedder.detect_and_embed_bytes.assert_called_once_with(b"preview")
