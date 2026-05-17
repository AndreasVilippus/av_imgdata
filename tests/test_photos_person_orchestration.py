#!/usr/bin/env python3
"""Contract tests for the central Photos person assignment/create orchestration.

These tests intentionally describe the target architecture. They are expected to
fail until ImgDataService exposes the central orchestration methods used below.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


class PhotosPersonOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_existing_photos_face_assigns_existing_person_after_mapping(self):
        with patch.object(
            self.service.name_mappings,
            "findNameMapping",
            return_value={"source_name": "Alias", "target_name": "Canonical Name"},
        ), patch.object(
            self.service.photos,
            "findKnownPersonByName",
            return_value={"id": 123, "name": "Canonical Name"},
        ) as find_person_mock, patch.object(
            self.service,
            "assignMatchedFaceToKnownPerson",
            return_value={"assigned": True},
        ) as assign_mock, patch.object(
            self.service,
            "createMatchedFaceAsPerson",
        ) as create_mock:
            result = self.service.resolveOrCreatePhotosPersonForExistingFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                face_id=456,
                person_name="Alias",
                item_id=789,
                create_missing_person=False,
            )

        find_person_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            name="Canonical Name",
        )
        assign_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=456,
            person_id=123,
            person_name="Canonical Name",
            item_id=789,
            image_path="/volume1/photo/image.jpg",
        )
        create_mock.assert_not_called()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_assign")
        self.assertEqual(result["resolved_name"], "Canonical Name")
        self.assertEqual(result["target_person"], {"id": 123, "name": "Canonical Name"})

    def test_existing_photos_face_creates_missing_person_when_allowed(self):
        with patch.object(self.service.name_mappings, "findNameMapping", return_value=None), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(self.service, "createMatchedFaceAsPerson", return_value={"person_id": 321}) as create_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock:
            result = self.service.resolveOrCreatePhotosPersonForExistingFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                face_id=456,
                person_name="New Person",
                item_id=789,
                create_missing_person=True,
            )

        create_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=456,
            person_name="New Person",
            item_id=789,
            image_path="/volume1/photo/image.jpg",
        )
        assign_mock.assert_not_called()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_create")
        self.assertEqual(result["target_person"], {"id": 321, "name": "New Person"})

    def test_existing_photos_face_warns_when_person_missing_and_create_not_allowed(self):
        with patch.object(self.service.name_mappings, "findNameMapping", return_value=None), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(self.service, "createMatchedFaceAsPerson") as create_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock:
            result = self.service.resolveOrCreatePhotosPersonForExistingFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                face_id=456,
                person_name="Missing Person",
                item_id=789,
                create_missing_person=False,
            )

        create_mock.assert_not_called()
        assign_mock.assert_not_called()
        self.assertFalse(result["updated"])
        self.assertEqual(result["warning"], "checks:warning_target_person_not_found")
        self.assertEqual(result["details"]["lookup_name"], "Missing Person")

    def test_metadata_face_adds_and_assigns_existing_person_after_mapping(self):
        metadata_face = {
            "name": "Alias",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_parsed",
            "source_format": "MWG_REGIONS",
        }
        with patch.object(
            self.service.name_mappings,
            "findNameMapping",
            return_value={"source_name": "Alias", "target_name": "Canonical Name"},
        ), patch.object(
            self.service.photos,
            "findKnownPersonByName",
            return_value={"id": 123, "name": "Canonical Name"},
        ), patch.object(
            self.service,
            "addMatchedMetadataFaceToPhotos",
            return_value={"face_id": 456, "item_id": 789},
        ) as add_mock, patch.object(
            self.service,
            "assignMatchedFaceToKnownPerson",
            return_value={"assigned": True},
        ) as assign_mock, patch.object(
            self.service,
            "createMetadataFaceAsPhotosPerson",
        ) as create_mock:
            result = self.service.resolveOrCreatePhotosPersonForMetadataFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=metadata_face,
                person_name="Alias",
                create_missing_person=False,
            )

        add_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            metadata_face=metadata_face,
            person_id=123,
        )
        assign_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=456,
            person_id=123,
            person_name="Canonical Name",
            item_id=789,
            image_path="/volume1/photo/image.jpg",
        )
        create_mock.assert_not_called()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_add_assign")
        self.assertEqual(result["target_person"], {"id": 123, "name": "Canonical Name"})

    def test_metadata_face_uses_create_flow_when_person_missing_and_allowed(self):
        metadata_face = {
            "name": "New Person",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_parsed",
            "source_format": "MWG_REGIONS",
        }
        with patch.object(self.service.name_mappings, "findNameMapping", return_value=None), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(self.service, "createMetadataFaceAsPhotosPerson", return_value={"face_id": 456, "person_id": 321}) as create_mock, \
             patch.object(self.service, "addMatchedMetadataFaceToPhotos") as add_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock:
            result = self.service.resolveOrCreatePhotosPersonForMetadataFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=metadata_face,
                person_name="New Person",
                create_missing_person=True,
            )

        create_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            metadata_face=metadata_face,
            person_name="New Person",
        )
        add_mock.assert_not_called()
        assign_mock.assert_not_called()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_create_from_metadata")
        self.assertEqual(result["target_person"], {"id": 321, "name": "New Person"})

    def test_metadata_face_warns_when_person_missing_and_create_not_allowed(self):
        metadata_face = {
            "name": "Missing Person",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_parsed",
            "source_format": "MWG_REGIONS",
        }
        with patch.object(self.service.name_mappings, "findNameMapping", return_value=None), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(self.service, "createMetadataFaceAsPhotosPerson") as create_mock, \
             patch.object(self.service, "addMatchedMetadataFaceToPhotos") as add_mock, \
             patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock:
            result = self.service.resolveOrCreatePhotosPersonForMetadataFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=metadata_face,
                person_name="Missing Person",
                create_missing_person=False,
            )

        create_mock.assert_not_called()
        add_mock.assert_not_called()
        assign_mock.assert_not_called()
        self.assertFalse(result["updated"])
        self.assertEqual(result["warning"], "checks:warning_target_person_not_found")
        self.assertEqual(result["details"]["lookup_name"], "Missing Person")


if __name__ == "__main__":
    unittest.main()
