import os
import json
import sys
import tempfile
import unittest
from io import StringIO

sys.path.insert(0, os.path.abspath("src"))

from services.file_analysis_service import FileAnalysisService


class StopAfterEntriesStart:
    def __init__(self, text):
        self.text = text
        self.index = 0
        self.seen_entries_start = False

    def read(self, size=1):
        if size != 1:
            raise AssertionError("test handle only supports single-character reads")
        if self.seen_entries_start:
            raise AssertionError("status reader must not scan entries payload")
        if self.index >= len(self.text):
            return ""
        char = self.text[self.index]
        self.index += 1
        if self.text[:self.index].endswith('"entries": ['):
            self.seen_entries_start = True
        return char


class FileAnalysisServiceTests(unittest.TestCase):
    def test_face_match_candidates_finding_type_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            payload = {
                "job_id": "job-1",
                "started_at": "2026-04-10T21:15:49+02:00",
                "finished_at": "",
                "last_updated_at": "2026-04-10T21:15:49+02:00",
                "status": "running",
                "shared_folder": "/volume1/photo",
                "count": 1,
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }

            written = service.writeCheckFindings("face_match_candidates", payload)

            self.assertTrue(written)
            stored = service.readCheckFindings("face_match_candidates")
            self.assertEqual(stored.get("count"), 1)
            self.assertEqual(stored.get("entries"), payload["entries"])

    def test_check_findings_status_omits_entries_and_preserves_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            payload = {
                "status": "running",
                "action": "mark_missing_photos_faces",
                "save_only": True,
                "auto": True,
                "transferred_count": 3,
                "count": 1909,
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }

            self.assertTrue(service.writeCheckFindings("face_match", payload))
            status = service.readCheckFindingsStatus("face_match")

            self.assertEqual(status.get("action"), "mark_missing_photos_faces")
            self.assertEqual(status.get("count"), 1909)
            self.assertNotIn("status", status)
            self.assertNotIn("save_only", status)
            self.assertNotIn("entries", status)

    def test_check_findings_status_streams_top_level_fields_and_skips_entries_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            finding_path = service._finding_path("face_match")
            finding_path.parent.mkdir(parents=True, exist_ok=True)
            finding_path.write_text(json.dumps({
                "action": "mark_missing_photos_faces",
                "auto": True,
                "count": 1909,
                "entries": [
                    {"image_path": f"/volume1/photo/{index}.jpg", "nested": {"value": index}}
                    for index in range(50)
                ],
                "save_only": True,
                "status": "running",
                "transferred_count": 7,
            }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

            status = service.readCheckFindingsStatus("face_match")

            self.assertEqual(status.get("action"), "mark_missing_photos_faces")
            self.assertEqual(status.get("count"), 1909)
            self.assertNotIn("status", status)
            self.assertNotIn("transferred_count", status)
            self.assertNotIn("save_only", status)
            self.assertNotIn("entries", status)

    def test_check_findings_status_stops_before_entries_payload(self):
        payload = (
            '{"action": "mark_missing_photos_faces", "auto": true, "count": 1909, '
            '"entries": [{"image_path": "/volume1/photo/test.jpg"}], '
            '"save_only": true, "status": "running", "transferred_count": 7}'
        )

        status = FileAnalysisService._read_check_findings_status_stream(StopAfterEntriesStart(payload))

        self.assertEqual(status.get("action"), "mark_missing_photos_faces")
        self.assertEqual(status.get("count"), 1909)
        self.assertTrue(status.get("auto"))
        self.assertNotIn("status", status)
        self.assertNotIn("entries", status)

    def test_check_findings_entries_skips_obsolete_paths_payload(self):
        payload = (
            '{"action": "mark_missing_photos_faces", "auto": false, "count": 1909, '
            '"entries": [{"image_path": "/volume1/photo/test.jpg"}], '
            '"paths": ["/volume1/photo/huge-legacy-path-list.jpg"], '
            '"save_only": false, "status": "finished", "transferred_count": 0}'
        )

        findings = FileAnalysisService._read_check_findings_without_keys_stream(
            StringIO(payload),
            {"paths"},
        )

        self.assertEqual(findings.get("action"), "mark_missing_photos_faces")
        self.assertEqual(findings.get("count"), 1909)
        self.assertEqual(findings.get("entries"), [{"image_path": "/volume1/photo/test.jpg"}])
        self.assertEqual(findings.get("status"), "finished")
        self.assertNotIn("paths", findings)

    def test_check_findings_entries_skips_legacy_heavy_entry_fields(self):
        payload = (
            '{"action": "mark_missing_photos_faces", "count": 1, '
            '"entries": [{"action": "mark_missing_photos_faces", '
            '"debug": {"candidate_persons": ["large legacy payload"]}, '
            '"image_path": "/volume1/photo/test.jpg"}], '
            '"paths": ["/volume1/photo/huge-legacy-path-list.jpg"]}'
        )

        findings = FileAnalysisService._read_check_findings_without_keys_stream(
            StringIO(payload),
            {"paths"},
            stop_after_keys={"entries"},
            entry_skip_keys={"debug"},
        )

        self.assertEqual(findings.get("entries"), [{
            "action": "mark_missing_photos_faces",
            "image_path": "/volume1/photo/test.jpg",
        }])
        self.assertTrue(findings.get("_stream_compacted"))

    def test_check_findings_status_reads_without_findings_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "finished",
                "count": 1,
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }))

            def fail_if_locked(_finding_type):
                raise AssertionError("status read must not acquire findings lock")

            service.lockCheckFindings = fail_if_locked
            status = service.readCheckFindingsStatus("face_match")

            self.assertEqual(status.get("count"), 1)
            self.assertNotIn("status", status)

    def test_check_findings_status_without_top_level_count_does_not_count_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "finished",
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }))

            status = service.readCheckFindingsStatus("face_match")

            self.assertEqual(status.get("count"), 0)
            self.assertNotIn("status", status)
            self.assertNotIn("entries", status)

    def test_delete_check_findings_removes_findings_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "finished",
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }))

            self.assertTrue(service.deleteCheckFindings("face_match"))

            self.assertFalse(service._finding_path("face_match").exists())


if __name__ == "__main__":
    unittest.main()
