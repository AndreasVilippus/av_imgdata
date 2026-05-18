#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api import imgdata_api


class _Request:
    def __init__(self, body):
        self._body = body
        self.cookies = {"id": "sid"}
        self.headers = {}

    async def json(self):
        return self._body


class ImgDataApiPersonOrchestrationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_face_create_match_uses_existing_face_orchestration(self):
        request = _Request({
            "face_id": 456,
            "person_name": "Alice",
            "source_name": "Alias",
            "save_mapping": True,
        })

        orchestration_result = {
            "updated": True,
            "operation": "photos_create",
            "target_person": {"id": 123, "name": "Alice"},
            "create_result": {"person_id": 123},
        }

        with patch.object(imgdata_api, "_prepare_session_request", return_value=(
            {"user_key": "user", "cookies": {}, "base_url": "https://example.test"},
            None,
        )), patch.object(
            imgdata_api.IMGDATA,
            "resolveOrCreatePhotosPersonForExistingFace",
            return_value=orchestration_result,
        ) as orchestrate_mock, patch.object(
            imgdata_api.IMGDATA,
            "createMatchedFaceAsPerson",
        ) as direct_create_mock, patch.object(
            imgdata_api.IMGDATA,
            "removeFaceMatchFindingEntry",
            return_value={"removed": True},
        ) as remove_mock, patch.object(
            imgdata_api,
            "_save_name_mapping_if_requested",
            return_value=True,
        ) as mapping_mock:
            response = await imgdata_api.face_create_match(request)

        self.assertTrue(response["success"])
        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="",
            face_id=456,
            person_name="Alice",
            create_missing_person=True,
        )
        direct_create_mock.assert_not_called()
        remove_mock.assert_called_once_with(face_id=456, increment_transferred_count=True)
        mapping_mock.assert_called_once_with(
            save_mapping=True,
            source_name="Alias",
            target_name="Alice",
        )
        self.assertEqual(response["data"]["person_id"], 123)
        self.assertEqual(response["data"]["person_name"], "Alice")
        self.assertEqual(response["data"]["result"], orchestration_result)

    async def test_face_create_metadata_match_uses_metadata_orchestration(self):
        metadata_face = {
            "name": "Alice",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_parsed",
            "source_format": "MWG_REGIONS",
        }
        request = _Request({
            "image_path": "/volume1/photo/image.jpg",
            "metadata_face": metadata_face,
            "person_name": "Alice",
            "source_name": "Alias",
            "save_mapping": True,
        })

        orchestration_result = {
            "updated": True,
            "operation": "photos_create_from_metadata",
            "target_person": {"id": 123, "name": "Alice"},
            "face_id": 456,
            "create_result": {"person_id": 123},
        }

        with patch.object(imgdata_api, "_prepare_session_request", return_value=(
            {"user_key": "user", "cookies": {}, "base_url": "https://example.test"},
            None,
        )), patch.object(
            imgdata_api.IMGDATA,
            "resolveOrCreatePhotosPersonForMetadataFace",
            return_value=orchestration_result,
        ) as orchestrate_mock, patch.object(
            imgdata_api.IMGDATA,
            "createMetadataFaceAsPhotosPerson",
        ) as direct_create_mock, patch.object(
            imgdata_api.IMGDATA,
            "removeFaceMatchFindingMetadataEntry",
            return_value={"removed": True},
        ) as remove_mock, patch.object(
            imgdata_api.IMGDATA,
            "recordFaceMatchTransferProgress",
            return_value={"transferred_count": 1},
        ) as progress_mock, patch.object(
            imgdata_api.IMGDATA,
            "_faceMatchTargetToken",
            return_value="token-1",
        ), patch.object(
            imgdata_api,
            "_save_name_mapping_if_requested",
            return_value=True,
        ) as mapping_mock:
            response = await imgdata_api.face_create_metadata_match(request)

        self.assertTrue(response["success"])
        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/image.jpg",
            metadata_face=metadata_face,
            person_name="Alice",
            create_missing_person=True,
        )
        direct_create_mock.assert_not_called()
        remove_mock.assert_called_once_with(
            image_path="/volume1/photo/image.jpg",
            metadata_face=metadata_face,
            increment_transferred_count=True,
        )
        progress_mock.assert_called_once_with("user", skip_targets=["token-1"])
        mapping_mock.assert_called_once_with(
            save_mapping=True,
            source_name="Alias",
            target_name="Alice",
        )
        self.assertEqual(response["data"]["face_id"], 456)
        self.assertEqual(response["data"]["person_id"], 123)
        self.assertEqual(response["data"]["transfer_result"], orchestration_result)


if __name__ == "__main__":
    unittest.main()
