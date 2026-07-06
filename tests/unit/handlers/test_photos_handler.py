#!/usr/bin/env python3
import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManagerError
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
            payload = self.post_payloads.pop(0)
            if isinstance(payload, Exception):
                raise payload
            return payload
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

    def test_person_status_counts_hidden_persons_separately(self):
        session_manager = DummySessionManager(get_payloads=[
            {"success": True, "data": {"list": [{"id": 1, "name": "Visible"}, {"id": 2, "name": ""}]}},
            {"success": True, "data": {"list": [{"id": 1, "name": "Visible"}, {"id": 2, "name": ""}, {"id": 3, "name": "Hidden"}, {"id": 4, "name": ""}]}},
        ])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        status = handler.person_status(user_key="user", cookies={}, base_url="https://example.test")

        self.assertEqual(status["total"], 4)
        self.assertEqual(status["known"], 2)
        self.assertEqual(status["unknown"], 2)
        self.assertEqual(status["visible_total"], 2)
        self.assertEqual(status["hidden_total"], 2)
        self.assertEqual(status["hidden_known"], 1)
        self.assertEqual(status["hidden_unknown"], 1)
        self.assertEqual(session_manager.get_calls[0]["params"]["show_hidden"], "false")
        self.assertEqual(session_manager.get_calls[1]["params"]["show_hidden"], "true")

    def test_person_status_background_returns_pending_without_synology_calls(self):
        session_manager = DummySessionManager()
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))
        handler.refresh_person_status_background = Mock(return_value=True)

        status = handler.person_status(user_key="user", cookies={}, base_url="https://example.test", background=True)

        self.assertEqual(status["total"], 0)
        self.assertTrue(status["cache_stale"])
        self.assertTrue(status["refreshing"])
        self.assertEqual(session_manager.get_calls, [])
        handler.refresh_person_status_background.assert_called_once()

    def test_person_status_uses_cache_without_refreshing(self):
        session_manager = DummySessionManager(get_payloads=[
            {"success": True, "data": {"list": [{"id": 1, "name": "Visible"}]}},
            {"success": True, "data": {"list": [{"id": 1, "name": "Visible"}]}},
        ])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        first = handler.person_status(user_key="user", cookies={}, base_url="https://example.test", force=True)
        second = handler.person_status(user_key="user", cookies={}, base_url="https://example.test", background=True)

        self.assertEqual(first["total"], 1)
        self.assertEqual(second["total"], 1)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(session_manager.get_calls), 2)

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

    def test_delete_face_posts_expected_payload(self):
        session_manager = DummySessionManager(post_payloads=[{"success": True, "data": {"deleted": True}}])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        result = handler.deleteFace(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=77,
        )

        self.assertEqual(result, {"deleted": True})
        self.assertEqual(len(session_manager.post_calls), 1)
        params = session_manager.post_calls[0]["params"]
        self.assertEqual(params["method"], "delete_face")
        self.assertEqual(params["version"], "1")
        self.assertEqual(params["face_id"], [77])

    def test_index_foto_team_paths_submits_basic_index_request_without_status_poll(self):
        session_manager = DummySessionManager(
            post_payloads=[{"success": True, "data": {"accepted": True}}]
        )
        handler = PhotosHandler(
            session_manager=session_manager,
            config_service=DummyConfigService("id_desc"),
        )

        result = handler.indexFotoTeamPaths(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            paths=["/volume1/photo/missing.jpg"],
        )

        self.assertEqual(result, {"accepted": True})
        self.assertEqual(len(session_manager.post_calls), 1)
        self.assertEqual(session_manager.get_calls, [])
        self.assertEqual(session_manager.post_calls[0]["api"], "SYNO.FotoTeam.Index")
        self.assertEqual(
            session_manager.post_calls[0]["params"],
            {
                "method": "index_add",
                "version": "1",
                "type": "basic",
                "paths": ["/volume1/photo/missing.jpg"],
            },
        )

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

    def test_assign_face_to_existing_person_posts_target_id_without_name(self):
        session_manager = DummySessionManager(post_payloads=[{"success": True, "data": {"ok": True}}])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        result = handler.assignFaceToPerson(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=146890,
            person_id=19785,
            person_name="Jelizaveta Vilippus geb. Kromskaja",
        )

        self.assertEqual(result, {"ok": True})
        params = session_manager.post_calls[0]["params"]
        self.assertEqual(params["method"], "separate")
        self.assertEqual(params["version"], "1")
        self.assertEqual(params["face_id"], [146890])
        self.assertEqual(params["target_id"], "19785")
        self.assertNotIn("name", params)

    def test_create_person_from_face_posts_name_without_target_id(self):
        session_manager = DummySessionManager(post_payloads=[{"success": True, "data": {"created": True}}])
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        result = handler.createPersonFromFace(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=146890,
            person_name="Jelizaveta Vilippus geb. Kromskaja",
        )

        self.assertEqual(result, {"created": True})
        params = session_manager.post_calls[0]["params"]
        self.assertEqual(params["method"], "separate")
        self.assertEqual(params["version"], "1")
        self.assertEqual(params["face_id"], [146890])
        self.assertEqual(params["name"], '"Jelizaveta Vilippus geb. Kromskaja"')
        self.assertNotIn("target_id", params)

    def test_find_known_person_by_name_treats_suggest_api_failure_as_no_match(self):
        session_manager = DummySessionManager(
            get_payloads=[{"success": True, "data": {"list": [{"id": 178, "name": "Andreas Vilippus"}]}}],
            post_payloads=[SessionManagerError({
                "error": "api_failed",
                "api": "SYNO.FotoTeam.Browse.Person",
                "response": {"success": False, "error": {"code": 902}},
            })],
        )
        handler = PhotosHandler(session_manager=session_manager, config_service=DummyConfigService("id_desc"))

        result = handler.findKnownPersonByName(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            name="Kaire Vilippus",
        )

        self.assertIsNone(result)
        self.assertEqual(len(session_manager.get_calls), 1)
        self.assertEqual(len(session_manager.post_calls), 1)

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
