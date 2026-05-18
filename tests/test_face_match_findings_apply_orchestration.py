#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class FaceMatchFindingsApplyOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def _stored_mark_missing_entry(self):
        return {
            "action": "mark_missing_photos_faces",
            "image_path": "/volume1/photo/image.jpg",
            "metadata_face": {
                "name": "Alice",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
                "source": "embedded_xmp_parsed",
                "source_format": "MWG_REGIONS",
            },
            "source_name": "Alice",
            "matched_person": {"id": 123, "name": "Alice"},
        }

    def test_auto_apply_mark_missing_photos_faces_uses_metadata_orchestration(self):
        entry = self._stored_mark_missing_entry()
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [entry],
        }

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings),              patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]),              patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons),              patch.object(self.service, "_storedFaceMatchEntryExists", return_value=True),              patch.object(self.service, "_resolveStoredFaceMatchEntry", return_value=entry),              patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForMetadataFace",
                 return_value={"updated": True, "operation": "photos_add_assign"},
             ) as orchestrate_mock,              patch.object(self.service, "addMatchedMetadataFaceToPhotos") as add_mock,              patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock,              patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            metadata_face=entry["metadata_face"],
            person_name="Alice",
            create_missing_person=False,
        )
        add_mock.assert_not_called()
        assign_mock.assert_not_called()
        persist_mock.assert_called_once()
        persist_kwargs = persist_mock.call_args.kwargs
        self.assertEqual(persist_kwargs["entries"], [])
        self.assertEqual(persist_kwargs["transferred_count"], 1)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["transferred_count"], 1)

    def test_auto_apply_mark_missing_photos_faces_keeps_entry_when_orchestration_warns(self):
        entry = self._stored_mark_missing_entry()
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [entry],
        }

        warning_result = {
            "updated": False,
            "warning": "checks:warning_target_person_not_found",
            "details": {"lookup_name": "Alice"},
        }

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings),              patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]),              patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons),              patch.object(self.service, "_storedFaceMatchEntryExists", return_value=True),              patch.object(self.service, "_resolveStoredFaceMatchEntry", return_value=entry),              patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForMetadataFace",
                 return_value=warning_result,
             ) as orchestrate_mock,              patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        orchestrate_mock.assert_called_once()
        persist_mock.assert_not_called()
        self.assertEqual(result["entries"], [entry])
        self.assertEqual(result["transferred_count"], 0)


if __name__ == "__main__":
    unittest.main()
