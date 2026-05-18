#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload


class MissingPhotosFacesEarlySkipTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    @staticmethod
    def _payload_with_faces(image_path, faces):
        return MetadataPayload(
            image_path=image_path,
            has_xmp=bool(faces),
            faces=faces,
            image_dimensions={"width": 1000, "height": 800, "unit": "pixel"},
        )

    @staticmethod
    def _face(name):
        return MetadataFace.from_center_box(
            name=name,
            x=0.5,
            y=0.5,
            w=0.2,
            h=0.2,
            source="xmp_file",
            source_format="MWG_REGIONS",
        )

    def test_search_missing_photos_faces_skips_photos_lookup_without_named_metadata_faces(self):
        image_path = "/volume1/photo/test.jpg"
        payload = self._payload_with_faces(image_path, [self._face("")])

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.files, "listImageFiles", return_value=[image_path]), \
             patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False), \
             patch.object(self.service, "_setFaceMatchingProgressMessage"), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service.photos, "findFotoTeamItemByPath") as find_item_mock, \
             patch.object(self.service.photos, "list_faceFotoTeamItems") as list_faces_mock:
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
            )

        self.assertTrue(result["searched"])
        self.assertIsNone(result["image"])
        find_item_mock.assert_not_called()
        list_faces_mock.assert_not_called()

    def test_search_missing_photos_faces_keeps_photos_lookup_with_named_metadata_faces(self):
        image_path = "/volume1/photo/test.jpg"
        payload = self._payload_with_faces(image_path, [self._face("Alice")])

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.files, "listImageFiles", return_value=[image_path]), \
             patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False), \
             patch.object(self.service, "_setFaceMatchingProgressMessage"), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 42}) as find_item_mock, \
             patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]) as list_faces_mock, \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(self.service.photos, "debugKnownPersonLookup", return_value={}):
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
            )

        self.assertTrue(result["searched"])
        self.assertEqual(result["image_path"], image_path)
        find_item_mock.assert_called_once()
        list_faces_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            id_item=42,
        )

    def test_save_only_missing_photos_faces_resumes_persisted_findings_before_final_write(self):
        old_path = "/volume1/photo/old.jpg"
        new_path = "/volume1/photo/new.jpg"
        old_face = self._face("Alice")
        new_face = self._face("Bob")
        old_payload = self._payload_with_faces(old_path, [old_face])
        new_payload = self._payload_with_faces(new_path, [new_face])
        old_entry = {
            "action": "mark_missing_photos_faces",
            "image_path": old_path,
            "metadata_face": old_face.to_dict(),
        }

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.files, "listImageFiles", return_value=[old_path, new_path]), \
             patch.object(self.service, "_readImageMetadata", side_effect=[old_payload, new_payload]), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False), \
             patch.object(self.service, "_setFaceMatchingProgressMessage"), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service, "getFaceMatchFindings", return_value={
                 "action": "mark_missing_photos_faces",
                 "save_only": True,
                 "entries": [old_entry],
             }), \
             patch.object(self.service.photos, "findFotoTeamItemByPath", side_effect=[
                 {"id": 41, "filename": "old.jpg"},
                 {"id": 42, "filename": "new.jpg"},
             ]), \
             patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]), \
             patch.object(self.service, "_selectMissingPhotosFaceCandidate", side_effect=[
                 (old_face, {"MWG_REGIONS": 1}),
                 (new_face, {"MWG_REGIONS": 1}),
             ]), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_lookupMatchedPersonBySourceName", return_value=(None, None, {})), \
             patch.object(self.service, "_writeFaceMatchFindings") as write_findings_mock:
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                save_only=True,
                resume_cursor={
                    "action": "mark_missing_photos_faces",
                    "save_only": True,
                    "findings_count": 1,
                    "path_index": 0,
                    "skip_targets": [],
                },
            )

        self.assertTrue(result["searched"])
        self.assertEqual(result["findings_count"], 2)
        final_write = write_findings_mock.call_args_list[-1].kwargs
        self.assertEqual(final_write["status"], "finished")
        self.assertEqual(len(final_write["entries"]), 2)
        self.assertEqual(final_write["entries"][0]["image_path"], old_path)
        self.assertEqual(final_write["entries"][1]["image_path"], new_path)

    def test_save_only_missing_photos_faces_flushes_running_findings_before_final_write(self):
        image_path = "/volume1/photo/new.jpg"
        face = self._face("Bob")
        payload = self._payload_with_faces(image_path, [face])

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.files, "listImageFiles", return_value=[image_path]), \
             patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False), \
             patch.object(self.service, "_setFaceMatchingProgressMessage"), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service, "_shouldFlushFaceMatchFindings", return_value=True), \
             patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 42, "filename": "new.jpg"}), \
             patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]), \
             patch.object(self.service, "_selectMissingPhotosFaceCandidate", return_value=(face, {"MWG_REGIONS": 1})), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_lookupMatchedPersonBySourceName", return_value=(None, None, {})), \
             patch.object(self.service, "_writeFaceMatchFindings") as write_findings_mock:
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                save_only=True,
            )

        self.assertTrue(result["searched"])
        running_writes = [
            call.kwargs
            for call in write_findings_mock.call_args_list
            if call.kwargs.get("status") == "running"
        ]
        self.assertEqual(len(running_writes), 1)
        self.assertFalse(running_writes[0]["finished"])
        self.assertEqual(len(running_writes[0]["entries"]), 1)
        self.assertEqual(write_findings_mock.call_args_list[-1].kwargs["status"], "finished")


if __name__ == "__main__":
    unittest.main()
