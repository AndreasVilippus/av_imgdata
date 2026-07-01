from types import SimpleNamespace

import services.face_recognition_service as face_recognition_module
from services.face_recognition_service import FaceRecognitionService


class _Findings:
    def __init__(self):
        self.values = {}

    def readCheckFindings(self, finding_type):
        return self.values.get(finding_type, {})

    def writeCheckFindings(self, finding_type, payload):
        self.values[finding_type] = payload
        return True

    def readRuntimeState(self, state_type, state_key):
        return self.values.get((state_type, state_key), {})

    def writeRuntimeState(self, state_type, state_key, payload):
        self.values[(state_type, state_key)] = payload
        return True


def _service():
    file_analysis = _Findings()
    backend = SimpleNamespace(
        file_analysis=file_analysis,
        _configuredInsightFaceModelName=lambda: "test_model",
        _buildStatusCounter=lambda key, **kwargs: {"key": key, **kwargs},
        _buildStatusProgress=lambda **kwargs: kwargs,
        _buildStatusPayload=lambda **kwargs: kwargs,
        _setCleanupProgress=lambda *args, **kwargs: None,
    )
    return FaceRecognitionService(backend), file_analysis


def test_profile_math_builds_normalized_centroid_and_medoid():
    centroid = FaceRecognitionService._centroid([[1.0, 0.0], [0.8, 0.2]])

    assert round(sum(value * value for value in centroid), 6) == 1.0
    assert FaceRecognitionService._medoid_index([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]]) == 1


def test_review_updates_only_persisted_recognition_finding():
    service, findings = _service()
    findings.values[service.FINDING_OUTLIERS] = {
        "entries": [{"outlier_id": "out-1", "selection_state": "review", "review_state": "suspected", "write_state": "internal_only"}]
    }

    result = service.update_review(action=service.ACTION_OUTLIERS, item_id="out-1", decision="excluded")

    assert result["updated"] is True
    entry = findings.values[service.FINDING_OUTLIERS]["entries"][0]
    assert entry["review_state"] == "excluded"
    assert entry["selection_state"] == "selected"


def test_item_path_accepts_direct_folder_payload_from_photos_api(tmp_path):
    service, _findings = _service()
    service.backend.photos = SimpleNamespace(
        getFotoTeamFolder=lambda **_kwargs: {"id": 20, "name": "2026/2026.05"}
    )
    service.backend._buildPhotoImagePath = lambda shared_folder, folder_name, filename: f"{shared_folder}/{folder_name}/{filename}"

    image_path = service._item_path(
        user_key="u",
        cookies={},
        base_url="https://dsm",
        shared_folder=str(tmp_path),
        item={"folder_id": 20, "filename": "image.jpg"},
        folder_cache={},
    )

    assert image_path == f"{tmp_path}/2026/2026.05/image.jpg"


def test_missing_reference_image_is_reported_in_quality_and_log():
    service, _findings = _service()
    logs = []
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))

    service._record_reference_image_missing(
        person={"id": 1, "name": "Ada"},
        item={"id": 10, "folder_id": 20, "filename": "missing.jpg"},
        image_path="/volume1/photo/missing.jpg",
    )

    assert service._image_quality_issues[0]["quality"] == "image_missing"
    assert service._image_quality_issues[0]["person_name"] == "Ada"
    assert logs[0][0] == "recognition_reference_image_missing"


def test_immediate_recognition_findings_do_not_use_persisted_list():
    service, findings = _service()
    findings.values[service.FINDING_SUGGESTIONS] = {
        "entries": [{"suggestion_id": "old", "selection_state": "review"}],
    }

    assert service.findings(
        service.ACTION_SUGGEST,
        user_key="user",
        operation_mode="immediate",
    ) == {}

    service._write_findings(
        service.FINDING_SUGGESTIONS,
        service.ACTION_SUGGEST,
        service.normalize_options({"operation_mode": "immediate"}),
        [{"suggestion_id": "active", "selection_state": "review"}],
        user_key="user",
    )

    assert findings.values[service.FINDING_SUGGESTIONS]["entries"][0]["suggestion_id"] == "old"
    assert service.findings(
        service.ACTION_SUGGEST,
        user_key="user",
        operation_mode="immediate",
    )["entries"][0]["suggestion_id"] == "active"
    assert service.findings(
        service.ACTION_SUGGEST,
        user_key="user",
        operation_mode="findings",
    )["entries"][0]["suggestion_id"] == "old"


def test_apply_uses_persisted_selected_suggestion_and_existing_assign_orchestration():
    service, findings = _service()
    calls = []
    service.backend.assignMatchedFaceToKnownPerson = lambda **kwargs: calls.append(kwargs) or {"updated": True}
    findings.values[service.FINDING_SUGGESTIONS] = {
        "entries": [{
            "suggestion_id": "rec-1",
            "selection_state": "selected",
            "write_state": "pending",
            "unknown_face_id": 11,
            "best_person_id": 22,
            "best_person_name": "Person",
            "image_id": 33,
            "image_path": "/volume1/photo/a.jpg",
        }]
    }

    result = service.apply_suggestions(user_key="u", cookies={}, base_url="https://dsm")

    assert result["written_count"] == 1
    assert calls[0]["face_id"] == 11
    assert calls[0]["item_id"] == 33
    assert findings.values[service.FINDING_SUGGESTIONS]["entries"][0]["write_state"] == "written"


def test_assignment_scan_finds_known_photos_face_matching_other_profile():
    service, findings = _service()
    options = service.normalize_options({"operation_mode": "save_only", "review_score": 0.5, "min_margin": 0.05})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [
            {
                "person_id": 1,
                "person_name": "Current",
                "used_count": 3,
                "centroid_embedding": [1.0, 0.0],
                "medoid": {"image_path": "/current.jpg", "bbox": {}},
            },
            {
                "person_id": 2,
                "person_name": "Suggested",
                "used_count": 3,
                "centroid_embedding": [0.0, 1.0],
                "medoid": {"image_path": "/suggested.jpg", "bbox": {"top": 0}},
            },
        ],
    }
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: "/volume1/photo")
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [{"id": 1, "name": "Current"}])
    service._prepared_embedder = lambda _options: SimpleNamespace()
    service._person_references = lambda **_kwargs: [{
        "face_id": 11,
        "image_id": 22,
        "image_path": "/volume1/photo/a.jpg",
        "bbox": {"left": 0.1},
        "embedding": [0.0, 1.0],
    }]

    service._build_assignment_suggestions(user_key="u", cookies={}, base_url="https://dsm", options=options)

    payload = findings.values[service.FINDING_ASSIGNMENTS]
    entry = payload["entries"][0]
    assert payload["action"] == service.ACTION_ASSIGNMENT
    assert entry["suggestion_id"] == "assign-11"
    assert entry["current_person_id"] == 1
    assert entry["best_person_id"] == 2
    assert entry["best_person_name"] == "Suggested"
    assert entry["selection_state"] == "review"


def test_apply_assignment_suggestion_uses_assignment_findings_type():
    service, findings = _service()
    calls = []
    service.backend.assignMatchedFaceToKnownPerson = lambda **kwargs: calls.append(kwargs) or {"updated": True}
    findings.values[service.FINDING_ASSIGNMENTS] = {
        "entries": [{
            "suggestion_id": "assign-1",
            "selection_state": "selected",
            "write_state": "pending",
            "unknown_face_id": 11,
            "current_person_id": 1,
            "current_person_name": "Current",
            "best_person_id": 22,
            "best_person_name": "Suggested",
            "image_id": 33,
            "image_path": "/volume1/photo/a.jpg",
        }]
    }

    result = service.apply_suggestions(
        user_key="u",
        cookies={},
        base_url="https://dsm",
        action=service.ACTION_ASSIGNMENT,
    )

    assert result["written_count"] == 1
    assert calls[0]["face_id"] == 11
    assert calls[0]["person_id"] == 22
    assert findings.values[service.FINDING_ASSIGNMENTS]["entries"][0]["write_state"] == "written"


def test_assignment_resume_skips_persons_before_previous_review_finding():
    service, findings = _service()
    options = service.normalize_options({"operation_mode": "immediate", "resume_existing": True})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [
            {"person_id": 1, "person_name": "One", "used_count": 3, "centroid_embedding": [1.0, 0.0], "medoid": {}},
            {"person_id": 2, "person_name": "Two", "used_count": 3, "centroid_embedding": [0.0, 1.0], "medoid": {}},
        ],
    }
    service._write_findings(
        service.FINDING_ASSIGNMENTS,
        service.ACTION_ASSIGNMENT,
        options,
        [{
            "suggestion_id": "assign-22",
            "current_person_id": 2,
            "current_face_id": 22,
            "image_id": 222,
            "selection_state": "selected",
            "write_state": "written",
        }],
        user_key="u",
    )
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: "/volume1/photo")
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [
        {"id": 1, "name": "One"},
        {"id": 2, "name": "Two"},
        {"id": 3, "name": "Three"},
    ])
    service._prepared_embedder = lambda _options: SimpleNamespace()
    scanned_person_ids = []

    def references(**kwargs):
        scanned_person_ids.append(int(kwargs["person"]["id"]))
        return []

    service._person_references = references

    service._build_assignment_suggestions(user_key="u", cookies={}, base_url="https://dsm", options=options)

    assert scanned_person_ids == [2, 3]


def test_person_reference_resume_skips_images_through_previous_review_image(tmp_path):
    service, _findings = _service()
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda *_args, **_kwargs: None
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [
        {"id": 10, "folder_id": 20, "filename": "image-1.jpg"},
        {"id": 11, "folder_id": 20, "filename": "image-2.jpg"},
        {"id": 12, "folder_id": 20, "filename": "image-3.jpg"},
    ]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda id_item, **_kwargs: [{
        "person_id": 1,
        "face_id": id_item + 100,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    paths = {}
    for name in ("image-1.jpg", "image-2.jpg", "image-3.jpg"):
        path = tmp_path / name
        path.write_bytes(b"jpeg")
        paths[name] = str(path)
    resolved_filenames = []
    service._item_path = lambda item, **_kwargs: resolved_filenames.append(item["filename"]) or paths[item["filename"]]
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
        progress_context={"action": service.ACTION_ASSIGNMENT, "resume_after_image_id": 11},
    )

    assert resolved_filenames == ["image-3.jpg"]
    assert [reference["image_id"] for reference in references] == [12]


def test_person_reference_scan_stops_when_cleanup_stop_requested(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    logs = []
    stop_checks = {"count": 0}
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._shouldStopCleanup = lambda _user_key, _action: stop_checks.__setitem__("count", stop_checks["count"] + 1) or stop_checks["count"] > 1
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.jpg"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
        progress_context={"action": service.ACTION_ASSIGNMENT},
    )

    assert references == []
    assert any(event == "recognition_person_reference_face_loop_stop_requested" for event, _fields in logs)


def test_assignment_scan_finishes_stopped_when_cleanup_stop_requested():
    service, findings = _service()
    progress_updates = []
    options = service.normalize_options({"operation_mode": "immediate"})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [{
            "person_id": 1,
            "person_name": "One",
            "used_count": 3,
            "centroid_embedding": [1.0, 0.0],
            "medoid": {},
        }],
    }
    stop_requested = {"value": False}
    service.backend._shouldStopCleanup = lambda _user_key, _action: stop_requested["value"]
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: "/volume1/photo")
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [{"id": 1, "name": "One"}])
    service._prepared_embedder = lambda _options: SimpleNamespace()

    def references(**_kwargs):
        stop_requested["value"] = True
        return []

    service._person_references = references

    service._build_assignment_suggestions(user_key="u", cookies={}, base_url="https://dsm", options=options)

    assert progress_updates[-1][1]["phase"] == "stopped"
    assert progress_updates[-1][1]["stop_requested"] is True
    assert progress_updates[-1][1]["status"]["phase"] == "stopped"


def test_excluding_outlier_updates_persisted_profile_immediately():
    service, findings = _service()
    options = service.normalize_options({})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [{
            "person_id": 22,
            "references": [
                {"face_id": 1, "image_id": 10, "image_path": "/a.jpg", "bbox": {}, "embedding": [1.0, 0.0]},
                {"face_id": 2, "image_id": 11, "image_path": "/b.jpg", "bbox": {}, "embedding": [0.0, 1.0]},
            ],
        }]
    }
    findings.values[service.FINDING_OUTLIERS] = {
        "options": options,
        "entries": [{"outlier_id": "out-1", "face_id": 1, "selection_state": "review", "review_state": "suspected", "write_state": "internal_only"}],
    }

    service.update_review(action=service.ACTION_OUTLIERS, item_id="out-1", decision="excluded")

    profile = findings.values[(service.PROFILE_STATE_TYPE, state_key)]["profiles"][0]
    assert [entry["face_id"] for entry in profile["references"]] == [2]
    assert profile["used_count"] == 1


def test_unreadable_image_uses_embedded_preview_instead_of_failing_run(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    logs = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: b"jpeg")
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.heic"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: (_ for _ in ()).throw(ValueError("image could not be read")),
        detect_and_embed_bytes=lambda _bytes: [],
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
    )

    assert references == []
    assert "recognition_image_preview_fallback" in [event for event, _fields in logs]


def test_unreadable_image_uses_exiftool_preview_when_native_preview_is_missing(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    logs = []
    embedded_bytes = b"\xff\xd8preview\xff\xd9"
    decoded = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend.exiftool_handler = SimpleNamespace(
        isEnabled=lambda: True,
        isAvailable=lambda: True,
        extractEmbeddedJpegPreview=lambda _path: embedded_bytes,
    )
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.heic"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: (_ for _ in ()).throw(ValueError("image could not be read")),
        detect_and_embed_bytes=lambda image_bytes: decoded.append(image_bytes) or [],
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
    )

    assert references == []
    assert decoded == [embedded_bytes]
    fallback_logs = [fields for event, fields in logs if event == "recognition_image_preview_fallback"]
    assert fallback_logs[0]["source"] == "exiftool"


def test_image_decoder_fallback_precedes_exiftool_preview(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.heic"
    image_path.write_bytes(b"heic")
    decoded_bytes = b"\xff\xd8full"
    decoded = []
    service.backend.files = SimpleNamespace(
        extractEmbeddedJpegPreview=lambda _path: (_ for _ in ()).throw(AssertionError("exiftool preview should not be needed"))
    )
    service.backend.image_decoder = SimpleNamespace(
        decode_to_jpeg=lambda _path: SimpleNamespace(success=True, image_bytes=decoded_bytes, source="pillow-heif")
    )
    service.backend._debugLog = lambda *_args, **_kwargs: None
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.heic"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: (_ for _ in ()).throw(ValueError("image could not be read")),
        detect_and_embed_bytes=lambda image_bytes: decoded.append(image_bytes) or [],
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
    )

    assert references == []
    assert decoded == [decoded_bytes]


def test_reference_image_cv2_failure_is_skipped_without_failing_run(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpg")
    logs = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.jpg"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: (_ for _ in ()).throw(RuntimeError("OpenCV out of memory")),
        detect_and_embed_bytes=lambda _bytes: [],
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
    )

    skipped = [fields for event, fields in logs if event == "recognition_image_skipped"]
    assert references == []
    assert skipped
    assert skipped[0]["direct_error"] == "RuntimeError: OpenCV out of memory"


def test_person_reference_scan_reports_image_counter_progress_without_current_file(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    progress_updates = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda *_args, **_kwargs: None
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.jpg"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
        progress_context={
            "action": service.ACTION_BUILD,
            "phase": "reading_reference_images",
            "persons_scanned": 0,
            "persons_total": 1,
        },
    )

    assert len(references) == 1
    assert progress_updates
    _user_key, update = progress_updates[-1]
    assert update["images_scanned"] == 1
    assert update["images_total"] == 1
    assert update["faces_scanned"] == 1
    assert "current_path" not in update
    assert "current_name" not in update
    assert update["status"]["progress"]["kind"] == "images"
    counter_values = {counter["key"]: counter["value"] for counter in update["status"]["counters"]}
    assert counter_values["images"] == 1
    assert "faces" not in counter_values
    assert counter_values["references"] == 1


def test_person_reference_scan_logs_loaded_items_and_summary(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    logs = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [
        {"id": 10, "folder_id": 20, "filename": "image.jpg"},
        {"id": "bad", "folder_id": 20, "filename": "bad.jpg"},
    ]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
    )

    assert len(references) == 1
    event_names = [event for event, _fields in logs]
    assert "recognition_person_reference_items_loaded" in event_names
    assert "recognition_reference_item_skipped" in event_names
    finished = [fields for event, fields in logs if event == "recognition_person_reference_scan_finished"][0]
    assert finished["person_id"] == 1
    assert finished["items_total"] == 2
    assert finished["invalid_items"] == 1
    assert finished["faces_scanned"] == 1
    assert finished["references_count"] == 1


def test_profile_reference_scan_stops_after_reference_limit(tmp_path):
    service, _findings = _service()
    logs = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda _user_key, **updates: updates
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [
        {"id": 10, "folder_id": 20, "filename": "image-1.jpg"},
        {"id": 11, "folder_id": 20, "filename": "image-2.jpg"},
        {"id": 12, "folder_id": 20, "filename": "image-3.jpg"},
    ]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda id_item, **_kwargs: [{
        "person_id": 1,
        "face_id": id_item + 100,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    paths = {}
    for name in ("image-1.jpg", "image-2.jpg", "image-3.jpg"):
        path = tmp_path / name
        path.write_bytes(b"jpeg")
        paths[name] = str(path)
    service._item_path = lambda item, **_kwargs: paths[item["filename"]]
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder,
        options=service.normalize_options({"max_profile_reference_faces_per_person": 2}), folder_cache={},
        progress_context={"action": service.ACTION_BUILD},
    )

    assert [reference["face_id"] for reference in references] == [110, 111]
    limit = [fields for event, fields in logs if event == "recognition_person_reference_limit_reached"][0]
    assert limit["reference_limit"] == 2
    finished = [fields for event, fields in logs if event == "recognition_person_reference_scan_finished"][0]
    assert finished["reference_limit_reached"] is True
    assert finished["references_count"] == 2


def test_person_reference_scan_can_report_person_progress_for_profile_build(tmp_path):
    service, _findings = _service()
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"jpeg")
    progress_updates = []
    service.backend.files = SimpleNamespace(extractEmbeddedJpegPreview=lambda _path: None)
    service.backend._debugLog = lambda *_args, **_kwargs: None
    service.backend._listAllPhotoItemsForPerson = lambda **_kwargs: [{"id": 10, "folder_id": 20, "filename": "image.jpg"}]
    service.backend.photos = SimpleNamespace(list_faceFotoTeamItems=lambda **_kwargs: [{
        "person_id": 1,
        "face_id": 99,
        "bbox": {"top_left": {"x": 0.1, "y": 0.1}, "bottom_right": {"x": 0.2, "y": 0.2}},
    }])
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service._item_path = lambda **_kwargs: str(image_path)
    embedder = SimpleNamespace(
        detect_and_embed=lambda _path: [{"bbox": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}, "embedding": [1.0, 0.0]}],
        _iou=lambda _left, _right: 1.0,
    )

    references = service._person_references(
        user_key="u", cookies={}, base_url="https://dsm", shared_folder=str(tmp_path),
        person={"id": 1, "name": "Ada"}, embedder=embedder, options=service.normalize_options({}), folder_cache={},
        progress_context={
            "action": service.ACTION_BUILD,
            "phase": "reading_reference_images",
            "progress_kind": "persons",
            "persons_scanned": 2,
            "persons_total": 5,
            "current_name": "Ada",
        },
    )

    assert len(references) == 1
    _user_key, update = progress_updates[-1]
    assert update["status"]["progress"]["kind"] == "persons"
    assert update["status"]["progress"]["current"] == 2
    assert update["status"]["progress"]["total"] == 5
    assert update["current_name"] == "Ada"
    counter_values = {counter["key"]: counter["value"] for counter in update["status"]["counters"]}
    assert counter_values["references"] == 1
    assert "faces" not in counter_values


def test_profile_build_person_progress_uses_scanned_primary_label():
    service, _findings = _service()
    progress_updates = []
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates

    service._set_progress(
        "u",
        service.ACTION_BUILD,
        service.normalize_options({}),
        running=True,
        finished=False,
        phase="building_profiles",
        persons_scanned=2,
        persons_total=5,
    )

    _user_key, update = progress_updates[-1]
    assert update["status"]["progress"]["primary_label_key"] == "cleanup:label_scanned"
    assert update["status"]["progress"]["fallback_primary_label"] == "geprüft"


def test_recognition_start_clears_stale_stop_request(monkeypatch):
    service, _findings = _service()
    progress_updates = []
    started_threads = []
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend.getCleanupProgress = lambda _user_key, _action: progress_updates[-1][1] if progress_updates else {}
    service.backend._cleanupStateKey = lambda user_key, action: f"{user_key}_{action}"
    service.backend.runtime_state = SimpleNamespace(values=lambda _name: {})

    class _Thread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started_threads.append(self.kwargs)

    monkeypatch.setattr(face_recognition_module, "Thread", _Thread)

    progress = service.start(
        user_key="u",
        cookies={},
        base_url="https://dsm",
        action=service.ACTION_BUILD,
        options={},
    )

    assert started_threads
    assert progress_updates[0][1]["stop_requested"] is False
    assert progress["stop_requested"] is False


def test_recognition_worker_failure_is_logged():
    service, _findings = _service()
    logs = []
    progress_updates = []
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    cleanup_threads = {"u_recognition_build_profiles": object()}
    service.backend._cleanupStateKey = lambda user_key, action: f"{user_key}_{action}"
    service.backend.runtime_state = SimpleNamespace(values=lambda name: cleanup_threads if name == "cleanup_threads" else {})
    service._set_progress = lambda user_key, action, options, **updates: progress_updates.append((user_key, action, updates))
    service._build_profiles = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))

    service._run(user_key="u", cookies={}, base_url="https://dsm", action=service.ACTION_BUILD, options=service.normalize_options({}))

    assert logs[0][0] == "recognition_worker_failed"
    assert logs[0][1]["action"] == service.ACTION_BUILD
    assert logs[0][1]["error_type"] == "RuntimeError"
    assert logs[-1][0] == "recognition_worker_finished"
    assert logs[-1][1]["failed"] is True
    assert cleanup_threads == {}
    assert progress_updates[-1][2]["phase"] == "failed"


def test_recognition_worker_success_logs_finished_and_cleans_thread():
    service, _findings = _service()
    logs = []
    cleanup_threads = {"u_recognition_build_profiles": object()}
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._cleanupStateKey = lambda user_key, action: f"{user_key}_{action}"
    service.backend.runtime_state = SimpleNamespace(values=lambda name: cleanup_threads if name == "cleanup_threads" else {})
    service._build_profiles = lambda **_kwargs: None

    service._run(user_key="u", cookies={}, base_url="https://dsm", action=service.ACTION_BUILD, options=service.normalize_options({}))

    assert logs[-1][0] == "recognition_worker_finished"
    assert logs[-1][1]["action"] == service.ACTION_BUILD
    assert logs[-1][1]["failed"] is False
    assert cleanup_threads == {}


def test_profile_build_logs_stage_coverage_and_person_result(tmp_path):
    service, _findings = _service()
    logs = []
    progress_updates = []
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend._shouldStopCleanup = lambda user_key, action: False
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: str(tmp_path))
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [{"id": 1, "name": "Ada"}])
    service._prepared_embedder = lambda _options: object()
    service._person_references = lambda **_kwargs: [{
        "face_id": 10,
        "image_id": 20,
        "image_path": str(tmp_path / "ada.jpg"),
        "bbox": {"left": 1, "top": 2, "width": 3, "height": 4},
        "embedding": [1.0, 0.0],
        "iou": 1.0,
    }]

    service._build_profiles(user_key="u", cookies={}, base_url="https://dsm", options=service.normalize_options({"min_faces_per_person": 2}))

    event_names = [event for event, _fields in logs]
    for expected in (
        "recognition_profiles_build_start",
        "recognition_profiles_shared_folder_resolved",
        "recognition_profiles_persons_loaded",
        "recognition_profiles_outlier_exclusions_loaded",
        "recognition_profile_insufficient_references",
        "recognition_profile_person_finished",
        "recognition_profiles_persisted",
    ):
        assert expected in event_names
    person_finished = [fields for event, fields in logs if event == "recognition_profile_person_finished"][0]
    assert person_finished["person_id"] == 1
    assert person_finished["reference_count"] == 1
    assert person_finished["profile_created"] is True
    assert person_finished["quality"] == "limited"
    assert progress_updates[-1][1]["phase"] == "finished"


def test_profile_build_logs_persisted_counts(tmp_path):
    service, _findings = _service()
    logs = []
    progress_updates = []
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend._shouldStopCleanup = lambda user_key, action: False
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: str(tmp_path))
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [{"id": 1, "name": "Ada"}])
    service._prepared_embedder = lambda _options: object()
    service._person_references = lambda **_kwargs: [{
        "face_id": 10,
        "image_id": 20,
        "image_path": str(tmp_path / "ada.jpg"),
        "bbox": {"left": 1, "top": 2, "width": 3, "height": 4},
        "embedding": [1.0, 0.0],
        "iou": 1.0,
    }]

    service._build_profiles(user_key="u", cookies={}, base_url="https://dsm", options=service.normalize_options({"min_faces_per_person": 2}))

    persisted = [entry for entry in logs if entry[0] == "recognition_profiles_persisted"]
    assert persisted
    checkpoints = [entry for entry in logs if entry[0] == "recognition_profiles_checkpoint_persisted"]
    assert checkpoints
    fields = persisted[0][1]
    assert fields["persons_total"] == 1
    assert fields["persons_scanned"] == 1
    assert fields["profiles_built"] == 1
    assert fields["quality_count"] == 1
    assert fields["state_written"] is True
    assert progress_updates[-1][1]["phase"] == "finished"


def test_profile_build_without_rebuild_all_skips_existing_profiles(tmp_path):
    service, findings = _service()
    logs = []
    progress_updates = []
    options = service.normalize_options({"min_faces_per_person": 2, "rebuild_all": False})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [{
            "person_id": 1,
            "person_name": "Existing",
            "profile_key": service._model_key(options),
            "reference_count": 3,
            "used_count": 3,
            "quality": "good",
            "centroid_embedding": [1.0, 0.0],
            "medoid": {},
            "references": [],
        }],
    }
    findings.values[service.FINDING_QUALITY] = {
        "entries": [{"person_id": 1, "person_name": "Existing", "quality": "good"}],
    }
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend._shouldStopCleanup = lambda user_key, action: False
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: str(tmp_path))
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [
        {"id": 1, "name": "Existing"},
        {"id": 2, "name": "New"},
    ])
    service._prepared_embedder = lambda _options: object()
    scanned_person_ids = []

    def references(**kwargs):
        scanned_person_ids.append(int(kwargs["person"]["id"]))
        return [{
            "face_id": 20,
            "image_id": 30,
            "image_path": str(tmp_path / "new.jpg"),
            "bbox": {"left": 1, "top": 2, "width": 3, "height": 4},
            "embedding": [0.0, 1.0],
            "iou": 1.0,
        }]

    service._person_references = references

    service._build_profiles(user_key="u", cookies={}, base_url="https://dsm", options=options)

    loaded = [fields for event, fields in logs if event == "recognition_profiles_persons_loaded"][0]
    persisted = [fields for event, fields in logs if event == "recognition_profiles_persisted"][0]
    profiles = findings.values[(service.PROFILE_STATE_TYPE, state_key)]["profiles"]
    assert scanned_person_ids == [2]
    assert loaded["persons_all_total"] == 2
    assert loaded["persons_total"] == 1
    assert loaded["existing_profiles_count"] == 1
    assert loaded["skipped_existing_profiles_count"] == 1
    assert loaded["rebuild_all"] is False
    assert persisted["persons_total"] == 1
    assert persisted["profiles_built"] == 2
    assert [profile["person_id"] for profile in profiles] == [1, 2]
    persons_loaded = [updates for _user_key, updates in progress_updates if updates.get("phase") == "persons_loaded"][0]
    assert persons_loaded["persons_total"] == 1


def test_profile_build_logs_empty_profiles_when_no_references(tmp_path):
    service, _findings = _service()
    logs = []
    progress_updates = []
    service.backend._debugLog = lambda event, **fields: logs.append((event, fields))
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend._shouldStopCleanup = lambda user_key, action: False
    service.backend.core = SimpleNamespace(getSharedFolder=lambda **_kwargs: str(tmp_path))
    service.backend.photos = SimpleNamespace(listFotoTeamPersonKnown=lambda **_kwargs: [{"id": 1, "name": "Ada"}])
    service._prepared_embedder = lambda _options: object()
    service._person_references = lambda **_kwargs: []

    service._build_profiles(user_key="u", cookies={}, base_url="https://dsm", options=service.normalize_options({}))

    empty = [fields for event, fields in logs if event == "recognition_profiles_empty"][0]
    assert empty["persons_total"] == 1
    assert empty["quality_count"] == 1
    assert empty["stopped"] is False
    assert progress_updates[-1][1]["profiles_built"] == 0


def test_unknown_face_recognition_without_profiles_reports_actionable_status():
    service, _findings = _service()
    progress_updates = []
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates

    service._build_suggestions(
        user_key="u",
        cookies={},
        base_url="https://dsm",
        options=service.normalize_options({"operation_mode": "immediate"}),
    )

    assert progress_updates
    _user_key, update = progress_updates[-1]
    assert update["running"] is False
    assert update["finished"] is True
    assert update["phase"] == "needs_profiles"
    assert update["message_key"] == "cleanup:recognition_profiles_missing"


def test_recognition_status_schema_uses_integrated_modes_for_operation_modes():
    service, findings = _service()
    progress_updates = []
    service.backend._buildStatusProgress = lambda **kwargs: kwargs
    service.backend._buildStatusCounter = lambda key, **kwargs: {"key": key, **kwargs}
    service.backend._buildStatusPayload = lambda **kwargs: kwargs
    service.backend._setCleanupProgress = lambda user_key, **updates: progress_updates.append((user_key, updates)) or updates
    service.backend.getCleanupProgress = lambda _user_key, _action: progress_updates[-1][1] if progress_updates else {}
    service._write_findings(
        service.FINDING_SUGGESTIONS,
        service.ACTION_SUGGEST,
        service.normalize_options({"operation_mode": "immediate"}),
        [{"suggestion_id": "rec-1", "selection_state": "review", "write_state": "pending"}],
        user_key="u",
    )
    findings.values[service.FINDING_SUGGESTIONS] = {
        "options": service.normalize_options({"operation_mode": "findings"}),
        "entries": [{"suggestion_id": "rec-2", "selection_state": "review", "write_state": "pending"}],
    }

    service.sync_review_progress(user_key="u", action=service.ACTION_SUGGEST, operation_mode="immediate")
    assert progress_updates[-1][1]["status"]["mode"] == "scan"

    service.sync_review_progress(user_key="u", action=service.ACTION_SUGGEST, operation_mode="findings")
    assert progress_updates[-1][1]["status"]["mode"] == "findings"
