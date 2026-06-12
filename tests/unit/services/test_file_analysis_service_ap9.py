from concurrent.futures import ThreadPoolExecutor

from services.file_analysis_service import FileAnalysisService


def make_service(tmp_path):
    return FileAnalysisService(str(tmp_path / "file_analysis.json"))


def test_latest_result_round_trip_uses_sqlite(tmp_path):
    service = make_service(tmp_path)

    assert service.writeLatestResult({"status": "finished", "count": 42})
    assert service.readLatestResult() == {"status": "finished", "count": 42}
    assert not (tmp_path / "file_analysis.json").exists()


def test_findings_round_trip_and_delete_use_sqlite(tmp_path):
    service = make_service(tmp_path)
    payload = {"status": "finished", "entries": [{"id": 1}, {"id": 2}]}

    assert service.writeCheckFindings("duplicate_faces", payload)
    assert service.readCheckFindings("duplicate_faces")["entries"] == payload["entries"]
    assert service.deleteCheckFindings("duplicate_faces")
    assert service.readCheckFindings("duplicate_faces") == {}


def test_findings_are_independent_by_type(tmp_path):
    service = make_service(tmp_path)

    service.writeCheckFindings("dimension_issues", {"entries": [{"id": "dimension"}]})
    service.writeCheckFindings("duplicate_faces", {"entries": [{"id": "duplicate"}]})

    assert service.readCheckFindings("dimension_issues")["entries"][0]["id"] == "dimension"
    assert service.readCheckFindings("duplicate_faces")["entries"][0]["id"] == "duplicate"


def test_runtime_state_round_trip_and_delete_use_sqlite(tmp_path):
    service = make_service(tmp_path)

    assert service.writeRuntimeState("checks_progress", "user_duplicate_faces", {"progress": 50})
    assert service.readRuntimeState("checks_progress", "user_duplicate_faces") == {"progress": 50}
    assert service.deleteRuntimeState("checks_progress", "user_duplicate_faces")
    assert service.readRuntimeState("checks_progress", "user_duplicate_faces") == {}


def test_append_findings_preserves_all_thread_updates(tmp_path):
    service = make_service(tmp_path)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda index: service.appendCheckFindingEntries("duplicate_faces", [{"id": index}]),
            range(20),
        ))

    assert all(results)
    assert sorted(entry["id"] for entry in service.readCheckFindings("duplicate_faces")["entries"]) == list(range(20))


def test_invalid_payloads_are_rejected(tmp_path):
    service = make_service(tmp_path)

    assert not service.writeLatestResult(None)
    assert not service.writeCheckFindings("duplicate_faces", None)
    assert not service.writeRuntimeState("checks_progress", "user", None)
