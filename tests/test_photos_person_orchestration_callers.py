#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class PhotosPersonOrchestrationCallerTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_replace_checks_face_name_delegates_photos_face_to_central_orchestration(self):
        expected = {
            "updated": True,
            "warning": "",
            "operation": "photos_assign",
            "target_person": {"id": 123, "name": "Alice"},
            "resolved_name": "Alice",
        }

        with patch.object(
            self.service,
            "resolveOrCreatePhotosPersonForExistingFace",
            return_value=expected,
        ) as orchestrate_mock:
            result = self.service.replaceChecksFaceName(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                face_data={
                    "source_format": "PHOTOS",
                    "face_id": 456,
                    "item_id": 789,
                },
                new_name="Alice",
                create_missing_person=True,
            )

        self.assertEqual(result, expected)
        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            face_id=456,
            person_name="Alice",
            item_id=789,
            create_missing_person=True,
        )

    def test_replace_checks_face_name_keeps_metadata_write_direct(self):
        with patch.object(
            self.service,
            "replaceMetadataFaceName",
            return_value={"updated": True, "warning": ""},
        ) as metadata_mock, patch.object(
            self.service,
            "resolveOrCreatePhotosPersonForExistingFace",
        ) as orchestrate_mock:
            result = self.service.replaceChecksFaceName(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                face_data={
                    "source_format": "MWG_REGIONS",
                    "name": "Old",
                },
                new_name="Alice",
                create_missing_person=True,
            )

        metadata_mock.assert_called_once()
        orchestrate_mock.assert_not_called()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "metadata_write")

    def test_normalize_photos_person_by_mapping_creates_target_via_central_orchestration(self):
        known_persons = [{"id": 10, "name": "Old Name"}]

        with patch.object(self.service, "_collectPhotoFaceIdsForPerson", return_value=[111, 112]), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForExistingFace",
                 return_value={
                     "updated": True,
                     "operation": "photos_create",
                     "target_person": {"id": 222, "name": "New Name"},
                 },
             ) as orchestrate_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson", return_value={"assigned": True}) as assign_mock:
            result = self.service._normalizePhotosPersonByMapping(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                person={"id": 10, "name": "Old Name"},
                known_persons=known_persons,
                mapping_lookup={"old name": "New Name"},
            )

        self.assertTrue(result["updated"])
        self.assertEqual(result["target_person_id"], 222)
        self.assertEqual(result["faces_reassigned"], 2)
        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="",
            face_id=111,
            person_name="New Name",
            create_missing_person=True,
        )
        assign_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=112,
            person_id=222,
            person_name="New Name",
        )

    def test_normalize_photos_person_by_mapping_reassigns_existing_target_without_create(self):
        known_persons = [{"id": 10, "name": "Old Name"}, {"id": 222, "name": "New Name"}]

        with patch.object(self.service, "_collectPhotoFaceIdsForPerson", return_value=[111, 112]), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value={"id": 222, "name": "New Name"}), \
             patch.object(self.service, "resolveOrCreatePhotosPersonForExistingFace") as orchestrate_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson", return_value={"assigned": True}) as assign_mock:
            result = self.service._normalizePhotosPersonByMapping(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                person={"id": 10, "name": "Old Name"},
                known_persons=known_persons,
                mapping_lookup={"old name": "New Name"},
            )

        self.assertTrue(result["updated"])
        self.assertEqual(result["target_person_id"], 222)
        self.assertEqual(result["faces_reassigned"], 2)
        orchestrate_mock.assert_not_called()
        self.assertEqual(assign_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
