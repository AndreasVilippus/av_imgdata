from unittest.mock import patch

from api.session_manager import SessionManager, SessionManagerError
from imgdata import ImgDataService
from models.metadata_payload import MetadataPayload


def make_service():
    return ImgDataService(SessionManager())


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

    with patch("imgdata.Thread", FakeThread):
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

    with patch("imgdata.Thread", FakeThread):
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

    service.searchNextChecksItem = lambda **kwargs: (_ for _ in ()).throw(
        SessionManagerError({"error": "resume_failed"})
    )

    service._runChecksScan(
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
    assert progress["files_scanned"] == 945
    assert progress["findings_count"] == 12
    assert progress["current_path"] == "/volume1/photo/tests/test.jpg"
    assert progress["resume_cursor"]["path_index"] == 944
    assert progress["resume_cursor"]["findings_count"] == 12
