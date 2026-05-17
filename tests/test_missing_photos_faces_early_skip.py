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


if __name__ == "__main__":
    unittest.main()
