#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath("src"))

from handler.photos_handler import PhotosHandler


class PhotosHandlerAddFaceNameTests(unittest.TestCase):
    def _handler(self):
        session_manager = Mock()
        session_manager.call_api_post.return_value = {
            "success": True,
            "data": {
                "list": [
                    {"face_id": 147695, "face_id_temp": "114213-0"}
                ]
            },
        }
        handler = PhotosHandler(session_manager, Mock())
        return handler, session_manager

    def test_add_face_to_item_includes_name_when_person_name_provided(self):
        handler, session_manager = self._handler()

        result = handler.addFaceToItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            id_item=114213,
            face_bbox={
                "top_left": {"x": 0.1, "y": 0.2},
                "bottom_right": {"x": 0.3, "y": 0.4},
            },
            face_id_temp="114213-0",
            person_name="ZZ_ID_0019",
        )

        self.assertEqual(result["list"][0]["face_id"], 147695)
        params = session_manager.call_api_post.call_args.kwargs["params"]
        face_payload = params["face"][0]
        self.assertEqual(face_payload["name"], "ZZ_ID_0019")
        self.assertNotIn("person_id", face_payload)

    def test_add_face_to_item_prefers_person_id_over_name(self):
        handler, session_manager = self._handler()

        handler.addFaceToItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            id_item=114213,
            face_bbox={
                "top_left": {"x": 0.1, "y": 0.2},
                "bottom_right": {"x": 0.3, "y": 0.4},
            },
            face_id_temp="114213-0",
            person_id=35820,
            person_name="Ignored Name",
        )

        params = session_manager.call_api_post.call_args.kwargs["params"]
        face_payload = params["face"][0]
        self.assertEqual(face_payload["person_id"], 35820)
        self.assertNotIn("name", face_payload)


if __name__ == "__main__":
    unittest.main()
