import os
import json
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))

from services.file_analysis_service import FileAnalysisService


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

            self.assertEqual(status.get("status"), "running")
            self.assertEqual(status.get("action"), "mark_missing_photos_faces")
            self.assertEqual(status.get("count"), 1909)
            self.assertTrue(status.get("save_only"))
            self.assertNotIn("entries", status)

    def test_check_findings_status_writes_lightweight_sidecar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "running",
                "action": "mark_missing_photos_faces",
                "save_only": True,
                "count": 2,
                "entries": [
                    {"image_path": "/volume1/photo/a.jpg", "debug": {"large": "x" * 100}},
                    {"image_path": "/volume1/photo/b.jpg", "debug": {"large": "y" * 100}},
                ],
            }))

            status_path = service._finding_status_path("face_match")
            self.assertTrue(status_path.exists())
            stored_status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(stored_status.get("count"), 2)
            self.assertEqual(stored_status.get("action"), "mark_missing_photos_faces")
            self.assertNotIn("entries", stored_status)

    def test_check_findings_status_fallback_skips_legacy_entries_payload(self):
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
            self.assertEqual(status.get("status"), "running")
            self.assertEqual(status.get("transferred_count"), 7)
            self.assertTrue(status.get("save_only"))
            self.assertNotIn("entries", status)

    def test_check_findings_status_reads_without_findings_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "finished",
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }))

            def fail_if_locked(_finding_type):
                raise AssertionError("status read must not acquire findings lock")

            service.lockCheckFindings = fail_if_locked
            status = service.readCheckFindingsStatus("face_match")

            self.assertEqual(status.get("count"), 1)
            self.assertEqual(status.get("status"), "finished")

    def test_delete_check_findings_removes_status_sidecar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileAnalysisService(result_path=os.path.join(tmpdir, "file_analysis.json"))
            self.assertTrue(service.writeCheckFindings("face_match", {
                "status": "finished",
                "entries": [{"image_path": "/volume1/photo/test.jpg"}],
            }))

            self.assertTrue(service.deleteCheckFindings("face_match"))

            self.assertFalse(service._finding_path("face_match").exists())
            self.assertFalse(service._finding_status_path("face_match").exists())


if __name__ == "__main__":
    unittest.main()
