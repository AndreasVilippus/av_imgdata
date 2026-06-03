#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager, SessionManagerError
from imgdata import ImgDataOperationError, ImgDataService
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload


class AutoApplyPersonOrchestrationCallerTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_findings_auto_apply_existing_photos_face_uses_existing_face_orchestration(self):
        entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/image.jpg",
            "face": {"face_id": 456, "item_id": 789, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [entry],
        }

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings),              patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]),              patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons),              patch.object(self.service, "_storedFaceMatchEntryExists", return_value=True),              patch.object(self.service, "_resolveStoredFaceMatchEntry", return_value=entry),              patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForExistingFace",
                 return_value={"updated": True, "operation": "photos_assign"},
             ) as orchestrate_mock,              patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock,              patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
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
            face_id=456,
            person_name="Alice",
            item_id=789,
            create_missing_person=False,
        )
        assign_mock.assert_not_called()
        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["entries"], [])
        self.assertEqual(persist_mock.call_args.kwargs["transferred_count"], 1)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["transferred_count"], 1)

    def test_findings_auto_apply_keeps_later_api_failure_after_checkpointing_success(self):
        first_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/first.jpg",
            "face": {"face_id": 456, "item_id": 789, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        second_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/second.jpg",
            "face": {"face_id": 457, "item_id": 790, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [first_entry, second_entry],
        }

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_storedFaceMatchEntryExists", return_value=True), \
             patch.object(self.service, "_resolveStoredFaceMatchEntry", side_effect=lambda **kwargs: kwargs["entry"]), \
             patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForExistingFace",
                 side_effect=[
                     {"updated": True, "operation": "photos_assign"},
                     SessionManagerError({
                         "error": "api_failed",
                         "api": "SYNO.FotoTeam.Browse.Person",
                         "response": {"success": False, "error": {"code": 117}},
                     }, status_code=502),
                 ],
             ), \
             patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["entries"], [second_entry])
        self.assertEqual(persist_mock.call_args.kwargs["transferred_count"], 1)
        self.assertEqual(result["entries"], [second_entry])
        self.assertEqual(result["transferred_count"], 1)

    def test_findings_auto_apply_persists_remapped_item_id_for_open_entry(self):
        entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/image.jpg",
            "image": {"id": 100},
            "face": {"face_id": 456},
        }
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "entries": [entry],
        }

        def remap_item_id(**kwargs):
            kwargs["entry"]["image"]["id"] = 200
            kwargs["entry"]["face"]["item_id"] = 200
            return True

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_storedFaceMatchEntryExists", side_effect=remap_item_id), \
             patch.object(self.service, "_resolveStoredFaceMatchEntry", side_effect=lambda **kwargs: kwargs["entry"]), \
             patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        persist_mock.assert_called_once()
        self.assertEqual(persist_mock.call_args.kwargs["entries"][0]["image"]["id"], 200)
        self.assertEqual(persist_mock.call_args.kwargs["entries"][0]["face"]["item_id"], 200)
        self.assertEqual(result["entries"][0]["image"]["id"], 200)
        self.assertEqual(result["entries"][0]["face"]["item_id"], 200)

    def test_findings_auto_apply_stops_at_unreadable_item_before_later_known_face(self):
        unreadable_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/unreadable.jpg",
            "image": {"id": 100},
            "face": {"face_id": 456, "item_id": 100, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        assignable_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/assignable.jpg",
            "image": {"id": 101},
            "face": {"face_id": 457, "item_id": 101, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [unreadable_entry, assignable_entry],
        }
        item_error = SessionManagerError({
            "error": "api_failed",
            "api": "SYNO.FotoTeam.Browse.Item",
            "response": {"success": False, "error": {"code": 117}},
        }, status_code=502)

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_storedFaceMatchEntryExists", side_effect=[item_error, True]), \
             patch.object(self.service, "_resolveStoredFaceMatchEntry", side_effect=lambda **kwargs: kwargs["entry"]), \
             patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForExistingFace",
                 return_value={"updated": True, "operation": "photos_assign"},
             ) as orchestrate_mock, \
             patch.object(self.service, "_persistFaceMatchFindingsEntries") as persist_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        orchestrate_mock.assert_not_called()
        persist_mock.assert_not_called()
        self.assertEqual(result["entries"], [unreadable_entry, assignable_entry])
        self.assertEqual(result["transferred_count"], 0)

    def test_findings_auto_apply_stops_at_first_unknown_before_later_known_face(self):
        unknown_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/unknown.jpg",
            "face": {"face_id": 456, "item_id": 100, "source_format": "PHOTOS"},
        }
        assignable_entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/assignable.jpg",
            "face": {"face_id": 457, "item_id": 101, "source_format": "PHOTOS"},
            "matched_person": {"id": 123, "name": "Alice"},
        }
        findings = {
            "status": "finished",
            "shared_folder": "/volume1/photo",
            "transferred_count": 0,
            "entries": [unknown_entry, assignable_entry],
        }

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_storedFaceMatchEntryExists", return_value=True), \
             patch.object(self.service, "_resolveStoredFaceMatchEntry", side_effect=lambda **kwargs: kwargs["entry"]), \
             patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForExistingFace",
                 return_value={"updated": True, "operation": "photos_assign"},
             ) as orchestrate_mock:
            result = self.service.getFaceMatchFindingEntries(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        orchestrate_mock.assert_not_called()
        self.assertEqual(result["entries"][0]["face"]["face_id"], 456)
        self.assertIsNone(result["entries"][0]["matched_person"])
        self.assertEqual(result["entries"][1], assignable_entry)
        progress = self.service.getFaceMatchingProgress("user")
        self.assertEqual(progress["message_key"], "face_match:progress_review_required")
        self.assertEqual(progress["entries_current"], 1)
        self.assertEqual(progress["entries_total"], 2)
        self.assertFalse(progress["running"])

    def test_findings_auto_apply_does_not_swallow_login_required_error(self):
        entry = {
            "action": "search_photo_face_in_file",
            "image_path": "/volume1/photo/image.jpg",
            "image": {"id": 100},
            "face": {"face_id": 456, "item_id": 100, "source_format": "PHOTOS"},
        }
        findings = {"entries": [entry]}
        login_error = SessionManagerError({
            "error": "api_failed",
            "api": "SYNO.FotoTeam.Browse.Item",
            "response": {"success": False, "error": {"code": 106}},
        }, status_code=401)

        with patch.object(self.service, "getFaceMatchFindings", return_value=findings), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_storedFaceMatchEntryExists", side_effect=login_error):
            with self.assertRaises(SessionManagerError):
                self.service.getFaceMatchFindingEntries(
                    user_key="user",
                    cookies={},
                    base_url="https://example.test",
                    auto=True,
                )

    def test_findings_auto_apply_lock_rejects_parallel_run(self):
        lock_key = "face_match:findings:auto:user"
        with self.service._writeOperationLock(lock_key, phase="test"):
            with self.assertRaises(ImgDataOperationError) as error:
                self.service.getFaceMatchFindingEntriesLocked(
                    user_key="user",
                    cookies={},
                    base_url="https://example.test",
                    auto=True,
                )

        self.assertEqual(error.exception.args[0], "write_conflict")

    def test_search_missing_photos_faces_auto_uses_metadata_orchestration(self):
        image_path = "/volume1/photo/image.jpg"
        target_face = MetadataFace.from_center_box(
            name="Alice",
            x=0.5,
            y=0.5,
            w=0.2,
            h=0.2,
            source="embedded_xmp_parsed",
            source_format="MWG_REGIONS",
        )
        payload = MetadataPayload(
            image_path=image_path,
            has_xmp=True,
            faces=[target_face],
            image_dimensions={"width": 1000, "height": 800, "unit": "pixel"},
        )

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"),              patch.object(self.service.files, "listImageFiles", return_value=[image_path]),              patch.object(self.service, "_readImageMetadata", return_value=payload),              patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0),              patch.object(self.service, "_shouldStopFaceMatching", return_value=False),              patch.object(self.service, "_setFaceMatchingProgressMessage"),              patch.object(self.service, "_setFaceMatchingProgress"),              patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 789}),              patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]),              patch.object(self.service, "_selectMissingPhotosFaceCandidate", return_value=(target_face, {"MWG_REGIONS": 1})),              patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]),              patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons),              patch.object(
                 self.service,
                 "_lookupMatchedPersonBySourceName",
                 return_value=({"id": 123, "name": "Alice"}, None, {}),
             ),              patch.object(
                 self.service,
                 "resolveOrCreatePhotosPersonForMetadataFace",
                 return_value={"updated": True, "operation": "photos_add_assign"},
             ) as orchestrate_mock,              patch.object(self.service, "addMatchedMetadataFaceToPhotos") as add_mock,              patch.object(self.service, "assignMatchedFaceToKnownPerson") as assign_mock:
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
            )

        orchestrate_mock.assert_called_once_with(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path=image_path,
            metadata_face=target_face.to_dict(),
            person_name="Alice",
            create_missing_person=False,
        )
        add_mock.assert_not_called()
        assign_mock.assert_not_called()
        self.assertTrue(result["searched"])
        self.assertEqual(result["transferred_count"], 1)

    def test_search_missing_photos_faces_save_only_auto_counts_only_unresolved_findings(self):
        image_path = "/volume1/photo/image.jpg"
        target_face = MetadataFace.from_center_box(
            name="Alice",
            x=0.5,
            y=0.5,
            w=0.2,
            h=0.2,
            source="embedded_xmp_parsed",
            source_format="MWG_REGIONS",
        )
        payload = MetadataPayload(
            image_path=image_path,
            has_xmp=True,
            faces=[target_face],
            image_dimensions={"width": 1000, "height": 800, "unit": "pixel"},
        )

        with patch.object(self.service.core, "getSharedFolder", return_value="/volume1/photo"), \
             patch.object(self.service.files, "listImageFiles", return_value=[image_path]), \
             patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service, "_refreshFaceMatchingSessionIfNeeded", return_value=0.0), \
             patch.object(self.service, "_shouldStopFaceMatching", return_value=False), \
             patch.object(self.service, "_setFaceMatchingProgressMessage"), \
             patch.object(self.service, "_setFaceMatchingProgress"), \
             patch.object(self.service.photos, "findFotoTeamItemByPath", return_value={"id": 789}), \
             patch.object(self.service.photos, "list_faceFotoTeamItems", return_value=[]), \
             patch.object(self.service, "_selectMissingPhotosFaceCandidate", return_value=(target_face, {"MWG_REGIONS": 1})), \
             patch.object(self.service.photos, "listFotoTeamPersonKnown", return_value=[]), \
             patch.object(self.service.photos, "sortPersonsForFaceMatch", side_effect=lambda persons: persons), \
             patch.object(self.service, "_lookupMatchedPersonBySourceName", return_value=({"id": 123, "name": "Alice"}, None, {})), \
             patch.object(self.service, "resolveOrCreatePhotosPersonForMetadataFace", return_value={"updated": True, "operation": "photos_add_assign"}), \
             patch.object(self.service, "_writeFaceMatchFindings") as write_findings_mock:
            result = self.service.searchMissingPhotosFaces(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                auto=True,
                save_only=True,
            )

        self.assertTrue(result["searched"])
        self.assertEqual(result["transferred_count"], 1)
        self.assertEqual(result["findings_count"], 0)
        write_findings_mock.assert_called_once()
        self.assertEqual(write_findings_mock.call_args.kwargs["entries"], [])


if __name__ == "__main__":
    unittest.main()
