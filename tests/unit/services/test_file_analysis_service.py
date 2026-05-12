import os
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


if __name__ == "__main__":
    unittest.main()
