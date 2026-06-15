from pytest import approx
from types import SimpleNamespace
from unittest.mock import Mock, patch

from models.bbox import BoundingBox
from models.metadata_face import MetadataFace
from services.face_frame_matcher import frame_metrics, match_decision
from services.face_frame_standardizer import build_target_frame, target_frame
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


def test_standardization_strategies_use_source_and_insight_frames():
    source = BoundingBox(0.3, 0.3, 0.7, 0.7)
    insight = BoundingBox(0.4, 0.4, 0.6, 0.6)

    assert build_target_frame(source, insight, strategy="insightface_exact") == insight
    assert build_target_frame(source, insight, strategy="largest_plausible") == source
    averaged = build_target_frame(source, insight, strategy="average_sources")
    assert (averaged.x1, averaged.y1, averaged.x2, averaged.y2) == approx((0.35, 0.35, 0.65, 0.65))


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


def test_preview_options_normalize_individual_sources_and_selection_mode():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": {
            "photos": True,
            "acd": True,
            "microsoft": False,
            "mwg_regions": True,
        },
        "selection_mode": "review_all",
    })

    assert options["source_formats"] == ["ACD", "MWG_REGIONS", "PHOTOS"]
    assert options["include_metadata"] is True
    assert options["include_photos"] is True
    assert options["selection_mode"] == "review_all"


def test_face_frame_operation_modes_follow_checks_principle():
    assert FaceFrameStandardizationService.normalize_options({"operation_mode": "immediate"})["operation_mode"] == "immediate"
    assert FaceFrameStandardizationService.normalize_options({"operation_mode": "save_only"})["operation_mode"] == "save_only"
    assert FaceFrameStandardizationService.normalize_options({"operation_mode": "findings"})["operation_mode"] == "findings"
    assert FaceFrameStandardizationService.normalize_options({})["selection_mode"] == "review_all"


def test_prepared_detector_is_reused_for_identical_options():
    backend = SimpleNamespace(
        _configuredInsightFaceModelName=Mock(return_value="buffalo_l"),
        _configuredInsightFaceModelRoot=Mock(return_value="/models"),
    )
    service = FaceFrameStandardizationService(backend)
    detector = Mock()
    options = service.normalize_options({})

    with patch("services.face_frame_standardization_service.InsightFaceDetector", return_value=detector) as detector_class:
        first = service._prepared_detector(options)
        second = service._prepared_detector(options)

    assert first is second
    detector_class.assert_called_once()
    detector.prepare.assert_called_once()


def test_explicitly_disabling_all_sources_keeps_all_sources_disabled():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": {
            "photos": False,
            "acd": False,
            "microsoft": False,
            "mwg_regions": False,
        },
    })

    assert options["source_formats"] == []
    assert options["include_metadata"] is False
    assert options["include_photos"] is False


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
            options=service.normalize_options({"profile": "normal", "include_photos": False, "selection_mode": "review_all"}),
        )

    assert written["type"] == "face_frame_standardization"
    finding = written["payload"]["entries"][0]
    assert set(("item_id", "image_path", "source_frame", "target_frame", "match", "selection_state", "write_state", "target")) <= set(finding)
    assert finding["target"] == "preview"
    assert finding["write_state"] == "pending"
    assert finding["source_frame"]["x"] == approx(0.5)
    assert finding["source_frame"]["w"] == approx(0.2)
    progress_updates = [call.kwargs for call in backend._setCleanupProgress.call_args_list]
    assert any(update.get("status") == {"schema_version": 1} and update.get("message_key") == "cleanup:face_frames_review_required" for update in progress_updates)


def test_review_all_mode_does_not_preselect_safe_findings():
    written = {}
    metadata_faces = [
        MetadataFace.from_center_box(
            name="Person",
            x=0.5,
            y=0.5,
            w=0.2,
            h=0.2,
            source="metadata",
            source_format="ACD",
        ),
        MetadataFace.from_center_box(
            name="Other",
            x=0.5,
            y=0.5,
            w=0.2,
            h=0.2,
            source="metadata",
            source_format="MICROSOFT",
        ),
    ]
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(writeCheckFindings=Mock(side_effect=lambda finding_type, payload: written.update(payload=payload))),
        _configuredInsightFaceModelName=Mock(return_value="buffalo_l"),
        _configuredInsightFaceModelRoot=Mock(return_value="/models"),
        _readImageMetadata=Mock(return_value=SimpleNamespace(faces=metadata_faces)),
        _loadPhotoFacesForImage=Mock(return_value=[]),
        _shouldStopCleanup=Mock(return_value=False),
        _setCleanupProgress=Mock(),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
    )
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6}}]

    with patch("services.face_frame_standardization_service.InsightFaceDetector", return_value=detector):
        FaceFrameStandardizationService(backend)._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "sources": ["acd"],
                "selection_mode": "review_all",
            }),
        )

    assert len(written["payload"]["entries"]) == 1
    assert written["payload"]["entries"][0]["source_frame"]["source_format"] == "ACD"
    assert written["payload"]["entries"][0]["selection_state"] == "review"


def test_immediate_mode_resumes_after_previous_review_path():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": ["acd"],
        "operation_mode": "immediate",
        "selection_mode": "review_all",
    })
    previous = {
        "status": "review_required",
        "options": options,
        "scan_next_path_index": 1,
        "entries": [],
    }
    stored = {"face_frame_standardization": previous}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/first.jpg", "/photo/second.jpg"])),
        file_analysis=SimpleNamespace(
            readCheckFindings=Mock(side_effect=lambda finding_type: stored.get(finding_type, {})),
            writeCheckFindings=Mock(side_effect=lambda finding_type, payload: stored.__setitem__(finding_type, payload) or True),
        ),
        _configuredInsightFaceModelName=Mock(return_value="buffalo_l"),
        _configuredInsightFaceModelRoot=Mock(return_value="/models"),
        _readImageMetadata=Mock(return_value=SimpleNamespace(faces=[])),
        _loadPhotoFacesForImage=Mock(return_value=[]),
        _shouldStopCleanup=Mock(return_value=False),
        _setCleanupProgress=Mock(),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
    )
    detector = Mock()
    detector.detect.return_value = []

    with patch("services.face_frame_standardization_service.InsightFaceDetector", return_value=detector):
        FaceFrameStandardizationService(backend)._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=options,
        )

    backend._readImageMetadata.assert_called_once_with("/photo/second.jpg", include_unnamed_acd=True)
    detector.detect.assert_called_once()
    assert stored["face_frame_standardization"]["scan_next_path_index"] == 2


def test_update_selection_persists_manual_decision():
    payload = {"entries": [{"item_id": "one", "selection_state": "review"}]}
    backend = SimpleNamespace(
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(return_value=__import__("contextlib").nullcontext()),
            readCheckFindings=Mock(return_value=payload),
            writeCheckFindings=Mock(return_value=True),
        )
    )

    result = FaceFrameStandardizationService(backend).update_selection(item_id="one", selected=True)

    assert result["updated"] is True
    assert payload["entries"][0]["selection_state"] == "selected"


def test_sync_review_progress_uses_current_open_finding_and_list_progress():
    payload = {
        "entries": [
            {"item_id": "done", "image_path": "/photo/done.jpg", "selection_state": "selected", "write_state": "written"},
            {"item_id": "open", "image_path": "/photo/current.jpg", "selection_state": "review", "write_state": "pending"},
        ],
    }
    backend = SimpleNamespace(
        file_analysis=SimpleNamespace(readCheckFindings=Mock(return_value=payload)),
        _buildStatusPayload=Mock(side_effect=lambda **kwargs: kwargs),
        _buildStatusProgress=Mock(side_effect=lambda **kwargs: kwargs),
        _buildStatusCounter=Mock(side_effect=lambda key, **kwargs: {"key": key, **kwargs}),
        _setCleanupProgress=Mock(side_effect=lambda user_key, **kwargs: kwargs),
    )

    progress = FaceFrameStandardizationService(backend).sync_review_progress(user_key="user")

    assert progress["current_path"] == "/photo/current.jpg"
    assert progress["findings_count"] == 1
    assert progress["status"]["progress"]["kind"] == "entries"
    assert progress["status"]["progress"]["current"] == 1
    assert progress["status"]["progress"]["total"] == 2


def test_apply_selected_writes_metadata_and_locks_photos():
    payload = {
        "entries": [
            {
                "item_id": "metadata",
                "image_path": "/photo/test.jpg",
                "source_frame": {
                    "source": "metadata",
                    "source_format": "ACD",
                    "name": "Person",
                    "x": 0.5,
                    "y": 0.5,
                    "w": 0.2,
                    "h": 0.2,
                },
                "target_frame": {"bbox": {"x1": 0.3, "y1": 0.3, "x2": 0.7, "y2": 0.7}},
                "selection_state": "selected",
                "write_state": "pending",
                "warnings": [],
            },
            {
                "item_id": "photos",
                "image_path": "/photo/test.jpg",
                "source_frame": {"source": "photos", "source_format": "PHOTOS"},
                "target_frame": {"bbox": {"x1": 0.3, "y1": 0.3, "x2": 0.7, "y2": 0.7}},
                "selection_state": "selected",
                "write_state": "pending",
                "warnings": [],
            },
        ],
    }
    backend = SimpleNamespace(
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(return_value=__import__("contextlib").nullcontext()),
            readCheckFindings=Mock(return_value=payload),
            writeCheckFindings=Mock(return_value=True),
        ),
        replaceMetadataFacePosition=Mock(return_value={"updated": True}),
    )

    result = FaceFrameStandardizationService(backend).apply_selected()

    assert result["written_count"] == 1
    assert result["skipped_count"] == 1
    assert payload["entries"][0]["write_state"] == "written"
    assert payload["entries"][1]["write_state"] == "locked"
    replacement = backend.replaceMetadataFacePosition.call_args.kwargs["source_face_data"]
    assert replacement["x"] == approx(0.5)
    assert replacement["w"] == approx(0.4)


def test_safe_mode_automatically_applies_safe_metadata_findings():
    stored = {}
    file_analysis = SimpleNamespace(
        lockCheckFindings=Mock(side_effect=lambda finding_type: __import__("contextlib").nullcontext()),
        readCheckFindings=Mock(side_effect=lambda finding_type: stored.get(finding_type, {})),
        writeCheckFindings=Mock(side_effect=lambda finding_type, payload: stored.__setitem__(finding_type, payload) or True),
    )
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=file_analysis,
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
                source_format="ACD",
            ),
        ])),
        _loadPhotoFacesForImage=Mock(return_value=[]),
        _shouldStopCleanup=Mock(return_value=False),
        _setCleanupProgress=Mock(),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
        replaceMetadataFacePosition=Mock(return_value={"updated": True}),
    )
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6}}]

    with patch("services.face_frame_standardization_service.InsightFaceDetector", return_value=detector):
        FaceFrameStandardizationService(backend)._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "sources": ["acd"],
                "selection_mode": "safe_matches",
            }),
        )

    entry = stored["face_frame_standardization"]["entries"][0]
    assert entry["selection_state"] == "selected"
    assert entry["write_state"] == "written"
    backend.replaceMetadataFacePosition.assert_called_once()
