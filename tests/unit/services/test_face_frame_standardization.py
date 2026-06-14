from pytest import approx
from types import SimpleNamespace
from unittest.mock import Mock, patch

from models.bbox import BoundingBox
from models.metadata_face import MetadataFace
from services.face_frame_matcher import frame_metrics, match_decision
from services.face_frame_standardizer import target_frame
from services.face_frame_standardization_service import FaceFrameStandardizationService


def test_exact_frame_is_safe():
    box = BoundingBox(0.4, 0.4, 0.6, 0.6)

    metrics = frame_metrics(box, box)

    assert metrics == approx({"iou": 1.0, "center_delta": 0.0, "size_delta": 0.0})
    assert match_decision(metrics) == "safe"


def test_unrelated_frame_is_conflict():
    metrics = frame_metrics(
        BoundingBox(0.0, 0.0, 0.2, 0.2),
        BoundingBox(0.8, 0.8, 1.0, 1.0),
    )

    assert match_decision(metrics) == "conflict"


def test_normal_profile_expands_and_shifts_detected_frame_up():
    detected = BoundingBox(0.4, 0.4, 0.6, 0.6)

    target = target_frame(detected, profile="normal")

    assert target.width() == approx(0.23)
    assert target.height() == approx(0.25)
    assert target.center()[1] < detected.center()[1]


def test_preview_options_cannot_enable_writes_and_are_bounded():
    options = FaceFrameStandardizationService.normalize_options({
        "target": "photos",
        "profile": "unknown",
        "changed_since_days": -4,
        "det_thresh": 3,
    })

    assert options["mode"] == "preview"
    assert options["target"] == "preview"
    assert options["profile"] == "normal"
    assert options["changed_since_days"] == 0
    assert options["det_thresh"] == 1.0


def test_preview_run_persists_required_finding_fields():
    written = {}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(writeCheckFindings=Mock(side_effect=lambda finding_type, payload: written.update(type=finding_type, payload=payload))),
        _configuredInsightFaceModelName=Mock(return_value="buffalo_l"),
        _configuredInsightFaceModelRoot=Mock(return_value="/models"),
        _readImageMetadata=Mock(return_value=SimpleNamespace(faces=[
            MetadataFace.from_center_box(
                name="Person",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MWG_REGIONS",
            ),
        ])),
        _loadPhotoFacesForImage=Mock(return_value=[]),
        _shouldStopCleanup=Mock(return_value=False),
        _setCleanupProgress=Mock(),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
    )
    service = FaceFrameStandardizationService(backend)
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6}}]

    with patch("services.face_frame_standardization_service.InsightFaceDetector", return_value=detector):
        service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=service.normalize_options({"profile": "normal", "include_photos": False}),
        )

    assert written["type"] == "face_frame_standardization"
    finding = written["payload"]["entries"][0]
    assert set(("item_id", "image_path", "source_frame", "target_frame", "match", "selection_state", "write_state", "target")) <= set(finding)
    assert finding["target"] == "preview"
    assert finding["write_state"] == "pending"
