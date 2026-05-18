#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class FaceMatchFileListStatusTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_search_file_face_in_sources_reports_file_listing_status(self):
        message_keys = []

        def record_message(_user_key, message_key, **_updates):
            message_keys.append(message_key)

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service, "_fileFaceMatchSourceScope", return_value="metadata"), \
             patch.object(self.service, "_getReverseFaceMatchCandidateEntries", return_value=[]), \
             patch.object(self.service.files, "listImageFiles", return_value=[]), \
             patch.object(self.service, "_setFaceMatchingProgressMessage", side_effect=record_message), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False):
            result = self.service.searchFileFaceInSources(
                user_key="user",
                cookies={},
                base_url="https://example.test",
            )

        self.assertTrue(result["searched"])
        self.assertIn("face_match:progress_listing_files", message_keys)
        self.assertIn("face_match:progress_files_listed", message_keys)
        self.assertLess(
            message_keys.index("face_match:progress_listing_files"),
            message_keys.index("face_match:progress_files_listed"),
        )


if __name__ == "__main__":
    unittest.main()
