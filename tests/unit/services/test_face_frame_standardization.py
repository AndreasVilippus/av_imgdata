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


def test_match_decision_uses_configured_deviation_thresholds():
    metrics = {"iou": 0.60, "center_delta": 0.04, "size_delta": 0.10}

    assert match_decision(metrics) == "review"
    assert match_decision(metrics, safe_iou=0.55) == "safe"
    assert match_decision(metrics, safe_iou=0.55, safe_center_delta=0.03) == "review"
    assert match_decision(metrics, review_iou=0.70) == "conflict"


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
    assert options["safe_iou"] == 0.65
    assert options["review_iou"] == 0.30
    assert options["safe_center_delta"] == 0.08
    assert options["safe_size_delta"] == 0.50


def test_preview_options_normalize_decision_thresholds():
    options = FaceFrameStandardizationService.normalize_options({
        "safe_iou": 2,
        "review_iou": -1,
        "safe_center_delta": 0.12,
        "safe_size_delta": 0.25,
    })

    assert options["safe_iou"] == 1.0
    assert options["review_iou"] == 0.0
    assert options["safe_center_delta"] == 0.12
    assert options["safe_size_delta"] == 0.25


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

    backend._createFaceDetector = Mock(return_value=detector)

    first = service._prepared_detector(options)
    second = service._prepared_detector(options)

    assert first is second
    backend._createFaceDetector.assert_called_once()
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


def test_preview_run_keeps_required_finding_fields_in_active_run_state():
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(writeCheckFindings=Mock()),
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

    backend._createFaceDetector = Mock(return_value=detector)
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=service.normalize_options({"profile": "normal", "include_photos": False, "selection_mode": "review_all"}),
        )

    backend.file_analysis.writeCheckFindings.assert_not_called()
    active = service.findings(user_key="user", operation_mode="immediate")
    finding = active["entries"][0]
    assert set(("item_id", "image_path", "source_frame", "target_frame", "match", "selection_state", "write_state", "target")) <= set(finding)
    assert finding["target"] == "preview"
    assert finding["write_state"] == "pending"
    assert finding["source_frame"]["x"] == approx(0.5)
    assert finding["source_frame"]["w"] == approx(0.2)
    progress_updates = [call.kwargs for call in backend._setCleanupProgress.call_args_list]
    assert any(update.get("status") == {"schema_version": 1} and update.get("message_key") == "cleanup:face_frames_review_required" for update in progress_updates)


def test_save_only_run_writes_persisted_findings_list():
    stored = {}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(
            writeCheckFindings=Mock(side_effect=lambda finding_type, payload: stored.__setitem__(finding_type, payload) or True),
        ),
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
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6}}]

    backend._createFaceDetector = Mock(return_value=detector)
    FaceFrameStandardizationService(backend)._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "operation_mode": "save_only",
                "profile": "normal",
                "include_photos": False,
            }),
        )

    assert stored["face_frame_standardization"]["mode"] == "save_only"
    assert stored["face_frame_standardization"]["entries"][0]["write_state"] == "pending"


def test_review_all_mode_does_not_preselect_safe_findings():
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
        file_analysis=SimpleNamespace(writeCheckFindings=Mock()),
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

    service = FaceFrameStandardizationService(backend)
    backend._createFaceDetector = Mock(return_value=detector)
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "sources": ["acd"],
                "selection_mode": "review_all",
            }),
        )

    active = service.findings(user_key="user", operation_mode="immediate")
    assert len(active["entries"]) == 1
    assert active["entries"][0]["source_frame"]["source_format"] == "ACD"
    assert active["entries"][0]["selection_state"] == "review"


def test_standardization_passes_configured_thresholds_to_match_decision():
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
    ]
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(writeCheckFindings=Mock()),
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

    service = FaceFrameStandardizationService(backend)
    backend._createFaceDetector = Mock(return_value=detector)
    with patch("services.face_frame_standardization_service.match_decision", return_value="review") as decision:
        service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "sources": ["acd"],
                "safe_iou": 0.72,
                "review_iou": 0.44,
                "safe_center_delta": 0.06,
                "safe_size_delta": 0.40,
            }),
        )

    assert decision.call_args.kwargs == {
        "safe_iou": 0.72,
        "review_iou": 0.44,
        "safe_center_delta": 0.06,
        "safe_size_delta": 0.40,
    }


def test_immediate_mode_resumes_after_previous_review_path():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": ["acd"],
        "operation_mode": "immediate",
        "selection_mode": "review_all",
        "resume_existing": True,
    })
    previous = {
        "status": "review_required",
        "options": options,
        "scan_next_path_index": 1,
        "entries": [],
    }
    stored = {"face_frame_standardization": {}}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/first.jpg", "/photo/second.jpg"])),
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(side_effect=lambda finding_type: __import__("contextlib").nullcontext()),
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

    service = FaceFrameStandardizationService(backend)
    service._write_active_findings("user", previous)
    backend._createFaceDetector = Mock(return_value=detector)
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=options,
        )

    backend._readImageMetadata.assert_called_once_with("/photo/second.jpg", include_unnamed_acd=True)
    detector.detect.assert_called_once()
    assert service.findings(user_key="user", operation_mode="immediate")["scan_next_path_index"] == 2


def test_immediate_mode_explicit_start_ignores_previous_partial_findings():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": ["acd"],
        "operation_mode": "immediate",
        "selection_mode": "safe_matches",
    })
    previous_options = FaceFrameStandardizationService.normalize_options({
        "sources": ["acd"],
        "operation_mode": "immediate",
        "selection_mode": "safe_matches",
    })
    previous = {
        "status": "review_required",
        "options": previous_options,
        "scan_next_path_index": 1,
        "entries": [
            {
                "item_id": "old",
                "image_path": "/photo/old.jpg",
                "selection_state": "review",
                "write_state": "pending",
            },
        ],
    }
    stored = {"face_frame_standardization": previous}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/first.jpg", "/photo/second.jpg"])),
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(side_effect=lambda finding_type: __import__("contextlib").nullcontext()),
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

    backend._createFaceDetector = Mock(return_value=detector)
    service = FaceFrameStandardizationService(backend)
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=options,
        )

    backend._readImageMetadata.assert_any_call("/photo/first.jpg", include_unnamed_acd=True)
    assert stored["face_frame_standardization"] == previous
    backend.file_analysis.writeCheckFindings.assert_not_called()
    assert service.findings(user_key="user", operation_mode="immediate")["scan_next_path_index"] == 2
    assert service.findings(user_key="user", operation_mode="immediate")["entries"] == []


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

    progress = FaceFrameStandardizationService(backend).sync_review_progress(user_key="user", operation_mode="findings")

    assert progress["current_path"] == "/photo/current.jpg"
    assert progress["findings_count"] == 1
    assert progress["status"]["progress"]["kind"] == "entries"
    assert progress["status"]["progress"]["current"] == 1
    assert progress["status"]["progress"]["total"] == 2


def test_apply_selected_writes_metadata_and_photos():
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
                "source_frame": {
                    "source": "photos",
                    "source_format": "PHOTOS",
                    "name": "Person",
                    "face_id": 77,
                    "person_id": 11,
                    "item_id": 42,
                },
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
        replacePhotosFacePosition=Mock(return_value={"updated": True}),
    )

    result = FaceFrameStandardizationService(backend).apply_selected(
        user_key="user",
        cookies={"_SSID": "sid"},
        base_url="https://example.test",
    )

    assert result["written_count"] == 2
    assert result["skipped_count"] == 0
    assert payload["entries"][0]["write_state"] == "written"
    assert payload["entries"][1]["write_state"] == "written"
    replacement = backend.replaceMetadataFacePosition.call_args.kwargs["source_face_data"]
    assert replacement["x"] == approx(0.5)
    assert replacement["w"] == approx(0.4)
    photos_call = backend.replacePhotosFacePosition.call_args.kwargs
    assert photos_call["user_key"] == "user"
    assert photos_call["cookies"] == {"_SSID": "sid"}
    assert photos_call["base_url"] == "https://example.test"
    assert photos_call["face_data"]["face_id"] == 77
    assert photos_call["source_face_data"]["w"] == approx(0.4)


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

    service = FaceFrameStandardizationService(backend)
    backend._createFaceDetector = Mock(return_value=detector)
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "sources": ["acd"],
                "selection_mode": "safe_matches",
            }),
        )

    file_analysis.writeCheckFindings.assert_not_called()
    entry = service.findings(user_key="user", operation_mode="immediate")["entries"][0]
    assert entry["selection_state"] == "selected"
    assert entry["write_state"] == "written"
    backend.replaceMetadataFacePosition.assert_called_once()


def test_safe_mode_automatically_selects_safe_photos_findings():
    entries = [
        {
            "source_frame": {"source_format": "PHOTOS"},
            "match": {"decision": "safe"},
            "selection_state": "review",
            "write_state": "pending",
        }
    ]

    FaceFrameStandardizationService._prepare_automatic_selections(entries)

    assert entries[0]["selection_state"] == "selected"


def test_safe_mode_recalculates_open_selections_from_previous_manual_run():
    options = FaceFrameStandardizationService.normalize_options({
        "sources": ["acd"],
        "selection_mode": "safe_matches",
        "resume_existing": True,
    })
    previous = {
        "options": FaceFrameStandardizationService.normalize_options({
            "sources": ["acd"],
            "selection_mode": "review_all",
        }),
        "entries": [
            {
                "item_id": "safe",
                "image_path": "/photo/safe.jpg",
                "source_frame": {"source_format": "ACD", "name": "Safe"},
                "target_frame": {"bbox": {"x1": 0.3, "y1": 0.3, "x2": 0.7, "y2": 0.7}},
                "match": {"decision": "safe"},
                "selection_state": "review",
                "write_state": "pending",
                "warnings": [],
            },
            {
                "item_id": "review",
                "image_path": "/photo/review.jpg",
                "source_frame": {"source_format": "ACD", "name": "Review"},
                "target_frame": {"bbox": {"x1": 0.3, "y1": 0.3, "x2": 0.7, "y2": 0.7}},
                "match": {"decision": "review"},
                "selection_state": "selected",
                "write_state": "pending",
                "warnings": [],
            },
        ],
    }
    stored = {"face_frame_standardization": {}}
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=[])),
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(side_effect=lambda finding_type: __import__("contextlib").nullcontext()),
            readCheckFindings=Mock(side_effect=lambda finding_type: stored.get(finding_type, {})),
            writeCheckFindings=Mock(side_effect=lambda finding_type, payload: stored.__setitem__(finding_type, payload) or True),
        ),
        _configuredInsightFaceModelName=Mock(return_value="buffalo_l"),
        _configuredInsightFaceModelRoot=Mock(return_value="/models"),
        _shouldStopCleanup=Mock(return_value=False),
        _setCleanupProgress=Mock(),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
        replaceMetadataFacePosition=Mock(return_value={"updated": True}),
    )

    service = FaceFrameStandardizationService(backend)
    service._write_active_findings("user", previous)
    backend._createFaceDetector = Mock(return_value=Mock())
    service._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=options,
        )

    entries = service.findings(user_key="user", operation_mode="immediate")["entries"]
    safe = next(entry for entry in entries if entry["item_id"] == "safe")
    review = next(entry for entry in entries if entry["item_id"] == "review")
    assert safe["selection_state"] == "selected"
    assert safe["write_state"] == "written"
    assert review["selection_state"] == "review"
    assert review["write_state"] == "pending"
    backend.replaceMetadataFacePosition.assert_called_once()


def test_face_frame_progress_overwrites_legacy_fields_on_new_status():
    captured = []
    backend = SimpleNamespace(
        _setCleanupProgress=Mock(side_effect=lambda user_key, **updates: captured.append((user_key, updates)) or updates),
        _buildStatusPayload=Mock(return_value={"schema_version": 1}),
        _buildStatusProgress=Mock(return_value={}),
        _buildStatusCounter=Mock(return_value={}),
    )

    FaceFrameStandardizationService(backend)._set_progress(
        "user",
        running=True,
        finished=False,
        phase="listing_files",
        message_key="cleanup:face_frames_listing_files",
        message="Building image list.",
        options=FaceFrameStandardizationService.normalize_options({}),
    )

    _user_key, update = captured[0]
    assert update["files_scanned"] == 0
    assert update["total_files"] == 0
    assert update["findings_count"] == 0
    assert update["selected_count"] == 0
    assert update["written_count"] == 0
    assert update["errors_count"] == 0
    assert update["current_path"] == ""


def test_face_frame_status_uses_file_progress_and_detail_counters():
    counters = []
    backend = SimpleNamespace(
        _buildStatusProgress=Mock(side_effect=lambda **kwargs: kwargs),
        _buildStatusCounter=Mock(side_effect=lambda key, **kwargs: counters.append((key, kwargs)) or {"key": key, **kwargs}),
        _buildStatusPayload=Mock(side_effect=lambda **kwargs: kwargs),
    )

    status = FaceFrameStandardizationService(backend)._status(
        phase="running",
        files_scanned=12,
        total_files=65,
        findings_count=3,
        selected_count=2,
        written_count=1,
        errors_count=0,
    )

    assert status["progress"]["kind"] == "files"
    assert status["mode"] == "scan"
    assert status["progress"]["current"] == 12
    assert status["progress"]["total"] == 65
    assert [key for key, _kwargs in counters] == ["checked", "findings", "automatic", "written", "errors"]
    labels = {key: kwargs["label_key"] for key, kwargs in counters}
    assert labels["checked"] == "cleanup:label_checked_count"
    assert labels["automatic"] == "cleanup:label_automatic"
    assert labels["written"] == "cleanup:label_corrected"


def test_face_frame_review_status_schema_uses_integrated_modes():
    backend = SimpleNamespace(
        _setCleanupProgress=Mock(side_effect=lambda _user_key, **updates: updates),
        _buildStatusProgress=Mock(side_effect=lambda **kwargs: kwargs),
        _buildStatusCounter=Mock(side_effect=lambda key, **kwargs: {"key": key, **kwargs}),
        _buildStatusPayload=Mock(side_effect=lambda **kwargs: kwargs),
        file_analysis=SimpleNamespace(readCheckFindings=Mock(return_value={
            "entries": [{"item_id": "stored", "selection_state": "review", "write_state": "pending"}],
        })),
    )
    service = FaceFrameStandardizationService(backend)
    service._write_active_findings("user", {
        "entries": [{"item_id": "active", "selection_state": "review", "write_state": "pending"}],
    })

    active = service.sync_review_progress(user_key="user", operation_mode="immediate")
    stored = service.sync_review_progress(user_key="user", operation_mode="findings")

    assert active["status"]["mode"] == "scan"
    assert stored["status"]["mode"] == "findings"


def test_save_only_start_ignores_persisted_findings_without_explicit_resume():
    stored = {
        "face_frame_standardization": {
            "mode": "save_only",
            "entries": [
                {
                    "item_id": FaceFrameStandardizationService._finding_id("/photo/test.jpg", "ACD", 0),
                    "image_path": "/photo/test.jpg",
                    "selection_state": "selected",
                    "write_state": "written",
                },
            ],
        },
    }
    backend = SimpleNamespace(
        core=SimpleNamespace(getSharedFolder=Mock(return_value="/photo")),
        checks_workflow=SimpleNamespace(get_candidate_paths=Mock(return_value=["/photo/test.jpg"])),
        file_analysis=SimpleNamespace(
            lockCheckFindings=Mock(side_effect=lambda finding_type: __import__("contextlib").nullcontext()),
            readCheckFindings=Mock(side_effect=lambda finding_type: stored.get(finding_type, {})),
            writeCheckFindings=Mock(side_effect=lambda finding_type, payload: stored.__setitem__(finding_type, payload) or True),
        ),
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
    )
    detector = Mock()
    detector.detect.return_value = [{"bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6}}]

    backend._createFaceDetector = Mock(return_value=detector)
    FaceFrameStandardizationService(backend)._run(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            options=FaceFrameStandardizationService.normalize_options({
                "operation_mode": "save_only",
                "sources": ["acd"],
            }),
        )

    assert len(stored["face_frame_standardization"]["entries"]) == 1
    assert stored["face_frame_standardization"]["entries"][0]["write_state"] == "pending"
