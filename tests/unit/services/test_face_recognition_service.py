from types import SimpleNamespace

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
    assert logs[0][0] == "recognition_image_preview_fallback"


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
    assert counter_values["faces"] == 1


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
