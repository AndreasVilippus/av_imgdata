#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataOperationError, ImgDataService


class MetadataFaceCreateWithNameTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def _metadata_face(self):
        return {
            "name": "ZZ_ID_0019",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_parsed",
            "source_format": "MWG_REGIONS",
        }

    def test_add_matched_metadata_face_to_photos_forwards_person_name(self):
        def add_face_side_effect(**kwargs):
            return {
                "list": [
                    {
                        "face_id": 147695,
                        "face_id_temp": kwargs["face_id_temp"],
                    }
                ]
            }

        created_photos_face = {
            "face_id": 147695,
            "person_id": 38517,
            "name": "ZZ_ID_0019",
            "bbox": {
                "top_left": {"x": 0.4, "y": 0.4},
                "bottom_right": {"x": 0.6, "y": 0.6},
            },
            "face_bounding_box": {
                "top_left": {"x": 0.4, "y": 0.4},
                "bottom_right": {"x": 0.6, "y": 0.6},
            },
        }

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 114213}), \
             patch.object(self.service.photos, "list_faceFotoTeamItems", side_effect=[[], [created_photos_face]]), \
             patch.object(
                 self.service.photos,
                 "addFaceToItem",
                 side_effect=add_face_side_effect,
             ) as add_mock, \
             patch.object(self.service, "_validatePhotosFaceOnItem"):
            result = self.service.addMatchedMetadataFaceToPhotos(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=self._metadata_face(),
                person_name="ZZ_ID_0019",
            )

        self.assertTrue(result["created"])
        self.assertEqual(result["face_id"], 147695)
        self.assertEqual(result["person_name"], "ZZ_ID_0019")
        self.assertEqual(result["person_id"], 38517)
        self.assertEqual(add_mock.call_args.kwargs["person_name"], "ZZ_ID_0019")
        self.assertIsNone(add_mock.call_args.kwargs["person_id"])

    def test_missing_photos_item_submits_reindex_and_reports_status(self):
        previous_lookup_cache = self.service.photos_lookup_cache
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = str(Path(temp_dir) / "missing-in-photos.jpg")
            Path(image_path).touch()

            with patch.object(
                self.service.config,
                "readMergedConfig",
                return_value={"photos": {"REINDEX_MISSING_ITEMS": True}},
            ), patch.object(
                self.service.core,
                "getSharedFolder",
                return_value="/volume1/photo",
            ), patch.object(
                self.service.photos,
                "findFotoTeamItemByPath",
                return_value=None,
            ), patch.object(
                self.service.photos,
                "indexFotoTeamPaths",
                return_value={"accepted": True},
            ) as index_mock:
                with self.assertRaises(ImgDataOperationError) as raised:
                    self.service.addMatchedMetadataFaceToPhotos(
                        user_key="user",
                        cookies={},
                        base_url="https://example.test",
                        image_path=image_path,
                        metadata_face=self._metadata_face(),
                        person_name="ZZ_ID_0019",
                    )

        self.assertEqual(str(raised.exception), "photos_item_not_found_for_image")
        self.assertEqual(
            raised.exception.details["reindex"],
            {
                "status": "submitted",
                "requested": True,
                "path": image_path,
                "type": "basic",
                "result": {"accepted": True},
            },
        )
        index_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            paths=[image_path],
            index_type="basic",
        )
        self.assertIsNot(self.service.photos_lookup_cache, previous_lookup_cache)

    def test_create_metadata_face_as_photos_person_uses_add_face_name_flow(self):
        metadata_face = self._metadata_face()
        with patch.object(
            self.service,
            "addMatchedMetadataFaceToPhotos",
            return_value={
                "created": True,
                "face_id": 147695,
                "person_id": 38517,
                "person_name": "ZZ_ID_0019",
                "add_result": {"list": [{"face_id": 147695}]},
            },
        ) as add_mock, patch.object(
            self.service,
            "createMatchedFaceAsPerson",
        ) as create_mock:
            result = self.service.createMetadataFaceAsPhotosPerson(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=metadata_face,
                person_name="ZZ_ID_0019",
            )

        add_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            metadata_face=metadata_face,
            person_name="ZZ_ID_0019",
        )
        create_mock.assert_not_called()
        self.assertEqual(result["face_id"], 147695)
        self.assertEqual(result["person_id"], 38517)
        self.assertEqual(result["person_name"], "ZZ_ID_0019")

    def test_metadata_orchestration_create_missing_person_uses_name_flow(self):
        with patch.object(self.service.name_mappings, "findNameMapping", return_value=None), \
             patch.object(self.service.photos, "findKnownPersonByName", return_value=None), \
             patch.object(
                 self.service,
                 "createMetadataFaceAsPhotosPerson",
                 return_value={"face_id": 147695, "person_id": 38517, "person_name": "ZZ_ID_0019"},
             ) as create_mock:
            result = self.service.resolveOrCreatePhotosPersonForMetadataFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/image.jpg",
                metadata_face=self._metadata_face(),
                person_name="ZZ_ID_0019",
                create_missing_person=True,
            )

        create_mock.assert_called_once()
        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_create_from_metadata")
        self.assertEqual(result["target_person"], {"id": 38517, "name": "ZZ_ID_0019"})


if __name__ == "__main__":
    unittest.main()
