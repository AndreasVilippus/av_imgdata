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
    processor.execute_face_detect.return_value = {"execution_target": "external_worker", "job_id": "job-1", "faces": [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}, "score": 0.9}]}
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceDetectorAdapter(options={"det_size": [640, 640], "det_thresh": 0.5, "max_num": 0}, local_detector_factory=local_factory, composition_factory=lambda: composition)

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert faces[0]["score"] == 0.9
    composition.external_face_processor.assert_called_once()
    assert composition.external_face_processor.call_args.kwargs["nas_root"] == Path("/volume1/photo")
    assert callable(composition.external_face_processor.call_args.kwargs["debug_logger"])
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
    adapter = ExternalWorkerFaceDetectorAdapter(options={}, local_detector_factory=lambda: detector, composition_factory=lambda: composition)

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert len(faces) == 1
    detector.detect.assert_called_once()
    composition.external_face_processor.assert_not_called()


def test_face_frame_detector_applies_size_filters_to_external_result():
    processor = Mock()
    processor.execute_face_detect.return_value = {"faces": [{"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.11, "y2": 0.11}}, {"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}}]}
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceDetectorAdapter(options={"min_width_ratio": 0.05, "min_height_ratio": 0.05}, local_detector_factory=Mock(side_effect=AssertionError("local detector must not be built")), composition_factory=lambda: composition)

    faces = adapter.detect(Path("/volume1/photo/album/image.jpg"))

    assert len(faces) == 1
    assert faces[0]["bbox"]["x2"] == 0.3


def test_face_detector_many_uses_batch_contract_when_available():
    processor = Mock()
    processor.has_compatible_worker.return_value = True
    processor.execute_face_detect_batch.return_value = {
        "execution_target": "external_worker",
        "job_id": "detect-batch-1",
        "images": {
            "/volume1/photo/album/a.jpg": [{"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}}],
            "/volume1/photo/album/b.jpg": [],
        },
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceDetectorAdapter(options={}, local_processor_factory=Mock(side_effect=AssertionError("local detector must not be built")), composition_factory=lambda: composition)

    result = adapter.detect_many([Path("/volume1/photo/album/a.jpg"), Path("/volume1/photo/album/b.jpg")])

    assert len(result["/volume1/photo/album/a.jpg"]) == 1
    processor.has_compatible_worker.assert_called_once_with(processor.FACE_DETECT_BATCH_CAPABILITY)
    processor.execute_face_detect_batch.assert_called_once()


def test_recognition_embedder_uses_face_native_embed_and_keeps_embeddings():
    processor = Mock()
    processor.execute_face_embed.return_value = {"execution_target": "external_worker", "job_id": "embed-1", "faces": [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}, "score": 0.9, "embedding": [0.1, 0.2, 0.3]}]}
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceEmbedderAdapter(options={"det_size": [640, 640], "det_thresh": 0.5, "max_num": 0}, action="recognition_build_profiles", local_processor_factory=Mock(side_effect=AssertionError("local embedder must not be built")), composition_factory=lambda: composition)

    faces = adapter.detect_and_embed(Path("/volume1/photo/album/image.jpg"))

    assert faces[0]["embedding"] == [0.1, 0.2, 0.3]
    kwargs = processor.execute_face_embed.call_args.kwargs
    assert kwargs["action"] == "recognition_build_profiles"
    assert kwargs["policy"] == "external_preferred"


def test_recognition_many_uses_face_native_embed_batch():
    processor = Mock()
    processor.has_compatible_worker.return_value = True
    processor.execute_face_embed_batch.return_value = {
        "execution_target": "external_worker",
        "job_id": "embed-batch-1",
        "images": {
            "/volume1/photo/album/a.jpg": [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}, "embedding": [1.0, 0.0]}],
            "/volume1/photo/album/b.jpg": [{"bbox": {"x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4}, "embedding": [0.0, 1.0]}],
        },
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceEmbedderAdapter(options={}, action="recognition_build_profiles", local_processor_factory=Mock(side_effect=AssertionError("local embedder must not be built")), composition_factory=lambda: composition)

    result = adapter.detect_and_embed_many([Path("/volume1/photo/album/a.jpg"), Path("/volume1/photo/album/b.jpg")])

    assert result["/volume1/photo/album/a.jpg"][0]["embedding"] == [1.0, 0.0]
    assert result["/volume1/photo/album/b.jpg"][0]["embedding"] == [0.0, 1.0]
    processor.has_compatible_worker.assert_called_once_with(processor.FACE_EMBED_BATCH_CAPABILITY)
    processor.execute_face_embed_batch.assert_called_once()


def test_recognition_many_can_start_and_finish_external_batch_separately():
    processor = Mock()
    processor.has_compatible_worker.return_value = True
    processor.start_face_embed_batch.return_value = {
        "job_id": "embed-batch-1",
        "capability": "face_native_embed_batch",
        "image_paths": [Path("/volume1/photo/album/a.jpg"), Path("/volume1/photo/album/b.jpg")],
    }
    processor.finish_face_batch.return_value = {
        "/volume1/photo/album/a.jpg": [{"bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}, "embedding": [1.0, 0.0]}],
        "/volume1/photo/album/b.jpg": [{"bbox": {"x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4}, "embedding": [0.0, 1.0]}],
    }
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceEmbedderAdapter(options={}, action="recognition_build_profiles", local_processor_factory=Mock(side_effect=AssertionError("local embedder must not be built")), composition_factory=lambda: composition)
    adapter.set_external_worker_operation_id("cleanup-recognition-op-1")

    handle = adapter.start_detect_and_embed_many([Path("/volume1/photo/album/a.jpg"), Path("/volume1/photo/album/b.jpg")])
    result = adapter.finish_detect_and_embed_many(handle)

    assert handle["job_id"] == "embed-batch-1"
    assert result["/volume1/photo/album/a.jpg"][0]["embedding"] == [1.0, 0.0]
    kwargs = processor.start_face_embed_batch.call_args.kwargs
    assert kwargs["operation_id"] == "cleanup-recognition-op-1"
    processor.finish_face_batch.assert_called_once_with(handle)


def test_recognition_adapter_cancels_jobs_for_current_operation():
    worker_api = Mock()
    worker_api.cancel_jobs_by_origin.return_value = {"status": "cancelled", "cancelled_jobs": 2}
    composition = Mock()
    composition.enabled.return_value = True
    composition.worker_api = worker_api
    adapter = ExternalWorkerFaceEmbedderAdapter(options={}, action="recognition_build_profiles", local_processor_factory=Mock(), composition_factory=lambda: composition)

    result = adapter.cancel_external_worker_operation("cleanup-recognition-op-1", reason="stopped")

    assert result["cancelled_jobs"] == 2
    worker_api.cancel_jobs_by_origin.assert_called_once_with(
        origin_filter={"operation_id": "cleanup-recognition-op-1", "action": "recognition_build_profiles"},
        reason="stopped",
    )


def test_recognition_rank_and_profile_math_use_vector_worker_contracts():
    processor = Mock()
    processor.execute_rank_embeddings.return_value = {"result": {"ranks": [{"best_index": 0, "best_score": 0.9}]}}
    processor.execute_profile_math.return_value = {"result": {"centroid_embedding": [1.0, 0.0], "medoid_index": 0, "intra_person_similarity": 0.8}}
    composition = Mock()
    composition.enabled.return_value = True
    composition.external_face_processor.return_value = processor
    adapter = ExternalWorkerFaceEmbedderAdapter(options={}, action="recognition_build_profiles", local_processor_factory=Mock(side_effect=AssertionError("local embedder must not be built")), composition_factory=lambda: composition)

    ranks = adapter.rank_embeddings([[1.0, 0.0]], [[1.0, 0.0]])
    math_result = adapter.profile_math([[1.0, 0.0]])

    assert ranks[0]["best_score"] == 0.9
    assert math_result["medoid_index"] == 0
    processor.execute_rank_embeddings.assert_called_once()
    processor.execute_profile_math.assert_called_once()


def test_recognition_preview_bytes_remain_local():
    embedder = Mock()
    embedder.detect_and_embed_bytes.return_value = [{"embedding": [1.0]}]
    adapter = ExternalWorkerFaceEmbedderAdapter(options={}, action="recognition_build_profiles", local_processor_factory=lambda: embedder, composition_factory=Mock(side_effect=AssertionError("composition must not be used for bytes")))

    assert adapter.detect_and_embed_bytes(b"preview") == [{"embedding": [1.0]}]
    embedder.detect_and_embed_bytes.assert_called_once_with(b"preview")
