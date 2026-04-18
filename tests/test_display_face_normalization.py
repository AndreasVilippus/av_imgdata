import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
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

if __name__ == "__main__":
    unittest.main()
