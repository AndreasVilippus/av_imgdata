from services.file_analysis_service import FileAnalysisService


def make_service(tmp_path):
    return FileAnalysisService(str(tmp_path / "file_analysis.json"))


def test_face_match_candidates_are_persisted_in_sqlite(tmp_path):
    service = make_service(tmp_path)
    payload = {
        "status": "running",
        "shared_folder": "/volume1/photo",
        "entries": [{"image_path": "/volume1/photo/test.jpg"}],
    }

    assert service.writeCheckFindings("face_match_candidates", payload)
    assert service.readCheckFindings("face_match_candidates")["entries"] == payload["entries"]


def test_findings_status_omits_entries_and_reports_stored_count(tmp_path):
    service = make_service(tmp_path)
    service.writeCheckFindings(
        "duplicate_faces",
        {
            "status": "running",
            "save_only": True,
            "entries": [{"image_path": "/volume1/photo/test.jpg"}],
        },
    )

    status = service.readCheckFindingsStatus("duplicate_faces")

    assert status["status"] == "running"
    assert status["save_only"] is True
    assert status["count"] == 1
    assert "entries" not in status


def test_read_findings_without_keys_removes_requested_top_level_fields(tmp_path):
    service = make_service(tmp_path)
    service.writeCheckFindings(
        "name_conflicts",
        {
            "paths": ["/volume1/photo/test.jpg"],
            "entries": [{"image_path": "/volume1/photo/test.jpg"}],
        },
    )

    findings = service.readCheckFindingsEntries("name_conflicts")

    assert "paths" not in findings
    assert findings["count"] == 1


def test_delete_findings_removes_sqlite_snapshot(tmp_path):
    service = make_service(tmp_path)
    service.writeCheckFindings("dimension_issues", {"entries": [{"id": 1}]})

    assert service.deleteCheckFindings("dimension_issues")
    assert service.readCheckFindings("dimension_issues") == {}
