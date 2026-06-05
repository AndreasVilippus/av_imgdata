import json
from unittest.mock import Mock, patch

from api.session_manager import SessionBootstrapRequired, SessionManager, SessionManagerError
from imgdata import ImgDataOperationError, ImgDataService, ScanContext
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload


def make_service():
    return ImgDataService(SessionManager())


def test_write_operation_lock_keeps_structured_conflict_details():
    service = make_service()

    with service._writeOperationLock(
        service._metadataWriteLockKey("/volume1/photo/a.jpg"),
        phase="metadata_write",
        context={"image_path": "/volume1/photo/a.jpg"},
    ):
        try:
            with service._writeOperationLock(
                service._metadataWriteLockKey("/volume1/photo/a.jpg"),
                phase="metadata_write",
                context={"image_path": "/volume1/photo/a.jpg"},
            ):
                pass
        except ImgDataOperationError as exc:
            details = exc.details
        else:
            raise AssertionError("expected write conflict")

    assert details["code"] == "write_conflict"
    assert details["message_key"] == "write_conflict"
    assert details["phase"] == "metadata_write"
    assert details["lock_key"] == "metadata:/volume1/photo/a.jpg"
    assert details["retryable"] is True
    assert details["image_path"] == "/volume1/photo/a.jpg"


def test_photo_face_write_lock_conflict_includes_affected_face_identity():
    service = make_service()

    with service._writeOperationLock(
        service._photosFaceWriteLockKey(77),
        phase="photos_face_assign",
        context={"face_id": 77, "item_id": 42},
    ):
        try:
            with service._writeOperationLock(
                service._photosFaceWriteLockKey(77),
                phase="photos_person_create_from_face",
                context={"face_id": 77, "item_id": 42},
            ):
                pass
        except ImgDataOperationError as exc:
            details = exc.details
        else:
            raise AssertionError("expected write conflict")

    assert details["code"] == "write_conflict"
    assert details["phase"] == "photos_person_create_from_face"
    assert details["lock_key"] == "photos:face:77"
    assert details["retryable"] is True
    assert details["face_id"] == 77
    assert details["item_id"] == 42


def test_photo_item_write_lock_conflict_includes_affected_item_identity():
    service = make_service()

    with service._writeOperationLock(
        service._photosItemWriteLockKey(42),
        phase="photos_face_create_from_metadata",
        context={"item_id": 42, "image_path": "/volume1/photo/a.jpg"},
    ):
        try:
            with service._writeOperationLock(
                service._photosItemWriteLockKey(42),
                phase="photos_face_create_from_metadata",
                context={"item_id": 42, "image_path": "/volume1/photo/a.jpg"},
            ):
                pass
        except ImgDataOperationError as exc:
            details = exc.details
        else:
            raise AssertionError("expected write conflict")

    assert details["code"] == "write_conflict"
    assert details["phase"] == "photos_face_create_from_metadata"
    assert details["lock_key"] == "photos:item:42"
    assert details["retryable"] is True
    assert details["item_id"] == 42
    assert details["image_path"] == "/volume1/photo/a.jpg"


def test_unrelated_metadata_face_and_photo_item_writes_do_not_block_each_other():
    service = make_service()

    with service._writeOperationLock(service._metadataWriteLockKey("/a.jpg"), phase="metadata_write"):
        with service._writeOperationLock(service._photosFaceWriteLockKey(77), phase="photos_face_assign"):
            with service._writeOperationLock(service._photosItemWriteLockKey(42), phase="photos_face_create"):
                pass


def test_checks_findings_status_uses_lightweight_status_reader():
    service = make_service()
    statuses = {
        "dimension_issues": {"status": "finished", "count": 946, "save_only": False},
        "duplicate_faces": {"status": "finished", "count": 67, "save_only": False},
        "position_deviations": {"status": "finished", "count": 488, "save_only": True},
        "name_conflicts": {"status": "finished", "count": 1, "save_only": True},
    }
    service.file_analysis.readCheckFindingsStatus = Mock(side_effect=lambda check_type: statuses[check_type])
    service.file_analysis.readCheckFindings = Mock(side_effect=AssertionError("status read must not load entries"))

    payload = service.getChecksFindingsStatus()

    assert payload == {"statuses": statuses}
    assert service.file_analysis.readCheckFindingsStatus.call_count == 4
    service.file_analysis.readCheckFindings.assert_not_called()


def test_file_analysis_progress_enrichment_uses_lightweight_findings_status_reader():
    service = make_service()
    service.runtime_state.get_value = Mock(return_value=None)
    service.runtime_state.read_persisted = Mock(return_value={})
    service.file_analysis.readLatestResult = Mock(return_value={
        "job_id": "job-1",
        "files_analyzed": 10,
        "files_matched_total": 10,
    })
    service.file_analysis.readCheckFindingsStatus = Mock(side_effect=lambda finding_type: {
        "job_id": "job-1",
        "count": 7 if finding_type == "duplicate_faces" else 0,
    })
    service.file_analysis.readCheckFindings = Mock(side_effect=AssertionError("progress status must not load finding entries"))

    progress = service.getFileAnalysisProgress()

    assert progress["files_with_duplicate_faces"] == 7
    assert service.file_analysis.readCheckFindingsStatus.call_count == 4
    service.file_analysis.readCheckFindings.assert_not_called()


def test_photo_face_match_assignment_mutation_updates_photos_findings_and_mapping():
    service = make_service()
    calls = []
    service.assignMatchedFaceToKnownPerson = lambda **kwargs: calls.append(("assign", kwargs)) or {"updated": True}
    service.removeFaceMatchFindingEntry = lambda **kwargs: calls.append(("remove", kwargs)) or {"count": 4, "transferred_count": 2}
    service.saveNameMapping = lambda **kwargs: calls.append(("mapping", kwargs)) or True

    result = service.applyPhotoFaceMatchAssignment(
        user_key="user",
        cookies={"_SSID": "sid"},
        base_url="https://example.test",
        face_id=77,
        person_id=91,
        person_name=" Target ",
        save_mapping=True,
        source_name="Legacy",
    )

    assert result == {
        "face_id": 77,
        "person_id": 91,
        "result": {"updated": True},
        "findings_update": {"count": 4, "transferred_count": 2},
        "mapping_saved": True,
    }
    assert calls == [
        ("assign", {
            "user_key": "user",
            "cookies": {"_SSID": "sid"},
            "base_url": "https://example.test",
            "face_id": 77,
            "person_id": 91,
            "person_name": "Target",
        }),
        ("remove", {"face_id": 77, "increment_transferred_count": True}),
        ("mapping", {"source_name": "Legacy", "target_name": "Target"}),
    ]


def test_remove_face_match_finding_entry_compacts_persisted_payload():
    service = make_service()
    written = {}
    service._debugLog = lambda *args, **kwargs: None
    service.getFaceMatchFindings = lambda: {
        "status": "finished",
        "action": "search_photo_face_in_file",
        "save_only": True,
        "transferred_count": 3,
        "entries": [
            {
                "face": {"face_id": 77},
                "lookup_debug": {"large": list(range(100))},
            },
            {
                "face": {"face_id": 88},
                "lookup_debug": {"large": list(range(100))},
                "resume_cursor": {"skip_face_ids": [77]},
                "matched_person": {
                    "id": 5,
                    "name": "Target",
                    "additional": {
                        "thumbnail": {
                            "cache_key": "thumb",
                            "large": "drop",
                        },
                        "raw": "drop",
                    },
                    "raw_payload": "drop",
                },
            },
        ],
    }
    service.file_analysis.writeCheckFindings = lambda finding_type, payload: written.update({
        "finding_type": finding_type,
        "payload": payload,
    }) or True

    result = service.removeFaceMatchFindingEntry(face_id=77)

    assert result["removed"] is True
    assert result["remaining_count"] == 1
    assert written["finding_type"] == "face_match"
    entry = written["payload"]["entries"][0]
    assert "lookup_debug" not in entry
    assert "resume_cursor" not in entry
    assert entry["matched_person"] == {
        "id": 5,
        "name": "Target",
        "additional": {
            "thumbnail": {
                "cache_key": "thumb",
            },
        },
    }


def test_photo_face_match_person_creation_mutation_updates_findings_and_mapping():
    service = make_service()
    calls = []
    create_result = {
        "operation": "photos_create",
        "target_person": {"id": 91, "name": "Target"},
    }
    service.resolveOrCreatePhotosPersonForExistingFace = lambda **kwargs: calls.append(("create", kwargs)) or create_result
    service.removeFaceMatchFindingEntry = lambda **kwargs: calls.append(("remove", kwargs)) or {"count": 4, "transferred_count": 2}
    service.saveNameMapping = lambda **kwargs: calls.append(("mapping", kwargs)) or True

    result = service.applyPhotoFaceMatchPersonCreation(
        user_key="user",
        cookies={"_SSID": "sid"},
        base_url="https://example.test",
        face_id=77,
        person_name=" Target ",
        save_mapping=True,
        source_name="Legacy",
    )

    assert result == {
        "face_id": 77,
        "person_id": 91,
        "person_name": "Target",
        "result": create_result,
        "findings_update": {"count": 4, "transferred_count": 2},
        "mapping_saved": True,
    }
    assert calls == [
        ("create", {
            "user_key": "user",
            "cookies": {"_SSID": "sid"},
            "base_url": "https://example.test",
            "image_path": "",
            "face_id": 77,
            "person_name": "Target",
            "create_missing_person": True,
        }),
        ("remove", {"face_id": 77, "increment_transferred_count": True}),
        ("mapping", {"source_name": "Legacy", "target_name": "Target"}),
    ]


def test_raw_face_check_without_sidecar_is_skipped_when_exiftool_context_is_disabled():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: None

    assert service._shouldSkipRawFaceCheckWithoutSidecar(
        "/volume1/photo/raw/DSC01889.ARW",
        "name_conflicts",
        scan_context,
    ) is True


def test_raw_face_check_with_sidecar_is_not_skipped():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: "/volume1/photo/raw/DSC01889.xmp"

    assert service._shouldSkipRawFaceCheckWithoutSidecar(
        "/volume1/photo/raw/DSC01889.ARW",
        "name_conflicts",
        scan_context,
    ) is False


def test_raw_dimension_issue_check_still_reads_raw_without_sidecar():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: None

    assert service._shouldSkipRawFaceCheckWithoutSidecar(
        "/volume1/photo/raw/DSC01889.ARW",
        "dimension_issues",
        scan_context,
    ) is False


def test_jpeg_face_check_without_sidecar_is_probed_for_embedded_xmp():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: None

    with patch("imgdata.os.path.isfile", return_value=True):
        assert service._shouldProbeJpegFaceCheckWithoutSidecar(
            "/volume1/photo/tests/0206671986005.jpg",
            "name_conflicts",
            scan_context,
        ) is True


def test_jpeg_face_check_with_sidecar_is_not_probed_for_skip():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: "/volume1/photo/tests/0206671986005.xmp"

    assert service._shouldProbeJpegFaceCheckWithoutSidecar(
        "/volume1/photo/tests/0206671986005.jpg",
        "name_conflicts",
        scan_context,
    ) is False


def test_jpeg_dimension_issue_check_is_not_probed_for_face_skip():
    service = make_service()
    scan_context = ScanContext({"files": {"PREFER_EXIFTOOL_FOR_CONTEXT": False}})
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: None

    assert service._shouldProbeJpegFaceCheckWithoutSidecar(
        "/volume1/photo/tests/0206671986005.jpg",
        "dimension_issues",
        scan_context,
    ) is False


def test_checks_face_scan_keeps_exiftool_fallbacks_enabled_for_metadata_read():
    service = make_service()
    captured = {}

    service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
    service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: "/volume1/photo/tests/test.xmp"
    service.files.analyzeMetadata = lambda payload: {}
    service._buildCheckEntriesForType = lambda **kwargs: []

    def read_metadata(image_path, **kwargs):
        captured.update(kwargs)
        return MetadataPayload(image_path=image_path)

    service._readImageMetadata = read_metadata

    service.searchNextChecksItem(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        check_type="name_conflicts",
        save_only=False,
    )

    assert captured.get("allow_exiftool_context_fallback", True) is True
    assert captured.get("allow_exiftool_sidecar_read", True) is True


def test_checks_candidate_paths_changed_since_days_uses_image_and_sidecar_mtime():
    service = make_service()
    paths = [
        "/volume1/photo/a.jpg",
        "/volume1/photo/b.jpg",
        "/volume1/photo/c.jpg",
    ]
    sidecars = {
        "/volume1/photo/b.jpg": "/volume1/photo/b.xmp",
        "/volume1/photo/c.jpg": "/volume1/photo/c.xmp",
    }
    service.files.listImageFiles = lambda shared_folder: paths
    service.files.findXmpForImage = lambda image_path, lookup_cache=None: sidecars.get(image_path)
    service._fileChangedSince = lambda path, cutoff: path in {
        "/volume1/photo/b.xmp",
        "/volume1/photo/c.jpg",
    }

    assert service._getChecksCandidatePaths(
        user_key="user",
        check_type="name_conflicts",
        shared_folder="/volume1/photo",
        changed_since_days=7,
        use_cache=False,
    ) == ["/volume1/photo/b.jpg", "/volume1/photo/c.jpg"]


def test_checks_candidate_paths_changed_since_days_zero_keeps_all_paths():
    service = make_service()
    paths = ["/volume1/photo/a.jpg", "/volume1/photo/b.jpg"]
    service.files.listImageFiles = lambda shared_folder: paths

    assert service._getChecksCandidatePaths(
        user_key="user",
        check_type="name_conflicts",
        shared_folder="/volume1/photo",
        changed_since_days=0,
        use_cache=False,
    ) == paths


def test_checks_candidate_paths_cache_is_owned_and_invalidated_by_workflow_service():
    service = make_service()
    listed_paths = [["/volume1/photo/a.jpg"], ["/volume1/photo/b.jpg"]]
    service.files.listImageFiles = lambda shared_folder: listed_paths.pop(0)

    assert service._getChecksCandidatePaths(
        user_key="user",
        check_type="name_conflicts",
        shared_folder="/volume1/photo",
    ) == ["/volume1/photo/a.jpg"]
    assert service._getChecksCandidatePaths(
        user_key="user",
        check_type="name_conflicts",
        shared_folder="/volume1/photo",
    ) == ["/volume1/photo/a.jpg"]

    service._invalidateChecksCandidatePathsCache("user", "name_conflicts")

    assert service._getChecksCandidatePaths(
        user_key="user",
        check_type="name_conflicts",
        shared_folder="/volume1/photo",
    ) == ["/volume1/photo/b.jpg"]
    assert listed_paths == []


def test_face_match_candidate_paths_cache_is_owned_by_workflow_service():
    service = make_service()
    listed_paths = [
        ["/volume1/photo/a.jpg"],
        ["/volume1/photo/b.jpg"],
        ["/volume1/other/c.jpg"],
    ]
    requested_folders = []

    def list_image_files(shared_folder):
        requested_folders.append(shared_folder)
        return listed_paths.pop(0)

    service.files.listImageFiles = list_image_files

    assert service._getFaceMatchCandidatePaths(
        user_key="user",
        action="search_missing_faces_insightface",
        shared_folder="/volume1/photo",
    ) == ["/volume1/photo/a.jpg"]
    assert service._getFaceMatchCandidatePaths(
        user_key="user",
        action="search_missing_faces_insightface",
        shared_folder="/volume1/photo",
    ) == ["/volume1/photo/a.jpg"]
    assert service._getFaceMatchCandidatePaths(
        user_key="user",
        action="search_missing_faces_insightface",
        shared_folder="/volume1/photo",
        use_cache=False,
    ) == ["/volume1/photo/b.jpg"]
    assert service._getFaceMatchCandidatePaths(
        user_key="user",
        action="search_missing_faces_insightface",
        shared_folder="/volume1/other",
    ) == ["/volume1/other/c.jpg"]

    assert requested_folders == ["/volume1/photo", "/volume1/photo", "/volume1/other"]
    assert listed_paths == []


def test_face_match_stop_request_is_owned_by_workflow_service():
    service = make_service()
    service._setFaceMatchingProgress(
        "user",
        operation_id="face-match-running",
        running=True,
        finished=False,
        action="search_photo_face_in_file",
    )

    progress = service.requestStopFaceMatching("user")

    assert progress["message_key"] == "face_match:progress_stopping"
    assert progress["stop_requested"] is True
    assert service._shouldStopFaceMatching("user") is True


def test_face_match_findings_flush_decision_is_owned_by_workflow_service():
    service = make_service()

    assert service._shouldFlushFaceMatchFindings(
        entries_count=1,
        last_flush_count=0,
        last_flush_at=0.0,
    ) is True
    assert service._shouldFlushFaceMatchFindings(
        entries_count=1,
        last_flush_count=1,
        last_flush_at=0.0,
    ) is False
    assert service._shouldFlushFaceMatchFindings(
        entries_count=service.FACE_MATCH_FINDINGS_FLUSH_ENTRY_INTERVAL + 1,
        last_flush_count=1,
        last_flush_at=0.0,
    ) is True


def test_checks_workflow_builds_scan_payload_and_advances_name_conflict_resume_state():
    service = make_service()
    payload = service.checks_workflow.build_scan_payload(
        check_type="name_conflicts",
        save_only=False,
        files_scanned=3,
        total_files=10,
        findings_count=4,
        path_index=3,
        pending_entries=[{"image_path": "photo/test.jpg"}],
        current_path="photo/test.jpg",
        result={"entry": {"image_path": "photo/test.jpg"}},
    )

    resume_cursor = service.checks_workflow.trusted_resume_cursor(
        {
            **payload,
            "resolved_count": 2,
            "ignored_count": 1,
        },
        check_type="name_conflicts",
        save_only=False,
        advance_current_result=True,
    )

    assert payload["resume_cursor"]["path_index"] == 3
    assert payload["resume_cursor"]["pending_entries"] == [{"image_path": "photo/test.jpg"}]
    assert resume_cursor["findings_count"] == 4
    assert resume_cursor["resolved_count"] == 2
    assert resume_cursor["ignored_count"] == 2
    assert resume_cursor["metrics_trusted"] is True


def test_search_missing_photos_faces_resumes_from_path_index():
    service = make_service()
    analyzed = []
    paths = [
        "/volume1/photo/tests/first.jpg",
        "/volume1/photo/tests/second.jpg",
        "/volume1/photo/tests/third.jpg",
    ]
    service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
    service.files.listImageFiles = lambda base_path: paths
    service._readImageMetadata = lambda image_path, include_unnamed_acd=False: analyzed.append(image_path) or MetadataPayload(
        image_path=image_path,
        faces=[],
    )
    service.photos.findFotoTeamItemByPath = lambda **kwargs: None

    result = service.searchMissingPhotosFaces(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        resume_cursor={
            "action": "mark_missing_photos_faces",
            "path_index": 2,
            "skip_targets": ["existing-token"],
            "transferred_count": 10,
            "findings_count": 11,
            "auto": True,
            "save_only": False,
        },
    )

    assert analyzed == ["/volume1/photo/tests/third.jpg"]
    assert result["resume_cursor"]["path_index"] == 3
    assert result["transferred_count"] == 10
    assert result["findings_count"] == 11


def test_face_matching_progress_serializes_metadata_face_objects():
    service = make_service()
    persisted = {}
    metadata_face = MetadataFace.from_center_box(
        name="Jelizaveta Vilippus geb. Kromskaja",
        x=0.500164,
        y=0.277917,
        w=0.087058,
        h=0.070207,
        source="embedded_xmp_parsed",
        source_format="ACD",
    )

    def write_runtime_state(name, user_key, payload):
        json.dumps(payload)
        persisted["name"] = name
        persisted["user_key"] = user_key
        persisted["payload"] = payload

    service.file_analysis.writeRuntimeState = write_runtime_state

    service._setFaceMatchingProgress(
        "user",
        result={
            "searched": True,
            "metadata_face": metadata_face,
            "nested": {"faces": [metadata_face]},
        },
    )

    assert persisted["name"] == "face_match_progress"
    assert persisted["payload"]["result"]["metadata_face"] == metadata_face.to_dict()
    assert persisted["payload"]["result"]["nested"]["faces"] == [metadata_face.to_dict()]
    assert service.getFaceMatchingProgress("user")["result"]["metadata_face"] == metadata_face.to_dict()


def test_start_face_matching_discovery_reuses_progress_cursor_when_skipping_target():
    service = make_service()

    class FakeThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self):
            return None

        def is_alive(self):
            return False

    service._setFaceMatchingProgress(
        "user",
        action="mark_missing_photos_faces",
        operation_id="face-match-existing",
        running=False,
        finished=True,
        images_read=1444,
        transferred_count=10,
        findings_count=11,
        resume_cursor={
            "action": "mark_missing_photos_faces",
            "path_index": 1444,
            "skip_targets": ["old-token"],
            "transferred_count": 10,
            "findings_count": 11,
            "auto": True,
            "save_only": False,
        },
    )

    with patch("services.face_match_workflow_service.Thread", FakeThread):
        progress = service.startFaceMatchingDiscovery(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            action="mark_missing_photos_faces",
            skip_targets=["new-token"],
            auto=True,
            save_only=False,
            resume_from_progress=False,
        )

    assert progress["operation_id"] == "face-match-existing"
    assert progress["images_read"] == 1444
    assert progress["transferred_count"] == 10
    assert progress["findings_count"] == 11
    assert progress["resume_cursor"]["path_index"] == 1444
    assert progress["resume_cursor"]["skip_targets"] == ["new-token", "old-token"]


def test_start_face_matching_discovery_preserves_search_photo_progress_when_skipping_face():
    service = make_service()

    class FakeThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self):
            return None

        def is_alive(self):
            return False

    service._setFaceMatchingProgress(
        "user",
        action="search_photo_face_in_file",
        operation_id="face-match-existing",
        running=False,
        finished=True,
        persons_read=42,
        images_read=17,
        faces_read=180,
        target_faces_read=3,
        metadata_faces_read=99,
        transferred_count=5,
        findings_count=6,
        resume_cursor={
            "action": "search_photo_face_in_file",
            "skip_face_ids": [123],
            "transferred_count": 5,
            "findings_count": 6,
            "auto": True,
            "save_only": False,
        },
    )

    with patch("services.face_match_workflow_service.Thread", FakeThread):
        progress = service.startFaceMatchingDiscovery(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            action="search_photo_face_in_file",
            skip_face_ids=[456],
            auto=True,
            save_only=False,
            resume_from_progress=False,
        )

    assert progress["operation_id"] == "face-match-existing"
    assert progress["persons_read"] == 42
    assert progress["images_read"] == 17
    assert progress["faces_read"] == 180
    assert progress["target_faces_read"] == 3
    assert progress["metadata_faces_read"] == 99
    assert progress["transferred_count"] == 5
    assert progress["findings_count"] == 6
    assert progress["resume_cursor"]["skip_face_ids"] == [123, 456]
    assert progress["resume_cursor"]["persons_read"] == 42


def test_run_checks_scan_preserves_latest_progress_on_session_error():
    service = make_service()
    service._setChecksProgress(
        "user",
        check_type="name_conflicts",
        source_mode="scan",
        running=True,
        finished=False,
        stop_requested=False,
        files_scanned=945,
        total_files=40798,
        findings_count=12,
        current_path="/volume1/photo/tests/test.jpg",
        resume_cursor={
            "check_type": "name_conflicts",
            "path_index": 944,
            "pending_entries": [],
            "save_only": False,
            "source_mode": "scan",
            "findings_count": 12,
        },
    )

    detail = {"error": "api_failed", "api": "SYNO.FotoTeam.Browse.Item", "response": {"success": False, "error": {"code": 902}}}
    service.checks_workflow.search_next_item = lambda **kwargs: (_ for _ in ()).throw(SessionManagerError(detail))

    service.checks_workflow._run_scan(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        check_type="name_conflicts",
        save_only=False,
    )

    progress = service.getChecksProgress("user", "name_conflicts")
    assert progress["running"] is False
    assert progress["finished"] is False
    assert progress["error"] == "session manager error"
    assert progress["error_details"] == detail
    assert progress["files_scanned"] == 945
    assert progress["findings_count"] == 12
    assert progress["current_path"] == "/volume1/photo/tests/test.jpg"
    assert progress["resume_cursor"]["path_index"] == 944
    assert progress["resume_cursor"]["findings_count"] == 12


def test_checks_save_only_auto_apply_progress_counts_stored_and_resolved_separately():
    service = make_service()
    image_path = "/volume1/photo/tests/conflict.jpg"
    resolved_entry = {
        "review_type": "name_conflicts",
        "image_path": image_path,
        "entry_id": "resolved",
        "left_face_signature": {"source_format": "ACD", "name": "Old", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
        "right_face_signature": {"source_format": "MWG_REGIONS", "name": "New", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
    }
    remaining_entry = {
        "review_type": "name_conflicts",
        "image_path": image_path,
        "entry_id": "remaining",
        "left_face_signature": {"source_format": "MICROSOFT", "name": "Old", "x": 0.5, "y": 0.2, "w": 0.3, "h": 0.4},
        "right_face_signature": {"source_format": "MWG_REGIONS", "name": "New", "x": 0.5, "y": 0.2, "w": 0.3, "h": 0.4},
    }
    captured_writes = []

    service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
    service._getChecksCandidatePaths = lambda **kwargs: [image_path]
    service._shouldStopChecks = lambda *args, **kwargs: False
    service._shouldSkipRawFaceCheckWithoutSidecar = lambda *args, **kwargs: False
    service._shouldProbeJpegFaceCheckWithoutSidecar = lambda *args, **kwargs: False
    service._readImageMetadata = lambda *args, **kwargs: MetadataPayload(image_path=image_path, faces=[])
    service.files.analyzeMetadata = lambda payload: {}
    service._buildCheckEntriesForType = Mock(return_value=[resolved_entry, remaining_entry])
    service._resolveChecksReviewEntry = Mock(return_value={
        "entry": None,
        "item": None,
        "auto_applied_count": 1,
        "processed_entry_tokens": [service._checksEntryToken(resolved_entry)],
    })
    service.checks_workflow.write_findings = lambda **kwargs: captured_writes.append(kwargs)

    result = service.searchNextChecksItem(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        check_type="name_conflicts",
        save_only=True,
        auto_apply_suggested_names=True,
    )

    assert result["findings_count"] == 1
    assert result["resolved_count"] == 1
    assert captured_writes[-1]["entries"] == [remaining_entry]

    progress = service.getChecksProgress("user", "name_conflicts")
    assert progress["findings_count"] == 1
    assert progress["resolved_count"] == 1
    counters = {counter["key"]: counter for counter in progress["status"]["counters"]}
    assert counters["findings"]["value"] == 1
    assert counters["findings"]["label_key"] == "checks:counter_stored_findings"
    assert counters["resolved"]["value"] == 1
    assert counters["resolved"]["label_key"] == "checks:counter_auto_resolved"


def test_run_face_matching_api_failure_does_not_request_login():
    service = make_service()
    service.session_manager.keepalive = lambda *args, **kwargs: {}
    service._setFaceMatchingProgress(
        "user",
        running=True,
        finished=False,
        paused=False,
        auth_required=False,
        action="mark_missing_photos_faces",
        auto=True,
        save_only=False,
        images_read=6038,
        resume_cursor={
            "action": "mark_missing_photos_faces",
            "path_index": 6038,
            "transferred_count": 0,
            "auto": True,
            "save_only": False,
        },
    )
    detail = {
        "error": "api_failed",
        "api": "SYNO.Foto.Browse.Item",
        "response": {"success": False, "error": {"code": 902}},
    }

    def fail_search(**kwargs):
        raise SessionManagerError(detail)

    service.searchMissingPhotosFaces = fail_search
    service._runFaceMatching(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        action="mark_missing_photos_faces",
        limit=0,
        offset=0,
        skip_face_ids=[],
        skip_targets=[],
        auto=True,
        save_only=False,
    )

    progress = service.getFaceMatchingProgress("user")
    assert progress["message_key"] == "face_match:progress_failed"
    assert progress["running"] is False
    assert progress["finished"] is True
    assert progress["paused"] is False
    assert progress["auth_required"] is False
    assert progress["error"] == "session manager error"
    assert progress["error_details"] == detail
    assert progress["images_read"] == 6038


def test_run_face_matching_publishes_success_result_with_terminal_state_atomically():
    service = make_service()
    updates = []
    result = {
        "searched": True,
        "metadata_face": {"name": "Person Candidate"},
        "findings_count": 1,
        "transferred_count": 0,
    }
    service.session_manager.keepalive = lambda *args, **kwargs: {}
    service.searchPhotoFaceInFile = Mock(return_value=result)
    service._setFaceMatchingProgress = lambda user_key, **kwargs: updates.append((user_key, kwargs))

    service._runFaceMatching(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        action="search_photo_face_in_file",
        limit=0,
        offset=0,
        skip_face_ids=[],
        skip_targets=[],
        auto=False,
        save_only=False,
    )

    assert updates == [("user", {
        "result": result,
        "running": False,
        "finished": True,
        "stop_requested": False,
        "action": "search_photo_face_in_file",
        "auto": False,
        "save_only": False,
        "findings_count": 1,
        "transferred_count": 0,
    })]


def test_run_face_matching_bootstrap_failure_requests_login():
    service = make_service()

    def fail_keepalive(*args, **kwargs):
        raise SessionBootstrapRequired("missing kk_message for resume bootstrap")

    service.session_manager.keepalive = fail_keepalive
    service._runFaceMatching(
        user_key="user",
        cookies={},
        base_url="https://example.test",
        action="mark_missing_photos_faces",
        limit=0,
        offset=0,
        skip_face_ids=[],
        skip_targets=[],
        auto=True,
        save_only=False,
    )

    progress = service.getFaceMatchingProgress("user")
    assert progress["message_key"] == "face_match:progress_auth_required"
    assert progress["running"] is False
    assert progress["finished"] is False
    assert progress["paused"] is True
    assert progress["auth_required"] is True
    assert progress["error"] == "missing kk_message for resume bootstrap"
    assert progress["error_details"] == {}
