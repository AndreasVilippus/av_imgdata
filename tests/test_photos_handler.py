#!/usr/bin/env python3
import os
import sys
import unittest
from copy import deepcopy

sys.path.insert(0, os.path.abspath("src"))

from handler.photos_handler import PhotosHandler, PhotosLookupCache


class DummyConfigService:
    def __init__(self, person_sort_order="id_desc"):
        self._person_sort_order = person_sort_order

    def readMergedConfig(self):
        return {
            "face_match": {
                "PERSON_SORT_ORDER": self._person_sort_order,
            },
            "photos": {
                "MAX_PHOTOS_PERSONS": 5000,
            },
        }


class DummySessionManager:
    def __init__(self, get_payloads=None, post_payloads=None):
        self.get_payloads = list(get_payloads or [])
        self.post_payloads = list(post_payloads or [])
        self.get_calls = []
        self.post_calls = []

    def call_api(self, **kwargs):
        self.get_calls.append(deepcopy(kwargs))
        if self.get_payloads:
            return self.get_payloads.pop(0)
        return {"success": True, "data": {"list": []}}

    def call_api_post(self, **kwargs):
        self.post_calls.append(deepcopy(kwargs))
        if self.post_payloads:
            return self.post_payloads.pop(0)
        return {"success": True, "data": {}}


class PhotosHandlerSortTests(unittest.TestCase):
    def setUp(self):
        self.persons = [
            {"id": 7, "name": ""},
            {"id": 2, "name": ""},
            {"id": 15, "name": ""},
        ]

    def test_sort_persons_for_face_match_descending_by_id_by_default(self):
        handler = PhotosHandler(session_manager=None, config_service=DummyConfigService("id_desc"))
        sorted_persons = handler.sortPersonsForFaceMatch(self.persons)
        self.assertEqual([person["id"] for person in sorted_persons], [15, 7, 2])

    def test_sort_persons_for_face_match_ascending_by_id(self):
        handler = PhotosHandler(session_manager=None, config_service=DummyConfigService("id_asc"))
        sorted_persons = handler.sortPersonsForFaceMatch(self.persons)
        self.assertEqual([person["id"] for person in sorted_persons], [2, 7, 15])

    def test_sort_persons_for_face_match_can_keep_original_order(self):
        handler = PhotosHandler(session_manager=None, config_service=DummyConfigService("none"))
        sorted_persons = handler.sortPersonsForFaceMatch(self.persons)
        self.assertEqual([person["id"] for person in sorted_persons], [7, 2, 15])

    def test_add_face_to_item_posts_expected_payload(self):
        session_manager = DummySessionManager(post_payloads=[{"success": True, "data": {"list": [{"face_id": 99, "face_id_temp": "42-0"}]}}])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        result = handler.addFaceToItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            id_item=42,
            face_bbox={
                "top_left": {"x": 0.1, "y": 0.2},
                "bottom_right": {"x": 0.3, "y": 0.4},
            },
            face_id_temp="42-0",
        )

        self.assertEqual(result.get("list")[0]["face_id"], 99)
        self.assertEqual(len(session_manager.post_calls), 1)
        params = session_manager.post_calls[0]["params"]
        self.assertEqual(params["method"], "add_face")
        self.assertEqual(params["version"], "3")
        self.assertEqual(params["id_item"], 42)
        self.assertEqual(params["face"][0]["face_id_temp"], "42-0")
        self.assertEqual(params["face"][0]["face_bounding_box"]["top_left"]["x"], 0.1)
        self.assertEqual(params["face"][0]["face_bounding_box"]["bottom_right"]["y"], 0.4)

    def test_add_face_to_item_includes_person_id_when_provided(self):
        session_manager = DummySessionManager(post_payloads=[{"success": True, "data": {"list": [{"face_id": 99, "face_id_temp": "42-0"}]}}])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        handler.addFaceToItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            id_item=42,
            face_bbox={
                "top_left": {"x": 0.1, "y": 0.2},
                "bottom_right": {"x": 0.3, "y": 0.4},
            },
            face_id_temp="42-0",
            person_id=91,
        )

        params = session_manager.post_calls[0]["params"]
        self.assertEqual(params["face"][0]["person_id"], 91)

    def test_find_item_by_path_resolves_photos_style_folder_keys_and_filename(self):
        session_manager = DummySessionManager(get_payloads=[
            {"success": True, "data": {"list": [{"id": 10, "name": "/trip"}]}},
            {"success": True, "data": {"list": [{"id": 11, "name": "/trip/day1"}]}},
            {"success": True, "data": {"list": [{"id": 77, "filename": "IMG_0001.JPG"}]}},
        ])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        item = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0001.JPG",
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["id"], 77)
        self.assertEqual(item["folder_id"], 11)
        self.assertEqual(session_manager.get_calls[0]["api"], "SYNO.FotoTeam.Browse.Folder")
        self.assertEqual(session_manager.get_calls[1]["params"]["id"], "10")
        self.assertEqual(session_manager.get_calls[2]["api"], "SYNO.FotoTeam.Browse.Item")
        self.assertEqual(session_manager.get_calls[2]["params"]["folder_id"], "11")

    def test_find_item_by_path_reuses_lookup_cache_for_same_folder(self):
        session_manager = DummySessionManager(get_payloads=[
            {"success": True, "data": {"list": [{"id": 10, "name": "/trip"}]}},
            {"success": True, "data": {"list": [{"id": 11, "name": "/trip/day1"}]}},
            {"success": True, "data": {"list": [
                {"id": 77, "filename": "IMG_0001.JPG"},
                {"id": 78, "filename": "IMG_0002.JPG"},
            ]}},
        ])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))
        cache = PhotosLookupCache()

        first = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0001.JPG",
            lookup_cache=cache,
        )
        second = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0002.JPG",
            lookup_cache=cache,
        )

        self.assertEqual(first["id"], 77)
        self.assertEqual(second["id"], 78)
        folder_calls = [call for call in session_manager.get_calls if call["api"] == "SYNO.FotoTeam.Browse.Folder"]
        item_calls = [call for call in session_manager.get_calls if call["api"] == "SYNO.FotoTeam.Browse.Item"]
        self.assertEqual(len(folder_calls), 2)
        self.assertEqual(len(item_calls), 1)

    def test_find_item_by_path_cache_handles_missing_file(self):
        session_manager = DummySessionManager(get_payloads=[
            {"success": True, "data": {"list": [{"id": 10, "name": "/trip"}]}},
            {"success": True, "data": {"list": [{"id": 11, "name": "/trip/day1"}]}},
            {"success": True, "data": {"list": [{"id": 77, "filename": "IMG_0001.JPG"}]}},
        ])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))
        cache = PhotosLookupCache()

        missing = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/MISSING.JPG",
            lookup_cache=cache,
        )
        existing = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0001.JPG",
            lookup_cache=cache,
        )

        self.assertIsNone(missing)
        self.assertEqual(existing["id"], 77)
        item_calls = [call for call in session_manager.get_calls if call["api"] == "SYNO.FotoTeam.Browse.Item"]
        self.assertEqual(len(item_calls), 1)

    def test_find_item_by_path_cache_is_not_global(self):
        handler = PhotosHandler(
            session_manager=DummySessionManager(get_payloads=[
                {"success": True, "data": {"list": [{"id": 10, "name": "/trip"}]}},
                {"success": True, "data": {"list": [{"id": 11, "name": "/trip/day1"}]}},
                {"success": True, "data": {"list": [{"id": 77, "filename": "IMG_0001.JPG"}]}},
                {"success": True, "data": {"list": [{"id": 10, "name": "/trip"}]}},
                {"success": True, "data": {"list": [{"id": 11, "name": "/trip/day1"}]}},
                {"success": True, "data": {"list": [{"id": 77, "filename": "IMG_0001.JPG"}]}},
            ]),
            config_service=DummyConfigService("id_desc"),
        )

        first = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0001.JPG",
            lookup_cache=PhotosLookupCache(),
        )
        second = handler.findFotoTeamItemByPath(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            image_path="/volume1/photo/trip/day1/IMG_0001.JPG",
            lookup_cache=PhotosLookupCache(),
        )

        self.assertEqual(first["id"], 77)
        self.assertEqual(second["id"], 77)
        self.assertEqual(len(handler._session_manager.get_calls), 6)


if __name__ == "__main__":
    unittest.main()
