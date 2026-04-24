import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api import imgdata_api
from api.session_manager import SessionManager, SessionManagerError
from imgdata import ImgDataService
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from parser.metadata_parser import MetadataParser
from services.bbox_normalizer import to_display_face


XMP_MWG_AND_MICROSOFT = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:MP="http://ns.microsoft.com/photo/1.2/"
    xmlns:MPRI="http://ns.microsoft.com/photo/1.2/t/RegionInfo#"
    xmlns:MPReg="http://ns.microsoft.com/photo/1.2/t/Region#"
    xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"
    xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#">
   <MP:RegionInfo rdf:parseType="Resource">
    <MPRI:Regions>
     <rdf:Bag>
      <rdf:li
       MPReg:PersonDisplayName="Person Alpha"
       MPReg:Rectangle="0.746875, 0.331250, 0.196875, 0.261458"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
   <mwg-rs:Regions rdf:parseType="Resource">
    <mwg-rs:RegionList>
     <rdf:Bag>
      <rdf:li>
       <rdf:Description
        mwg-rs:Name="Person Alpha"
        mwg-rs:Type="Face">
        <mwg-rs:Area
         stArea:x="0.154412"
         stArea:y="0.537786"
         stArea:w="0.308824"
         stArea:h="0.435866"
         stArea:unit="normalized"/>
       </rdf:Description>
      </rdf:li>
     </rdf:Bag>
    </mwg-rs:RegionList>
   </mwg-rs:Regions>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""

XMP_ACD_UNNAMED = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:acdsee-rs="http://ns.acdsee.com/regions/"
    xmlns:acdsee-stArea="http://ns.acdsee.com/sType/Area#"
    acdsee-rs:Type="Face"
    acdsee-rs:NameAssignType="manual">
   <acdsee-rs:DLYArea
    acdsee-stArea:x="0.4"
    acdsee-stArea:y="0.3"
    acdsee-stArea:w="0.2"
    acdsee-stArea:h="0.25"/>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""

XMP_MICROSOFT_RENAME = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:MP="http://ns.microsoft.com/photo/1.2/"
    xmlns:MPRI="http://ns.microsoft.com/photo/1.2/t/RegionInfo#"
    xmlns:MPReg="http://ns.microsoft.com/photo/1.2/t/Region#">
   <MP:RegionInfo rdf:parseType="Resource">
    <MPRI:Regions>
     <rdf:Bag>
      <rdf:li
       MPReg:PersonDisplayName="Person Legacy"
       MPReg:Rectangle="0.1, 0.2, 0.3, 0.4"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""

XMP_POSITION_REPLACE_ORIENTED = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
    xmlns:MP="http://ns.microsoft.com/photo/1.2/"
    xmlns:MPRI="http://ns.microsoft.com/photo/1.2/t/RegionInfo#"
    xmlns:MPReg="http://ns.microsoft.com/photo/1.2/t/Region#"
    xmlns:acdsee-rs="http://ns.acdsee.com/regions/"
    xmlns:acdsee-stArea="http://ns.acdsee.com/sType/Area#">
   <tiff:Orientation>6</tiff:Orientation>
   <MP:RegionInfo rdf:parseType="Resource">
    <MPRI:Regions>
     <rdf:Bag>
      <rdf:li
       MPReg:PersonDisplayName="Person Alpha"
       MPReg:Rectangle="0.531444,0.1304015,0.198945,0.180806"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
   <acdsee-rs:Regions>
    <rdf:Seq>
     <rdf:li>
      <rdf:Description
       acdsee-rs:Type="Face"
       acdsee-rs:Name="Person Alpha"
       acdsee-rs:NameAssignType="manual">
       <acdsee-rs:DLYArea
        acdsee-stArea:x="0.630916"
        acdsee-stArea:y="0.220804"
        acdsee-stArea:w="0.198945"
        acdsee-stArea:h="0.180806"/>
      </rdf:Description>
     </rdf:li>
    </rdf:Seq>
   </acdsee-rs:Regions>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


class DisplayFaceNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.parser = MetadataParser()
        self.service = ImgDataService(SessionManager())

    def test_to_display_face_normalizes_oriented_mwg_face_and_adds_bbox(self):
        payload = self.parser.parse(
            image_path="dev/test.jpg",
            xmp_content=XMP_MWG_AND_MICROSOFT,
            image_orientation=6,
            use_acd=False,
            use_microsoft=False,
            use_mwg_regions=True,
        )

        self.assertEqual(len(payload.faces), 1)
        face = to_display_face(payload.faces[0])

        self.assertTrue(face.get("display_normalized"))
        self.assertAlmostEqual(face["x"], 0.462214)
        self.assertAlmostEqual(face["y"], 0.154412)
        self.assertAlmostEqual(face["w"], 0.435866)
        self.assertAlmostEqual(face["h"], 0.308824)
        self.assertAlmostEqual(face["bbox"]["y1"], 0.0, places=6)

    def test_to_display_face_is_idempotent(self):
        payload = self.parser.parse(
            image_path="dev/test.jpg",
            xmp_content=XMP_MWG_AND_MICROSOFT,
            image_orientation=6,
            use_acd=False,
            use_microsoft=True,
            use_mwg_regions=False,
        )

        once = to_display_face(payload.faces[0])
        twice = to_display_face(once)

        self.assertEqual(once, twice)

    def test_parser_can_optionally_include_unnamed_acd_faces(self):
        default_payload = self.parser.parse(
            image_path="dev/test.jpg",
            xmp_content=XMP_ACD_UNNAMED,
            image_orientation=1,
            use_acd=True,
            use_microsoft=False,
            use_mwg_regions=False,
        )
        extended_payload = self.parser.parse(
            image_path="dev/test.jpg",
            xmp_content=XMP_ACD_UNNAMED,
            image_orientation=1,
            use_acd=True,
            use_microsoft=False,
            use_mwg_regions=False,
            include_unnamed_acd=True,
        )

        self.assertEqual(len(default_payload.faces), 0)
        self.assertEqual(len(extended_payload.faces), 1)
        self.assertEqual(extended_payload.faces[0].source_format, "ACD")
        self.assertEqual(extended_payload.faces[0].name, "")

    def test_search_missing_photos_faces_skips_existing_unknown_photos_face(self):
        metadata_face = MetadataFace.from_center_box(
            name="Person Candidate",
            x=0.373492,
            y=0.369883,
            w=0.13295,
            h=0.176901,
            source="embedded_xmp_exiftool",
            source_format="MWG_REGIONS",
        )
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: ["/volume1/photo/2011/2011.01 - Amsterdam - KickOff/CIMG4917.JPG"]
        self.service._readImageMetadata = lambda image_path, include_unnamed_acd=False: MetadataPayload(
            image_path=image_path,
            faces=[metadata_face],
        )
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 92877}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: [
            {
                "face_id": 85793,
                "face_name": "",
                "person_id": 2970,
                "bbox": {
                    "top_left": {"x": 0.42799001562888678, "y": 0.33412106037139894},
                    "bottom_right": {"x": 0.62816962230498841, "y": 0.60102720260620113},
                },
            },
            {
                "face_id": 85794,
                "face_name": "",
                "person_id": 16835,
                "bbox": {
                    "top_left": {"x": 0.26341613459182051, "y": 0.22684593200683595},
                    "bottom_right": {"x": 0.45473087954116126, "y": 0.48193225860595701},
                },
            },
        ]

        result = self.service.searchMissingPhotosFaces(
            user_key="user",
            cookies={},
            base_url="https://example.test",
        )

        self.assertTrue(result.get("searched"))
        self.assertIsNone(result.get("image_path"))
        self.assertIsNone(result.get("metadata_face"))

    def test_add_matched_metadata_face_to_photos_forwards_person_id(self):
        metadata_face = {
            "name": "Person Target",
            "x": 0.6254395,
            "y": 0.428125,
            "w": 0.073857,
            "h": 0.05,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }
        captured = {}
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 35535}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: []

        def fake_add_face(**kwargs):
            captured.update(kwargs)
            return {"list": [{"face_id": 107256, "face_id_temp": kwargs["face_id_temp"]}]}

        self.service.photos.addFaceToItem = fake_add_face

        result = self.service.addMatchedMetadataFaceToPhotos(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/generic-event/generic-photo-100.JPG",
            metadata_face=metadata_face,
            person_id=91,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["face_id"], 107256)
        self.assertEqual(captured["person_id"], 91)

    def test_cleanup_targets_exclude_photos(self):
        self.assertEqual(
            self.service._normalizeCleanupTargets(["PHOTOS", "ACD", "MICROSOFT", "MWG_REGIONS"]),
            ["ACD", "MICROSOFT", "MWG_REGIONS"],
        )

    def test_cleanup_name_normalization_never_touches_photos_persons(self):
        self.service.name_mappings.readNameMappings = lambda: [
            {"source_name": "Person Legacy", "target_name": "Person Target"},
        ]

        calls = {"photos_list": 0, "metadata_normalize": 0}

        def fail_if_photos_listed(**kwargs):
            calls["photos_list"] += 1
            raise AssertionError("Photos cleanup path must not run")

        self.service.photos.listFotoTeamPersonKnown = fail_if_photos_listed

        def track_metadata_normalization(**kwargs):
            calls["metadata_normalize"] += 1
            return {"updated": False, "updated_faces": 0, "formats": {}}

        self.service.normalizeMetadataFaceNamesFromMappings = track_metadata_normalization
        self.service.exiftool_handler.isAvailable = lambda: True
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: []

        self.service._runCleanupNameNormalization(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            action="normalize_names",
            targets=["PHOTOS"],
        )

        progress = self.service.getCleanupProgress("user", "normalize_names")
        self.assertFalse(progress.get("running"))
        self.assertTrue(progress.get("finished"))
        self.assertEqual(progress.get("targets"), [])
        self.assertEqual(calls["photos_list"], 0)
        self.assertEqual(calls["metadata_normalize"], 0)

    def test_face_signature_keeps_photos_face_id(self):
        photo_face = self.service._metadataFaceFromPhotoFace(
            {
                "face_id": 1234,
                "person_id": 77,
                "face_name": "Person Alpha",
                "bbox": {
                    "top_left": {"x": 0.1, "y": 0.2},
                    "bottom_right": {"x": 0.3, "y": 0.4},
                },
            }
        )

        signature = self.service._faceSignature(photo_face)

        self.assertEqual(signature["face_id"], 1234)
        self.assertEqual(signature["person_id"], 77)

    def test_get_cleanup_progress_clears_stale_running_state_without_worker(self):
        written = {}
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: {
            "action": "normalize_names",
            "running": True,
            "finished": False,
            "targets": ["ACD"],
        }
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True

        progress = self.service.getCleanupProgress("user", "normalize_names")

        self.assertFalse(progress.get("running"))
        self.assertTrue(progress.get("finished"))
        self.assertEqual(progress.get("message"), "Last cleanup job is no longer running.")
        self.assertEqual(written.get("state_type"), "cleanup_progress")
        self.assertEqual(written.get("state_key"), "user_normalize_names")
        self.assertFalse(written.get("payload", {}).get("running"))

    def test_replace_checks_face_name_reassigns_photos_face_using_name_mapping(self):
        captured = {}

        def fake_find_known_person(**kwargs):
            captured["lookup_name"] = kwargs["name"]
            return {"id": 91, "name": "Person Target"}

        def fake_assign(**kwargs):
            captured["assign"] = kwargs
            return {"success": True}

        self.service.name_mappings.findNameMapping = lambda name: {"source_name": "Alias Target", "target_name": "Person Target"} if name == "Alias Target" else None
        self.service.photos.findKnownPersonByName = fake_find_known_person
        self.service.photos.assignFaceToPerson = fake_assign

        result = self.service.replaceChecksFaceName(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/test.jpg",
            face_data={
                "face_id": 555,
                "source": "photos",
                "source_format": "PHOTOS",
                "name": "Person Legacy",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            new_name="Alias Target",
        )

        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_assign")
        self.assertEqual(captured["lookup_name"], "Person Target")
        self.assertEqual(captured["assign"]["face_id"], 555)
        self.assertEqual(captured["assign"]["person_id"], 91)
        self.assertEqual(captured["assign"]["person_name"], "Person Target")

    def test_replace_checks_face_name_reports_missing_target_person_for_photos(self):
        self.service.name_mappings.findNameMapping = lambda name: None
        self.service.photos.findKnownPersonByName = lambda **kwargs: None

        result = self.service.replaceChecksFaceName(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/test.jpg",
            face_data={
                "face_id": 555,
                "source": "photos",
                "source_format": "PHOTOS",
                "name": "Person Legacy",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            new_name="Missing Person",
        )

        self.assertFalse(result["updated"])
        self.assertEqual(result["warning"], "checks:warning_target_person_not_found")
        self.assertEqual(result["details"]["requested_name"], "Missing Person")

    def test_replace_checks_face_name_marks_metadata_write_operation(self):
        self.service.replaceMetadataFaceName = lambda **kwargs: {
            "updated": True,
            "warning": "",
            "target_path": kwargs["image_path"],
        }

        result = self.service.replaceChecksFaceName(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/test.jpg",
            face_data={
                "source": "metadata",
                "source_format": "ACD",
                "name": "Person Legacy",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            new_name="Person Target",
        )

        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "metadata_write")

    def test_search_next_checks_item_save_only_applies_suggested_name_changes(self):
        captured = {}

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = lambda **kwargs: [
            {"review_type": "name_conflicts", "image_path": kwargs["image_path"], "entry_id": "remaining"}
        ] if captured.get("refreshed") else [
            {"review_type": "name_conflicts", "image_path": kwargs["image_path"], "entry_id": "initial"}
        ]
        self.service._resolveChecksReviewEntry = lambda **kwargs: captured.update({
            "entry": kwargs["entry"],
            "auto_apply_suggested_names": kwargs["auto_apply_suggested_names"],
            "auto_apply_suggested_duplicates": kwargs["auto_apply_suggested_duplicates"],
            "refreshed": True,
        }) or {
            "entry": None,
            "item": None,
            "auto_applied_count": 1,
        }
        self.service._writeChecksFindings = lambda **kwargs: captured.update({"saved_findings": kwargs}) or True

        result = self.service.searchNextChecksItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            check_type="name_conflicts",
            save_only=True,
            auto_apply_suggested_names=True,
        )

        self.assertTrue(captured["auto_apply_suggested_names"])
        self.assertFalse(captured["auto_apply_suggested_duplicates"])
        self.assertEqual(result["save_only"], True)
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(captured["saved_findings"]["entries"][0]["entry_id"], "remaining")

    def test_search_next_checks_item_save_only_applies_suggested_duplicate_changes(self):
        captured = {}

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = lambda **kwargs: [] if captured.get("resolved") else [
            {"review_type": "duplicate_faces", "image_path": kwargs["image_path"], "entry_id": "initial"}
        ]
        self.service._resolveChecksReviewEntry = lambda **kwargs: captured.update({
            "auto_apply_suggested_names": kwargs["auto_apply_suggested_names"],
            "auto_apply_suggested_duplicates": kwargs["auto_apply_suggested_duplicates"],
            "resolved": True,
        }) or {
            "entry": None,
            "item": None,
            "auto_applied_count": 1,
        }
        self.service._writeChecksFindings = lambda **kwargs: captured.update({"saved_findings": kwargs}) or True

        result = self.service.searchNextChecksItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            check_type="duplicate_faces",
            save_only=True,
            auto_apply_suggested_duplicates=True,
        )

        self.assertFalse(captured["auto_apply_suggested_names"])
        self.assertTrue(captured["auto_apply_suggested_duplicates"])
        self.assertEqual(result["save_only"], True)
        self.assertEqual(result["findings_count"], 0)
        self.assertEqual(captured["saved_findings"]["entries"], [])

    def test_run_checks_thread_preserves_latest_progress_on_session_error(self):
        self.service._setChecksProgress(
            "user",
            check_type="name_conflicts",
            source_mode="scan",
            running=True,
            finished=False,
            stop_requested=False,
            files_scanned=945,
            total_files=40798,
            findings_count=12,
            current_path="/volume1/photo/tests/test.jpg",
            resume_cursor={
                "check_type": "name_conflicts",
                "path_index": 944,
                "pending_entries": [],
                "save_only": False,
                "source_mode": "scan",
                "findings_count": 12,
            },
        )

        self.service.searchNextChecksItem = lambda **kwargs: (_ for _ in ()).throw(
            SessionManagerError({"error": "resume_failed"})
        )

        self.service._runChecksScan(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            check_type="name_conflicts",
            save_only=False,
        )

        progress = self.service.getChecksProgress("user", "name_conflicts")
        self.assertFalse(progress["running"])
        self.assertFalse(progress["finished"])
        self.assertEqual(progress["error"], "session manager error")
        self.assertEqual(progress["files_scanned"], 945)
        self.assertEqual(progress["findings_count"], 12)
        self.assertEqual(progress["current_path"], "/volume1/photo/tests/test.jpg")
        self.assertEqual(progress["resume_cursor"]["path_index"], 944)
        self.assertEqual(progress["resume_cursor"]["findings_count"], 12)

    def test_checks_replace_metadata_face_name_returns_success_when_refresh_fails(self):
        async def run_test():
            async def fake_prepare_session_request(request):
                return {
                    "user_key": "user",
                    "cookies": {"_SSID": "sid"},
                    "base_url": "https://example.test",
                }, None

            async def fake_read_request_body(request):
                return {
                    "image_path": "/volume1/photo/tests/test.jpg",
                    "face": {
                        "face_id": 77,
                        "name": "Person Legacy",
                        "source_format": "PHOTOS",
                    },
                    "new_name": "Person Target",
                    "save_mapping": False,
                    "source_name": "Person Legacy",
                }

            with patch.object(imgdata_api, "_prepare_session_request", fake_prepare_session_request), \
                 patch.object(imgdata_api, "_read_request_body", fake_read_request_body), \
                 patch.object(
                     imgdata_api.IMGDATA,
                     "replaceChecksFaceName",
                     lambda **kwargs: {
                         "updated": True,
                         "warning": "",
                         "operation": "photos_assign",
                         "resolved_name": "Person Target",
                         "target_person": {"id": 42, "name": "Person Target"},
                     },
                 ), \
                 patch.object(
                     imgdata_api,
                     "_refresh_checks_mutation_state",
                     side_effect=SessionManagerError({"error": "resume_failed"}),
                 ):
                response = await imgdata_api.checks_replace_metadata_face_name(object())
                payload = json.loads(response.body.decode("utf-8"))
                self.assertTrue(payload["success"])
                self.assertTrue(payload["data"]["updated"])
                self.assertIsNone(payload["data"]["findings_update"])
                self.assertEqual(payload["data"]["refresh_error"]["message"], "session_manager_error")

        asyncio.run(run_test())

    def test_resolve_checks_review_entry_auto_applies_suggested_photos_name_change(self):
        item = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_name": "Person Target",
            "right_name": "Person Legacy",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": {
                "source": "embedded_xmp_exiftool",
                "source_format": "ACD",
                "name": "Person Target",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            "right_face_target": {
                "source": "photos",
                "source_format": "PHOTOS",
                "face_id": 77,
                "name": "Person Legacy",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
        }
        captured = {}

        with patch.object(self.service, "getChecksReviewItem", side_effect=[item]), \
             patch.object(self.service, "replaceChecksFaceName", side_effect=lambda **kwargs: captured.update(kwargs) or {
                 "updated": True,
                 "operation": "photos_assign",
             }), \
             patch.object(self.service, "_buildCheckEntriesForType", return_value=[]):
            result = self.service._resolveChecksReviewEntry(
                entry={"review_type": "name_conflicts", "image_path": "/volume1/photo/tests/test.jpg"},
                auto_apply_suggested_names=True,
                user_key="user",
                cookies={"_SSID": "session"},
                base_url="https://example.test",
            )

        self.assertIsNone(result["entry"])
        self.assertIsNone(result["item"])
        self.assertEqual(result["auto_applied_count"], 1)
        self.assertEqual(captured["user_key"], "user")
        self.assertEqual(captured["cookies"], {"_SSID": "session"})
        self.assertEqual(captured["base_url"], "https://example.test")
        self.assertEqual(captured["new_name"], "Person Target")
        self.assertEqual(captured["face_data"]["source_format"], "PHOTOS")
        self.assertEqual(captured["face_data"]["face_id"], 77)

    def test_orientation_risk_fallback_prefers_non_risky_side(self):
        risky_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        safe_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="metadata",
            source_format="ACD",
        )

        left_state, right_state = self.service._applyOrientationRiskSuggestion(
            left_state="alert",
            right_state="alert",
            left_face=risky_face,
            right_face=safe_face,
        )

        self.assertEqual((left_state, right_state), ("alert", "suggested"))

    def test_orientation_risk_fallback_does_not_override_existing_suggestion(self):
        risky_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        safe_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="metadata",
            source_format="ACD",
        )

        left_state, right_state = self.service._applyOrientationRiskSuggestion(
            left_state="suggested",
            right_state="alert",
            left_face=risky_face,
            right_face=safe_face,
        )

        self.assertEqual((left_state, right_state), ("suggested", "alert"))

    def test_position_deviation_review_item_stays_neutral_even_with_orientation_risk(self):
        risky_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        safe_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="metadata",
            source_format="ACD",
        )
        payload = MetadataPayload(image_path="dev/test.jpg", faces=[safe_face, risky_face])
        entry = self.service._buildCheckEntry(
            review_type="position_deviations",
            image_path="dev/test.jpg",
            face_name="Person Alpha",
            left_face=safe_face,
            right_face=risky_face,
        )

        with patch.object(self.service, "_readImageMetadata", return_value=payload):
            item = self.service._buildPositionDeviationReviewItem(
                image_path="dev/test.jpg",
                entry=entry,
            )

        self.assertEqual(item["left_state"], "alert")
        self.assertEqual(item["right_state"], "alert")

    def test_position_deviation_review_item_prefers_configured_single_source_of_truth(self):
        embedded_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="embedded_xmp_exiftool",
            source_format="ACD",
        )
        sidecar_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="xmp_file",
            source_format="MWG_REGIONS",
        )
        payload = MetadataPayload(image_path="dev/test.jpg", faces=[embedded_face, sidecar_face])
        entry = self.service._buildCheckEntry(
            review_type="position_deviations",
            image_path="dev/test.jpg",
            face_name="Person Alpha",
            left_face=embedded_face,
            right_face=sidecar_face,
        )
        self.service.config.readMergedConfig = lambda: {
            "analysis": {
                "CHECKS": {
                    "SINGLE_SOURCE_OF_TRUTH": "metadata:mwg_regions:sidecar",
                },
            },
        }

        with patch.object(self.service, "_readImageMetadata", return_value=payload):
            item = self.service._buildPositionDeviationReviewItem(
                image_path="dev/test.jpg",
                entry=entry,
            )

        self.assertEqual(item["left_state"], "alert")
        self.assertEqual(item["right_state"], "suggested")

    def test_normalize_metadata_face_names_from_mappings_updates_selected_formats(self):
        payload = MetadataPayload(image_path="dev/test.jpg", has_xmp=True)
        written = {}

        def capture_write(_target_path, xmp_content):
            written["xmp"] = xmp_content
            return {"updated": True}

        with patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", return_value=XMP_MICROSOFT_RENAME), \
             patch.object(self.service.exiftool_handler, "writeXmpDetailed", side_effect=capture_write):
            result = self.service.normalizeMetadataFaceNamesFromMappings(
                image_path="dev/test.jpg",
                target_formats=["MICROSOFT"],
                mapping_lookup={"person legacy": "Person Target"},
            )

        self.assertTrue(result["updated"])
        self.assertEqual(result["updated_faces"], 1)
        self.assertEqual(result["formats"], {"MICROSOFT": 1})
        self.assertIn("Person Target", written["xmp"])
        self.assertNotIn("Person Legacy", written["xmp"])

    def test_normalize_metadata_face_names_from_mappings_requires_exiftool(self):
        with patch.object(self.service.exiftool_handler, "isAvailable", return_value=False):
            result = self.service.normalizeMetadataFaceNamesFromMappings(
                image_path="dev/test.jpg",
                target_formats=["MICROSOFT"],
                mapping_lookup={"person legacy": "Person Target"},
            )

        self.assertFalse(result["updated"])
        self.assertEqual(result["warning"], "checks:warning_exiftool_required")

    def test_normalize_metadata_face_names_from_mappings_stops_before_write(self):
        payload = MetadataPayload(image_path="dev/test.jpg", has_xmp=True)

        with patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", return_value=XMP_MICROSOFT_RENAME), \
             patch.object(self.service.exiftool_handler, "writeXmpDetailed") as write_mock:
            result = self.service.normalizeMetadataFaceNamesFromMappings(
                image_path="dev/test.jpg",
                target_formats=["MICROSOFT"],
                mapping_lookup={"person legacy": "Person Target"},
                should_stop=lambda: True,
            )

        self.assertFalse(result["updated"])
        self.assertTrue(result["stopped"])
        write_mock.assert_not_called()

    def test_duplicate_support_prefers_safe_reinforcement_when_totals_tie(self):
        mwg_bottom = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        mwg_top = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.154412,
            y=0.537786,
            w=0.308824,
            h=0.435866,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        acd_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="metadata",
            source_format="ACD",
        )
        microsoft_face = MetadataFace.from_top_left_box(
            name="Person Alpha",
            left=0.746875,
            top=0.33125,
            w=0.196875,
            h=0.261458,
            source="metadata",
            source_format="MICROSOFT",
            orientation=6,
        )

        bottom_stats = self.service._duplicateSuggestionSupportStats(
            mwg_bottom,
            [mwg_bottom, mwg_top, acd_face, microsoft_face],
        )
        top_stats = self.service._duplicateSuggestionSupportStats(
            mwg_top,
            [mwg_bottom, mwg_top, acd_face, microsoft_face],
        )

        self.assertEqual(bottom_stats, (1, 0))
        self.assertEqual(top_stats, (1, 1))

    def test_duplicate_suggestion_prefers_larger_face_when_it_fully_contains_smaller_face(self):
        larger_face = MetadataFace.from_top_left_box(
            name="Person Target",
            left=0.2,
            top=0.2,
            w=0.3,
            h=0.3,
            source="metadata",
            source_format="ACD",
        )
        smaller_face = MetadataFace.from_top_left_box(
            name="Person Target",
            left=0.25,
            top=0.25,
            w=0.1,
            h=0.1,
            source="metadata",
            source_format="MICROSOFT",
        )

        left_state, right_state = self.service._getDuplicateSuggestionStates(
            left_face=larger_face,
            right_face=smaller_face,
            faces=[larger_face, smaller_face],
        )

        self.assertEqual((left_state, right_state), ("suggested", "alert"))

    def test_duplicate_review_prefers_configured_single_source_of_truth(self):
        embedded_face = MetadataFace.from_top_left_box(
            name="Person Target",
            left=0.2,
            top=0.2,
            w=0.3,
            h=0.3,
            source="embedded_xmp_exiftool",
            source_format="ACD",
        )
        sidecar_face = MetadataFace.from_top_left_box(
            name="Person Target",
            left=0.25,
            top=0.25,
            w=0.1,
            h=0.1,
            source="xmp_file",
            source_format="MICROSOFT",
        )
        payload = MetadataPayload(image_path="dev/test.jpg", faces=[embedded_face, sidecar_face])
        entry = self.service._buildCheckEntry(
            review_type="duplicate_faces",
            image_path="dev/test.jpg",
            face_name="Person Target",
            left_face=embedded_face,
            right_face=sidecar_face,
        )
        self.service.config.readMergedConfig = lambda: {
            "analysis": {
                "CHECKS": {
                    "SINGLE_SOURCE_OF_TRUTH": "metadata:microsoft:sidecar",
                },
            },
        }

        with patch.object(self.service, "_readImageMetadata", return_value=payload):
            item = self.service.getChecksReviewItem(
                entry=entry,
                user_key="user",
                cookies={},
                base_url="",
                shared_folder="",
            )

        self.assertEqual(item["left_state"], "alert")
        self.assertEqual(item["right_state"], "suggested")

    def test_name_conflict_prefers_configured_single_source_of_truth_over_mapping(self):
        photos_face = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.45,
            y=0.45,
            w=0.2,
            h=0.2,
            source="photos",
            source_format="PHOTOS",
        )
        embedded_face = MetadataFace.from_center_box(
            name="Person Beta",
            x=0.45,
            y=0.45,
            w=0.2,
            h=0.2,
            source="embedded_xmp_exiftool",
            source_format="ACD",
        )
        self.service.name_mappings.findNameMapping = lambda name: (
            {"target_name": "Person Alpha"} if name == "Person Beta" else None
        )
        self.service.config.readMergedConfig = lambda: {
            "analysis": {
                "CHECKS": {
                    "SINGLE_SOURCE_OF_TRUTH": "photos",
                },
            },
        }

        left_state, right_state = self.service._getNameConflictSuggestionStates(
            "Person Alpha",
            "Person Beta",
            left_face=photos_face,
            right_face=embedded_face,
        )

        self.assertEqual((left_state, right_state), ("suggested", "alert"))

    def test_single_source_of_truth_can_match_specific_metadata_format_and_any_location(self):
        embedded_microsoft = MetadataFace.from_center_box(
            name="Person Alpha",
            x=0.4,
            y=0.4,
            w=0.2,
            h=0.2,
            source="embedded_xmp_exiftool",
            source_format="MICROSOFT",
        )
        sidecar_acd = MetadataFace.from_center_box(
            name="Person Beta",
            x=0.4,
            y=0.4,
            w=0.2,
            h=0.2,
            source="xmp_file",
            source_format="ACD",
        )
        self.service.config.readMergedConfig = lambda: {
            "analysis": {
                "CHECKS": {
                    "SINGLE_SOURCE_OF_TRUTH": "metadata:microsoft:any",
                },
            },
        }

        left_state, right_state = self.service._getNameConflictSuggestionStates(
            "Person Alpha",
            "Person Beta",
            left_face=embedded_microsoft,
            right_face=sidecar_acd,
        )

        self.assertEqual((left_state, right_state), ("suggested", "alert"))

    def test_replace_metadata_face_position_denormalizes_for_oriented_microsoft_target(self):
        payload = MetadataPayload(image_path="dev/test.jpg", has_xmp=True)
        written = {}

        def capture_write(_target_path, xmp_content):
            written["xmp"] = xmp_content
            return {"updated": True}

        with patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", return_value=XMP_POSITION_REPLACE_ORIENTED), \
             patch.object(self.service.exiftool_handler, "writeXmpDetailed", side_effect=capture_write):
            result = self.service.replaceMetadataFacePosition(
                image_path="dev/test.jpg",
                face_data={
                    "name": "Person Alpha",
                    "x": 0.6309165,
                    "y": 0.220804,
                    "w": 0.198945,
                    "h": 0.180806,
                    "source": "embedded_xmp_exiftool",
                    "source_format": "MICROSOFT",
                    "orientation": 6,
                },
                source_face_data={
                    "name": "Person Alpha",
                    "x": 0.630916,
                    "y": 0.220804,
                    "w": 0.198945,
                    "h": 0.180806,
                    "source": "embedded_xmp_exiftool",
                    "source_format": "ACD",
                },
            )

        self.assertTrue(result["updated"])
        self.assertIn('Rectangle="0.130401,0.269611,0.180806,0.198945"', written["xmp"])

    def test_stored_reverse_face_match_entry_reads_unnamed_acd_targets(self):
        unnamed_face = MetadataFace.from_center_box(
            name="",
            x=0.4,
            y=0.3,
            w=0.2,
            h=0.25,
            source="metadata",
            source_format="ACD",
        )
        payload = MetadataPayload(
            image_path="dev/test.jpg",
            has_xmp=True,
            faces=[unnamed_face],
        )
        captured_flags = []

        def fake_read(image_path, *, include_unnamed_acd=False):
            captured_flags.append(include_unnamed_acd)
            return payload

        with patch.object(self.service, "_readImageMetadata", side_effect=fake_read):
            exists = self.service._storedFaceMatchEntryExists(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                entry={
                    "action": "search_file_face_in_sources",
                    "image_path": "dev/test.jpg",
                    "metadata_face": unnamed_face.to_dict(),
                },
                image_faces_cache={},
            )

        self.assertTrue(exists)
        self.assertEqual(captured_flags, [True])

    def test_build_checks_scan_payload_keeps_resume_cursor_in_sync(self):
        payload = self.service._buildChecksScanPayload(
            check_type="name_conflicts",
            save_only=False,
            files_scanned=3,
            total_files=10,
            findings_count=4,
            path_index=3,
            pending_entries=[{"image_path": "photo/test.jpg"}],
            current_path="photo/test.jpg",
            result={"entry": {"image_path": "photo/test.jpg"}, "item": {"review_type": "name_conflicts"}},
            message_key="checks:progress_result_found",
            message="Check finding found.",
            message_params={"count": 4},
        )

        self.assertEqual(payload["source_mode"], "scan")
        self.assertEqual(payload["check_type"], "name_conflicts")
        self.assertEqual(payload["findings_count"], 4)
        self.assertEqual(payload["resume_cursor"]["path_index"], 3)
        self.assertEqual(payload["resume_cursor"]["findings_count"], 4)
        self.assertEqual(payload["resume_cursor"]["pending_entries"], [{"image_path": "photo/test.jpg"}])

    def test_load_photo_faces_for_image_with_override_replaces_matching_face(self):
        original_face = MetadataFace.from_center_box(
            name="Person Legacy",
            x=0.45,
            y=0.45,
            w=0.2,
            h=0.2,
            source="photos",
            source_format="PHOTOS",
        )
        original_face.face_id = 77
        original_face.person_id = 11
        untouched_face = MetadataFace.from_center_box(
            name="Person Other",
            x=0.2,
            y=0.2,
            w=0.1,
            h=0.1,
            source="photos",
            source_format="PHOTOS",
        )
        replacement_face_data = original_face.to_dict()
        original_face_data = original_face.to_dict()
        original_face_data["face_id"] = 77
        original_face_data["person_id"] = 11
        replacement_face_data["face_id"] = 77
        replacement_face_data["name"] = "Person Current"
        replacement_face_data["person_id"] = 42

        with patch.object(self.service, "_loadPhotoFacesForImage", return_value=[original_face, untouched_face]):
            faces = self.service._loadPhotoFacesForImageWithOverride(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                shared_folder="photo",
                image_path="photo/test.jpg",
                original_face_data=original_face_data,
                replacement_face_data=replacement_face_data,
            )

        self.assertEqual([face.name for face in faces], ["Person Current", "Person Other"])
        self.assertEqual(self.service._faceSignature(faces[0]).get("face_id"), 77)
        self.assertEqual(self.service._faceSignature(faces[0]).get("person_id"), 42)

    def test_checks_replace_metadata_face_name_route_forwards_photos_override(self):
        face = {
            "name": "Person Legacy",
            "x": 0.45,
            "y": 0.45,
            "w": 0.2,
            "h": 0.2,
            "source": "photos",
            "source_format": "PHOTOS",
            "face_id": 77,
            "person_id": 11,
        }

        async def fake_prepare(_request):
            return ({"user_key": "user", "cookies": {}, "base_url": "http://example.test"}, None)

        async def fake_body(_request):
            return {
                "image_path": "photo/test.jpg",
                "face": face,
                "new_name": "Person Current",
            }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(imgdata_api.IMGDATA, "replaceChecksFaceName", return_value={
                 "updated": True,
                 "operation": "photos_assign",
                 "resolved_name": "Person Current",
                 "target_person": {"id": 42},
             }), \
             patch.object(imgdata_api, "_refresh_checks_mutation_state", return_value={"entries": []}) as refresh_mock:
            response = asyncio.run(imgdata_api.checks_replace_metadata_face_name(None))

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        kwargs = refresh_mock.call_args.kwargs
        self.assertEqual(kwargs["check_type"], "name_conflicts")
        self.assertEqual(kwargs["image_path"], "photo/test.jpg")
        self.assertEqual(kwargs["original_face_data"]["name"], "Person Legacy")
        self.assertEqual(kwargs["replacement_face_data"]["name"], "Person Current")
        self.assertEqual(kwargs["replacement_face_data"]["person_id"], 42)

    def test_checks_replace_metadata_face_position_route_refreshes_without_override(self):
        face = {
            "name": "Person Legacy",
            "x": 0.45,
            "y": 0.45,
            "w": 0.2,
            "h": 0.2,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }
        source_face = {
            "name": "Person Legacy",
            "x": 0.5,
            "y": 0.5,
            "w": 0.2,
            "h": 0.2,
            "source": "photos",
            "source_format": "PHOTOS",
        }

        async def fake_prepare(_request):
            return ({"user_key": "user", "cookies": {}, "base_url": "http://example.test"}, None)

        async def fake_body(_request):
            return {
                "image_path": "photo/test.jpg",
                "face": face,
                "source_face": source_face,
                "review_type": "position_deviations",
            }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(imgdata_api.IMGDATA, "replaceMetadataFacePosition", return_value={"updated": True}), \
             patch.object(imgdata_api, "_refresh_checks_mutation_state", return_value={"entries": []}) as refresh_mock:
            response = asyncio.run(imgdata_api.checks_replace_metadata_face_position(None))

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        kwargs = refresh_mock.call_args.kwargs
        self.assertEqual(kwargs["check_type"], "position_deviations")
        self.assertEqual(kwargs["image_path"], "photo/test.jpg")
        self.assertNotIn("original_face_data", kwargs)
        self.assertNotIn("replacement_face_data", kwargs)

    def test_checks_assign_face_person_route_forwards_photos_override(self):
        face = {
            "name": "Person Legacy",
            "x": 0.45,
            "y": 0.45,
            "w": 0.2,
            "h": 0.2,
            "source": "photos",
            "source_format": "PHOTOS",
            "face_id": 77,
            "person_id": 11,
        }

        async def fake_prepare(_request):
            return ({"user_key": "user", "cookies": {}, "base_url": "http://example.test"}, None)

        async def fake_body(_request):
            return {
                "image_path": "photo/test.jpg",
                "face": face,
                "review_type": "duplicate_faces",
                "person_id": 42,
                "person_name": "Person Current",
            }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(imgdata_api.IMGDATA, "assignChecksFaceToKnownPerson", return_value={"updated": True}), \
             patch.object(imgdata_api, "_refresh_checks_mutation_state", return_value={"entries": []}) as refresh_mock:
            response = asyncio.run(imgdata_api.checks_assign_face_person(None))

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        kwargs = refresh_mock.call_args.kwargs
        self.assertEqual(kwargs["check_type"], "duplicate_faces")
        self.assertEqual(kwargs["image_path"], "photo/test.jpg")
        self.assertEqual(kwargs["original_face_data"]["person_id"], 11)
        self.assertEqual(kwargs["replacement_face_data"]["name"], "Person Current")
        self.assertEqual(kwargs["replacement_face_data"]["person_id"], 42)

    def test_start_checks_review_findings_returns_only_stored_entries(self):
        stored_entries = [
            {"review_type": "name_conflicts", "image_path": "photo/a.jpg"},
            {"review_type": "name_conflicts", "image_path": "photo/b.jpg"},
        ]
        with patch.object(self.service, "getChecksFindingEntries", return_value={
            "save_only": True,
            "entries": stored_entries,
        }):
            result = self.service.startChecksReview(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                source_mode="findings",
                check_type="name_conflicts",
            )

        self.assertEqual(result["check_type"], "name_conflicts")
        self.assertEqual(result["source_mode"], "findings")
        self.assertTrue(result["save_only"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["entries"], stored_entries)

if __name__ == "__main__":
    unittest.main()
