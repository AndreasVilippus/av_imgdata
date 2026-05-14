import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath("src"))

from api import imgdata_api
from api.session_manager import SessionManager, SessionManagerError
from imgdata import ImgDataOperationError, ImgDataService
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from parser.metadata_parser import MetadataParser
from services.config_service import ConfigService


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

    def test_load_xmp_from_image_parsed_accepts_nonstandard_namespace_prefix(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            path = handle.name
            handle.write(b"prefix")
            handle.write(
                b'<ns0:xmpmeta xmlns:ns0="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"></rdf:RDF></ns0:xmpmeta>'
            )
            handle.write(b"suffix")
        try:
            parsed = self.service.files.loadXmpFromImageParsed(path)
        finally:
            os.unlink(path)

        self.assertIn("<ns0:xmpmeta", parsed or "")
        self.assertIn("</ns0:xmpmeta>", parsed or "")

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

    def test_search_missing_photos_faces_keeps_second_face_for_same_person_on_photo(self):
        metadata_face = MetadataFace.from_center_box(
            name="Person Target",
            x=0.6254395,
            y=0.428125,
            w=0.073857,
            h=0.05,
            source="embedded_xmp_exiftool",
            source_format="MICROSOFT",
        )
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: ["/volume1/photo/tests/generic-event/generic-photo-100.JPG"]
        self.service._readImageMetadata = lambda image_path, include_unnamed_acd=False: MetadataPayload(
            image_path=image_path,
            faces=[metadata_face],
        )
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 35535, "filename": "generic-photo-100.JPG"}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: [{
            "face_id": 8001,
            "face_name": "Person Target",
            "person_id": 91,
            "bbox": {
                "top_left": {"x": 0.1, "y": 0.1},
                "bottom_right": {"x": 0.2, "y": 0.2},
            },
        }]
        self.service.photos.listFotoTeamPersonKnown = lambda **kwargs: [{"id": 91, "name": "Person Target"}]
        self.service.photos.sortPersonsForFaceMatch = lambda persons: persons
        self.service._lookupMatchedPersonBySourceName = lambda **kwargs: ({"id": 91, "name": "Person Target"}, None, {})

        result = self.service.searchMissingPhotosFaces(
            user_key="user",
            cookies={},
            base_url="https://example.test",
        )

        self.assertTrue(result.get("searched"))
        self.assertEqual(result.get("action"), "mark_missing_photos_faces")
        self.assertEqual(result.get("image_path"), "/volume1/photo/tests/generic-event/generic-photo-100.JPG")
        self.assertTrue(result.get("add_new_faces_to_photos"))
        self.assertEqual(result.get("matched_person_id"), 91)
        self.assertEqual(result.get("source_name"), "Person Target")

    def test_search_photo_face_in_file_save_only_persists_found_match(self):
        metadata_face = MetadataFace.from_center_box(
            name="Person Known",
            x=0.15,
            y=0.15,
            w=0.10,
            h=0.10,
            source="embedded_xmp_parsed",
            source_format="MICROSOFT",
        )
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.sortPersonsForFaceMatch = lambda persons: persons
        self.service.photos.listFotoTeamPersonUnknown = lambda **kwargs: [{"id": 111}]
        self.service.photos.listFotoTeamItems = lambda **kwargs: [{
            "id": 222,
            "folder_id": 333,
            "filename": "test.jpg",
        }]
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: [{
            "face_id": 444,
            "face_name": "",
            "person_id": 111,
            "bbox": {
                "top_left": {"x": 0.10, "y": 0.10},
                "bottom_right": {"x": 0.20, "y": 0.20},
            },
        }]
        self.service.photos.getFotoTeamFolder = lambda **kwargs: {"folder": {"name": "tests"}}
        self.service._readImageMetadata = lambda image_path: MetadataPayload(
            image_path=image_path,
            faces=[metadata_face],
        )
        self.service.face_matcher.match = lambda photo_faces, file_faces: [{
            "file_face_index": 0,
            "file_name": "Person Known",
        }]
        self.service.photos.listFotoTeamPersonKnown = lambda **kwargs: [{"id": 555, "name": "Person Known"}]
        self.service.photos.findKnownPersonByName = lambda **kwargs: {"id": 555, "name": "Person Known"}
        self.service.photos.debugKnownPersonLookup = lambda **kwargs: {}
        self.service.file_analysis.writeCheckFindings = Mock()

        result = self.service.searchPhotoFaceInFile(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            save_only=True,
        )

        self.assertTrue(result["searched"])
        self.assertTrue(result["save_only"])
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(self.service.getFaceMatchingProgress("user")["findings_count"], 1)
        self.assertGreaterEqual(self.service.file_analysis.writeCheckFindings.call_count, 2)
        first_finding_type, first_payload = self.service.file_analysis.writeCheckFindings.call_args_list[0].args
        self.assertEqual(first_finding_type, "face_match")
        self.assertEqual(first_payload["status"], "running")
        self.assertEqual(first_payload["finished_at"], "")
        self.assertEqual(first_payload["count"], 1)
        finding_type, payload = self.service.file_analysis.writeCheckFindings.call_args.args
        self.assertEqual(finding_type, "face_match")
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["matched_person_id"], 555)
        self.assertEqual(payload["entries"][0]["image_path"], "/volume1/photo/tests/test.jpg")

    def test_search_photo_face_in_file_save_only_stop_persists_partial_findings(self):
        metadata_face = MetadataFace.from_center_box(
            name="Person Known",
            x=0.15,
            y=0.15,
            w=0.10,
            h=0.10,
            source="embedded_xmp_parsed",
            source_format="MICROSOFT",
        )
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.sortPersonsForFaceMatch = lambda persons: persons
        self.service.photos.listFotoTeamPersonUnknown = lambda **kwargs: [{"id": 111}, {"id": 112}]
        self.service.photos.listFotoTeamItems = lambda **kwargs: [{
            "id": 222,
            "folder_id": 333,
            "filename": "test.jpg",
        }]
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: [{
            "face_id": 444,
            "face_name": "",
            "person_id": 111,
            "bbox": {
                "top_left": {"x": 0.10, "y": 0.10},
                "bottom_right": {"x": 0.20, "y": 0.20},
            },
        }]
        self.service.photos.getFotoTeamFolder = lambda **kwargs: {"folder": {"name": "tests"}}
        self.service._readImageMetadata = lambda image_path: MetadataPayload(
            image_path=image_path,
            faces=[metadata_face],
        )
        self.service.face_matcher.match = lambda photo_faces, file_faces: [{
            "file_face_index": 0,
            "file_name": "Person Known",
        }]
        self.service.photos.listFotoTeamPersonKnown = lambda **kwargs: [{"id": 555, "name": "Person Known"}]
        self.service.photos.findKnownPersonByName = lambda **kwargs: {"id": 555, "name": "Person Known"}
        self.service.photos.debugKnownPersonLookup = lambda **kwargs: {}
        self.service.file_analysis.writeCheckFindings = Mock()

        with patch.object(self.service, "_shouldStopFaceMatching", side_effect=[False, False, False, True]):
            result = self.service.searchPhotoFaceInFile(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                save_only=True,
            )

        self.assertTrue(result["stopped"])
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(self.service.getFaceMatchingProgress("user")["findings_count"], 1)
        self.assertGreaterEqual(self.service.file_analysis.writeCheckFindings.call_count, 2)
        first_finding_type, first_payload = self.service.file_analysis.writeCheckFindings.call_args_list[0].args
        self.assertEqual(first_finding_type, "face_match")
        self.assertEqual(first_payload["status"], "running")
        self.assertEqual(first_payload["finished_at"], "")
        self.assertEqual(first_payload["count"], 1)
        finding_type, payload = self.service.file_analysis.writeCheckFindings.call_args.args
        self.assertEqual(finding_type, "face_match")
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["matched_person_id"], 555)

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
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[
            [],
            [{
                "face_id": 107256,
                "face_name": "Person Target",
                "person_id": 91,
                "bbox": {
                    "top_left": {"x": 0.1, "y": 0.2},
                    "bottom_right": {"x": 0.2, "y": 0.3},
                },
            }],
        ])

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
        self.assertEqual(self.service.photos.list_faceFotoTeamItems.call_count, 2)

    def test_add_matched_metadata_face_to_photos_allows_second_face_for_same_person_on_same_item(self):
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
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[
            [{
                "face_id": 8001,
                "face_name": "Person Target",
                "person_id": 91,
                "bbox": {
                    "top_left": {"x": 0.1, "y": 0.1},
                    "bottom_right": {"x": 0.2, "y": 0.2},
                },
            }],
            [{
                "face_id": 8001,
                "face_name": "Person Target",
                "person_id": 91,
                "bbox": {
                    "top_left": {"x": 0.1, "y": 0.1},
                    "bottom_right": {"x": 0.2, "y": 0.2},
                },
            }, {
                "face_id": 107256,
                "face_name": "Person Target",
                "person_id": 91,
                "bbox": {
                    "top_left": {"x": 0.58, "y": 0.40},
                    "bottom_right": {"x": 0.66, "y": 0.45},
                },
            }],
        ])

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
        self.assertEqual(self.service.photos.list_faceFotoTeamItems.call_count, 2)

    def test_add_matched_metadata_face_to_photos_reports_missing_created_face(self):
        metadata_face = {
            "name": "Person Target",
            "x": 0.6254395,
            "y": 0.428125,
            "w": 0.073857,
            "h": 0.05,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 35535}
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[[], []])
        self.service.photos.addFaceToItem = lambda **kwargs: {
            "list": [{"face_id": 107256, "face_id_temp": kwargs["face_id_temp"]}],
        }

        with self.assertRaises(ImgDataOperationError) as context:
            self.service.addMatchedMetadataFaceToPhotos(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                image_path="/volume1/photo/tests/generic-event/generic-photo-100.JPG",
                metadata_face=metadata_face,
                person_id=91,
            )

        self.assertEqual(context.exception.details["code"], "photos_face_changed_during_operation")
        self.assertEqual(context.exception.details["reason"], "photos_face_missing")
        self.assertEqual(context.exception.details["phase"], "photos_face_create_postcheck")
        self.assertEqual(context.exception.details["item_id"], 35535)
        self.assertEqual(context.exception.details["face_id"], 107256)

    def test_add_matched_metadata_face_to_photos_recovers_face_id_from_postcheck_when_add_result_is_empty(self):
        metadata_face = {
            "name": "Person Target",
            "x": 0.6254395,
            "y": 0.428125,
            "w": 0.073857,
            "h": 0.05,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 35535}
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[
            [],
            [{
                "face_id": 107256,
                "face_name": "",
                "person_id": 0,
                "bbox": {
                    "top_left": {"x": 0.588511, "y": 0.403125},
                    "bottom_right": {"x": 0.662368, "y": 0.453125},
                },
            }],
            [{
                "face_id": 107256,
                "face_name": "",
                "person_id": 0,
                "bbox": {
                    "top_left": {"x": 0.588511, "y": 0.403125},
                    "bottom_right": {"x": 0.662368, "y": 0.453125},
                },
            }],
        ])
        self.service.photos.addFaceToItem = lambda **kwargs: {"list": []}

        result = self.service.addMatchedMetadataFaceToPhotos(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/generic-event/generic-photo-100.JPG",
            metadata_face=metadata_face,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["face_id"], 107256)
        self.assertEqual(self.service.photos.list_faceFotoTeamItems.call_count, 3)

    def test_assign_matched_face_validates_photos_person_after_write_when_item_known(self):
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[
            [{"face_id": 555, "person_id": 17, "bbox": {}}],
            [{"face_id": 555, "person_id": 17, "bbox": {}}],
        ])
        self.service.photos.assignFaceToPerson = lambda **kwargs: {"success": True}

        with self.assertRaises(ImgDataOperationError) as context:
            self.service.assignMatchedFaceToKnownPerson(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                face_id=555,
                person_id=91,
                person_name="Person Target",
                item_id=35535,
                image_path="/volume1/photo/tests/generic-event/generic-photo-100.JPG",
            )

        self.assertEqual(context.exception.details["code"], "photos_face_changed_during_operation")
        self.assertEqual(context.exception.details["reason"], "photos_face_person_mismatch")
        self.assertEqual(context.exception.details["phase"], "photos_face_assign_postcheck")
        self.assertEqual(context.exception.details["person_id"], 91)

    def test_create_matched_face_as_person_derives_person_id_from_postcheck_face(self):
        self.service.photos.createPersonFromFace = lambda **kwargs: {}
        self.service.photos.findKnownPersonByName = Mock()
        self.service.photos.list_faceFotoTeamItems = Mock(side_effect=[
            [{"face_id": 107256, "person_id": 0, "bbox": {}}],
            [{"face_id": 107256, "person_id": 91, "bbox": {}}],
        ])

        result = self.service.createMatchedFaceAsPerson(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            face_id=107256,
            person_name="Person Target",
            item_id=35535,
            image_path="/volume1/photo/tests/generic-event/generic-photo-100.JPG",
        )

        self.assertEqual(result["person_id"], 91)
        self.service.photos.findKnownPersonByName.assert_not_called()

    def test_face_create_metadata_match_route_returns_operation_details(self):
        metadata_face = {
            "name": "Person Target",
            "x": 0.6254395,
            "y": 0.428125,
            "w": 0.073857,
            "h": 0.05,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }

        async def fake_prepare(_request):
            return ({"user_key": "user", "cookies": {}, "base_url": "http://example.test"}, None)

        async def fake_body(_request):
            return {
                "image_path": "photo/test.jpg",
                "metadata_face": metadata_face,
                "person_name": "Person Target",
            }

        detail = {
            "reason": "photos_face_create_failed",
            "image_path": "photo/test.jpg",
            "item_id": 35535,
            "person_id": None,
            "person_name_required_in_photos": False,
            "metadata_face_name": "Person Target",
            "metadata_face_source_format": "MICROSOFT",
            "face_id_temp": "35535-123456",
            "add_result": {"list": []},
        }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(
                 imgdata_api.IMGDATA,
                 "addMatchedMetadataFaceToPhotos",
                 side_effect=ImgDataOperationError("photos_face_create_failed", detail),
             ):
            payload = asyncio.run(imgdata_api.face_create_metadata_match(None))

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["message"], "face_create_metadata_match_failed")
        self.assertEqual(payload["error"]["details"], detail)

    def test_face_create_metadata_match_route_returns_person_id(self):
        metadata_face = {
            "name": "Person Target",
            "x": 0.6254395,
            "y": 0.428125,
            "w": 0.073857,
            "h": 0.05,
            "source": "embedded_xmp_exiftool",
            "source_format": "MICROSOFT",
        }

        async def fake_prepare(_request):
            return ({"user_key": "user", "cookies": {}, "base_url": "http://example.test"}, None)

        async def fake_body(_request):
            return {
                "image_path": "photo/test.jpg",
                "metadata_face": metadata_face,
                "person_name": "Person Target",
            }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(
                 imgdata_api.IMGDATA,
                 "addMatchedMetadataFaceToPhotos",
                 return_value={"face_id": 107256, "item_id": 35535},
             ), \
             patch.object(
                 imgdata_api.IMGDATA,
                 "createMatchedFaceAsPerson",
                 return_value={"person_id": 91},
             ), \
             patch.object(
                 imgdata_api.IMGDATA,
                 "removeFaceMatchFindingMetadataEntry",
                 return_value={"removed": True},
             ):
            payload = asyncio.run(imgdata_api.face_create_metadata_match(None))

        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["person_id"], 91)

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

    def test_checks_conflict_token_ignores_name_and_source_noise(self):
        entry_a = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "ACD",
                "name": "Kaire Vilippus",
                "x": 0.460801,
                "y": 0.688777,
                "w": 0.275065,
                "h": 0.594169,
            },
            "right_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "MWG_REGIONS",
                "name": "Andreas Vilippus",
                "x": 0.483776,
                "y": 0.603067,
                "w": 0.377395,
                "h": 0.791537,
            },
        }
        entry_b = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {
                "source": "metadata",
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.4837760001,
                "y": 0.6030670001,
                "w": 0.3773950001,
                "h": 0.7915370001,
            },
            "right_face_signature": {
                "source": "metadata",
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.4608010001,
                "y": 0.6887770001,
                "w": 0.2750650001,
                "h": 0.5941690001,
            },
        }

        self.assertEqual(
            self.service._checksConflictToken(entry_a),
            self.service._checksConflictToken(entry_b),
        )

    def test_get_cleanup_progress_preserves_persisted_running_state_without_local_worker(self):
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

        self.assertTrue(progress.get("running"))
        self.assertFalse(progress.get("finished"))
        self.assertEqual(progress.get("targets"), ["ACD"])
        self.assertEqual(written, {})

    def test_get_checks_progress_preserves_persisted_running_scan_without_local_worker(self):
        written = {}
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: {
            "check_type": "name_conflicts",
            "running": True,
            "finished": False,
            "source_mode": "scan",
            "files_scanned": 945,
            "total_files": 1572,
            "current_path": "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
        }
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True

        progress = self.service.getChecksProgress("user", "name_conflicts")

        self.assertTrue(progress.get("running"))
        self.assertFalse(progress.get("finished"))
        self.assertEqual(progress.get("source_mode"), "scan")
        self.assertEqual(progress.get("files_scanned"), 945)
        self.assertEqual(written, {})

    def test_get_face_matching_progress_preserves_persisted_running_state_without_local_worker(self):
        written = {}
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: {
            "operation_id": "face_match-existing",
            "running": True,
            "finished": False,
            "action": "search_photo_face_in_file",
            "findings_count": 7,
            "resume_cursor": {
                "skip_face_ids": [123],
                "transferred_count": 2,
                "auto": False,
                "save_only": False,
                "action": "search_photo_face_in_file",
                "findings_count": 7,
            },
        }
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True

        progress = self.service.getFaceMatchingProgress("user")

        self.assertTrue(progress.get("running"))
        self.assertFalse(progress.get("finished"))
        self.assertFalse(progress.get("stop_requested"))
        self.assertTrue(progress.get("active"))
        self.assertFalse(progress.get("stale"))
        self.assertEqual(progress.get("findings_count"), 7)
        self.assertEqual(written, {})

    def test_face_matching_progress_syncs_counts_from_resume_cursor(self):
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: {}
        self.service.file_analysis.writeRuntimeState = Mock()

        self.service._setFaceMatchingProgress(
            "user",
            action="mark_missing_photos_faces",
            findings_count=37,
            transferred_count=61,
            resume_cursor={
                "action": "mark_missing_photos_faces",
                "findings_count": 65,
                "transferred_count": 61,
                "skip_targets": ["target-a"],
            },
        )
        self.service._setFaceMatchingProgress(
            "user",
            message="Face transferred.",
            transferred_count=61,
            resume_cursor={
                "action": "mark_missing_photos_faces",
                "findings_count": 65,
                "transferred_count": 61,
                "skip_targets": ["target-a"],
            },
        )

        progress = self.service.getFaceMatchingProgress("user")

        self.assertEqual(progress["findings_count"], 65)
        self.assertEqual(progress["transferred_count"], 61)

    def test_get_file_analysis_progress_preserves_persisted_running_state_without_local_worker(self):
        written = {}
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: {
            "operation_id": "file_analysis-existing",
            "job_id": "20260426000000",
            "running": True,
            "finished": False,
            "stopped": False,
            "status": "running",
            "phase": "analysis",
            "files_analyzed": 12,
            "files_matched_total": 40,
            "analysis_progress": {"current": 12, "total": 40},
        }
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True
        self.service.file_analysis.readLatestResult = lambda: {}

        progress = self.service.getFileAnalysisProgress()

        self.assertTrue(progress.get("running"))
        self.assertFalse(progress.get("finished"))
        self.assertFalse(progress.get("stopped"))
        self.assertEqual(progress.get("status"), "running")
        self.assertEqual(progress.get("files_analyzed"), 12)
        self.assertEqual(written, {})

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

    def test_replace_checks_face_name_can_create_missing_photos_person(self):
        captured = {}
        self.service.name_mappings.findNameMapping = lambda name: None
        self.service.photos.findKnownPersonByName = lambda **kwargs: None

        def fake_create(**kwargs):
            captured.update(kwargs)
            return {"person_id": 91}

        self.service.createMatchedFaceAsPerson = fake_create

        result = self.service.replaceChecksFaceName(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            image_path="/volume1/photo/tests/test.jpg",
            face_data={
                "face_id": 555,
                "item_id": 123,
                "source": "photos",
                "source_format": "PHOTOS",
                "name": "Person Legacy",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            new_name="Missing Person",
            create_missing_person=True,
        )

        self.assertTrue(result["updated"])
        self.assertEqual(result["operation"], "photos_create")
        self.assertEqual(result["target_person"]["id"], 91)
        self.assertEqual(result["target_person"]["name"], "Missing Person")
        self.assertEqual(captured["face_id"], 555)
        self.assertEqual(captured["item_id"], 123)
        self.assertEqual(captured["person_name"], "Missing Person")

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
            {"review_type": "name_conflicts", "image_path": kwargs["image_path"], "entry_id": "initial"},
            {"review_type": "name_conflicts", "image_path": kwargs["image_path"], "entry_id": "remaining"}
        ]
        self.service._resolveChecksReviewEntry = lambda **kwargs: captured.update({
            "entry": kwargs["entry"],
            "auto_apply_suggested_names": kwargs["auto_apply_suggested_names"],
            "auto_apply_suggested_duplicates": kwargs["auto_apply_suggested_duplicates"],
        }) or {
            "entry": None,
            "item": None,
            "auto_applied_count": 1,
            "processed_entry_tokens": [],
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

    def test_search_next_checks_item_save_only_saves_warning_findings_and_continues(self):
        captured = {}
        paths = [
            "/volume1/photo/tests/first.jpg",
            "/volume1/photo/tests/second.jpg",
        ]

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: paths
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = lambda **kwargs: [
            {
                "review_type": "name_conflicts",
                "image_path": kwargs["image_path"],
                "entry_id": Path(kwargs["image_path"]).stem,
            }
        ]

        def resolve_entry(**kwargs):
            if kwargs["entry"]["entry_id"] == "first":
                return {
                    "entry": kwargs["entry"],
                    "item": None,
                    "auto_applied_count": 0,
                    "auto_apply_warning": "checks:warning_exiftool_required",
                }
            return {
                "entry": kwargs["entry"],
                "item": None,
                "auto_applied_count": 0,
            }

        self.service._resolveChecksReviewEntry = resolve_entry
        self.service._writeChecksFindings = lambda **kwargs: captured.update({"saved_findings": kwargs}) or True

        result = self.service.searchNextChecksItem(
            user_key="user",
            cookies={},
            base_url="https://example.test",
            check_type="name_conflicts",
            save_only=True,
            auto_apply_suggested_names=True,
        )

        self.assertTrue(result["finished"])
        self.assertEqual(result["files_scanned"], 2)
        self.assertEqual(result["total_files"], 2)
        self.assertEqual(result["findings_count"], 2)
        self.assertEqual(
            [entry["entry_id"] for entry in captured["saved_findings"]["entries"]],
            ["first", "second"],
        )

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

    def test_search_next_checks_item_scan_returns_entry_without_resolving_item_when_no_auto_apply(self):
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = lambda **kwargs: [
            {"review_type": "name_conflicts", "image_path": kwargs["image_path"], "entry_id": "initial"}
        ]

        with patch.object(self.service, "getChecksReviewItem", side_effect=AssertionError("must not resolve item during scan")):
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                auto_apply_suggested_names=False,
                auto_apply_suggested_duplicates=False,
            )

        self.assertFalse(result["running"])
        self.assertTrue(result["finished"])
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["result"]["entry"]["entry_id"], "initial")
        self.assertIsNone(result["result"]["item"])

    def test_search_next_checks_item_resume_returns_pending_entry_without_resolving_item_when_no_auto_apply(self):
        resume_cursor = {
            "check_type": "name_conflicts",
            "path_index": 945,
            "pending_entries": [
                {
                    "review_type": "name_conflicts",
                    "image_path": "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
                    "entry_id": "remaining",
                    "face_name": "Andreas Vilippus",
                }
            ],
            "save_only": False,
            "source_mode": "scan",
            "findings_count": 1,
        }
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: [
            f"/volume1/photo/tests/{index:04d}.jpg" for index in range(1000)
        ]

        with patch.object(self.service, "getChecksReviewItem", side_effect=AssertionError("must not resolve item during resume")):
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                resume_cursor=resume_cursor,
                auto_apply_suggested_names=False,
                auto_apply_suggested_duplicates=False,
            )

        self.assertFalse(result["running"])
        self.assertTrue(result["finished"])
        self.assertEqual(result["files_scanned"], 945)
        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["resume_cursor"]["path_index"], 945)
        self.assertEqual(result["resume_cursor"]["pending_entries"], [])
        self.assertEqual(result["result"]["entry"]["entry_id"], "remaining")
        self.assertIsNone(result["result"]["item"])

    def test_search_next_checks_item_auto_apply_name_conflict_uses_rebuilt_image_queue(self):
        image_path = "/volume1/photo/tests/test.jpg"
        initial_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "initial",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        flipped_same_pair = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "flipped",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Kaire Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Andreas Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        remaining_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "remaining",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Person Remaining",
                "x": 0.11,
                "y": 0.22,
                "w": 0.10,
                "h": 0.10,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Person Other",
                "x": 0.31,
                "y": 0.42,
                "w": 0.12,
                "h": 0.14,
            },
        }
        initial_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "left_name": "Andreas Vilippus",
            "right_name": "Kaire Vilippus",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(initial_entry["left_face_signature"]),
            "right_face_target": dict(initial_entry["right_face_signature"]),
        }
        remaining_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "remaining-item",
        }

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: [image_path]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = Mock(side_effect=[
            [initial_entry, flipped_same_pair, remaining_entry],
        ])

        with patch.object(self.service, "getChecksReviewItem", side_effect=[initial_item]) as review_mock, \
             patch.object(self.service, "replaceChecksFaceName", return_value={"updated": True, "operation": "metadata_write"}):
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                auto_apply_suggested_names=True,
                auto_apply_suggested_duplicates=False,
            )

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["result"]["entry"]["entry_id"], "remaining")
        self.assertIsNone(result["result"]["item"])
        self.assertEqual(result["resume_cursor"]["pending_entries"], [])
        self.assertEqual(self.service._buildCheckEntriesForType.call_count, 1)
        self.assertEqual(review_mock.call_count, 1)

    def test_search_next_checks_item_auto_applies_rebuilt_suggested_name_conflicts(self):
        image_path = "/volume1/photo/tests/test.jpg"
        first_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "first",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        second_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "second",
            "left_face_signature": {
                "source_format": "MICROSOFT",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        first_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "left_name": "Andreas Vilippus",
            "right_name": "Kaire Vilippus",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(first_entry["left_face_signature"]),
            "right_face_target": dict(first_entry["right_face_signature"]),
        }
        second_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "left_name": "Andreas Vilippus",
            "right_name": "Kaire Vilippus",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(second_entry["left_face_signature"]),
            "right_face_target": dict(second_entry["right_face_signature"]),
        }

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: [image_path]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = Mock(side_effect=[
            [first_entry, second_entry],
        ])

        with patch.object(self.service, "getChecksReviewItem", side_effect=[first_item]) as review_mock, \
             patch.object(self.service, "replaceChecksFaceName", return_value={"updated": True, "operation": "metadata_write"}) as replace_mock:
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                auto_apply_suggested_names=True,
                auto_apply_suggested_duplicates=False,
            )

        self.assertEqual(replace_mock.call_count, 1)
        self.assertEqual(result["resolved_count"], 1)
        self.assertEqual(result["result"]["entry"]["entry_id"], "second")
        self.assertIsNone(result["result"]["item"])
        self.assertEqual(self.service._buildCheckEntriesForType.call_count, 1)
        self.assertEqual(review_mock.call_count, 1)

    def test_resolve_checks_review_entry_respects_auto_apply_limit(self):
        image_path = "/volume1/photo/tests/test.jpg"
        first_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "first",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        second_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "second",
            "left_face_signature": {
                "source_format": "MICROSOFT",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        first_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "left_name": "Andreas Vilippus",
            "right_name": "Kaire Vilippus",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(first_entry["left_face_signature"]),
            "right_face_target": dict(first_entry["right_face_signature"]),
        }

        with patch.object(self.service, "getChecksReviewItem", return_value=first_item), \
             patch.object(self.service, "replaceChecksFaceName", return_value={"updated": True, "operation": "metadata_write"}) as replace_mock, \
             patch.object(self.service, "_buildCheckEntriesForType", return_value=[first_entry, second_entry]) as rebuild_mock:
            result = self.service._resolveChecksReviewEntry(
                entry=first_entry,
                auto_apply_suggested_names=True,
                user_key="user",
                cookies={"_SSID": "session"},
                base_url="https://example.test",
                max_auto_apply_actions=1,
            )

        self.assertEqual(replace_mock.call_count, 1)
        self.assertEqual(rebuild_mock.call_count, 0)
        self.assertIsNone(result["entry"])
        self.assertIsNone(result["item"])
        self.assertEqual(result["auto_applied_count"], 1)
        self.assertTrue(result["auto_apply_limit_reached"])
        self.assertTrue(result["processed_entry_tokens"])

    def test_search_next_checks_item_does_not_auto_apply_manual_mutation_remainders(self):
        image_path = "/volume1/photo/tests/test.jpg"
        pending_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "remaining-after-manual-change",
            "_manual_review_required": True,
        }
        resume_cursor = {
            "check_type": "name_conflicts",
            "path_index": 25,
            "pending_entries": [pending_entry],
            "save_only": False,
            "source_mode": "scan",
            "findings_count": 1,
            "metrics_trusted": True,
        }
        review_item = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "left_name": "Andreas Vilippus",
            "right_name": "Kaire Vilippus",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": {"source_format": "ACD", "name": "Andreas Vilippus"},
            "right_face_target": {"source_format": "MWG_REGIONS", "name": "Kaire Vilippus"},
        }
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: [image_path for _ in range(30)]

        with patch.object(self.service, "getChecksReviewItem", return_value=review_item), \
             patch.object(self.service, "replaceChecksFaceName") as replace_mock:
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                resume_cursor=resume_cursor,
                auto_apply_suggested_names=True,
                auto_apply_suggested_duplicates=False,
            )

        replace_mock.assert_not_called()
        self.assertEqual(result["result"]["entry"]["entry_id"], "remaining-after-manual-change")
        self.assertEqual(result["result"]["item"]["left_state"], "suggested")
        self.assertEqual(result["resume_cursor"]["pending_entries"], [])

    def test_refresh_checks_scan_progress_for_image_rebuilds_remaining_conflicts_for_same_file(self):
        current_progress = {
            "check_type": "name_conflicts",
            "source_mode": "scan",
            "running": False,
            "finished": True,
            "save_only": False,
            "files_scanned": 945,
            "total_files": 40798,
            "findings_count": 2,
            "current_path": "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
            "result": {
                "entry": {
                    "review_type": "name_conflicts",
                    "image_path": "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
                    "entry_id": "initial-current",
                }
            },
            "resume_cursor": {
                "check_type": "name_conflicts",
                "path_index": 945,
                "pending_entries": [
                    {
                        "review_type": "name_conflicts",
                        "image_path": "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
                        "entry_id": "initial-pending",
                    }
                ],
                "save_only": False,
                "source_mode": "scan",
                "findings_count": 2,
            },
        }
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: dict(current_progress)
        written = {}
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True
        self.service._loadPhotoFacesForImageWithOverride = lambda **kwargs: []
        self.service._buildCheckEntriesForType = lambda **kwargs: [
            {
                "review_type": "name_conflicts",
                "image_path": kwargs["image_path"],
                "entry_id": "remaining-after-rename",
            }
        ]

        self.service.refreshChecksScanProgressForImage(
            user_key="user",
            check_type="name_conflicts",
            image_path="/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG",
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
        )

        self.assertEqual(written["state_type"], "checks_progress")
        self.assertEqual(written["state_key"], "user_name_conflicts")
        self.assertEqual(written["payload"]["findings_count"], 2)
        self.assertIsNone(written["payload"]["result"])
        self.assertEqual(written["payload"]["resume_cursor"]["path_index"], 945)
        self.assertEqual(len(written["payload"]["resume_cursor"]["pending_entries"]), 1)
        self.assertEqual(written["payload"]["resume_cursor"]["pending_entries"][0]["entry_id"], "remaining-after-rename")
        self.assertTrue(written["payload"]["resume_cursor"]["pending_entries"][0]["_manual_review_required"])
        self.assertEqual(written["payload"]["findings_count"], 2)

    def test_refresh_checks_scan_progress_for_image_excludes_processed_face_pair_token(self):
        image_path = "/volume1/photo/2011/2011.06.11 - Harz/DSC03369.JPG"
        current_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "current",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        remaining_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "remaining",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.10,
                "y": 0.20,
                "w": 0.10,
                "h": 0.10,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Person Other",
                "x": 0.30,
                "y": 0.40,
                "w": 0.11,
                "h": 0.11,
            },
        }
        flipped_current_entry = {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "entry_id": "current-flipped",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Kaire Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Andreas Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        current_progress = {
            "check_type": "name_conflicts",
            "source_mode": "scan",
            "running": False,
            "finished": True,
            "save_only": False,
            "files_scanned": 945,
            "total_files": 40798,
            "findings_count": 2,
            "current_path": image_path,
            "result": {"entry": current_entry},
            "resume_cursor": {
                "check_type": "name_conflicts",
                "path_index": 945,
                "pending_entries": [remaining_entry],
                "save_only": False,
                "source_mode": "scan",
                "findings_count": 2,
            },
        }
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: dict(current_progress)
        written = {}
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True
        self.service._loadPhotoFacesForImageWithOverride = lambda **kwargs: []
        self.service._buildCheckEntriesForType = lambda **kwargs: [flipped_current_entry, remaining_entry]

        self.service.refreshChecksScanProgressForImage(
            user_key="user",
            check_type="name_conflicts",
            image_path=image_path,
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
        )

        self.assertEqual(written["payload"]["findings_count"], 2)
        self.assertEqual(written["payload"]["resolved_count"], 0)
        self.assertEqual(written["payload"]["ignored_count"], 0)
        pending_entries = written["payload"]["resume_cursor"]["pending_entries"]
        self.assertEqual(len(pending_entries), 1)
        self.assertEqual(pending_entries[0]["entry_id"], "remaining")
        self.assertEqual(written["payload"]["resume_cursor"]["findings_count"], 2)

    def test_refresh_checks_scan_progress_for_image_increments_resolved_name_conflicts(self):
        image_path = "/volume1/photo/tests/test.jpg"
        current_progress = {
            "check_type": "name_conflicts",
            "source_mode": "scan",
            "running": False,
            "finished": True,
            "save_only": False,
            "files_scanned": 20,
            "total_files": 100,
            "findings_count": 7,
            "resolved_count": 2,
            "ignored_count": 1,
            "current_path": image_path,
            "result": {
                "entry": {
                    "review_type": "name_conflicts",
                    "image_path": image_path,
                    "entry_id": "current",
                },
            },
            "resume_cursor": {
                "check_type": "name_conflicts",
                "path_index": 20,
                "pending_entries": [],
                "save_only": False,
                "source_mode": "scan",
                "findings_count": 7,
                "resolved_count": 2,
                "ignored_count": 1,
                "metrics_trusted": True,
            },
        }
        self.service.file_analysis.readRuntimeState = lambda state_type, state_key: dict(current_progress)
        written = {}
        self.service.file_analysis.writeRuntimeState = lambda state_type, state_key, payload: written.update({
            "state_type": state_type,
            "state_key": state_key,
            "payload": dict(payload),
        }) or True
        self.service._loadPhotoFacesForImageWithOverride = lambda **kwargs: []
        self.service._buildCheckEntriesForType = lambda **kwargs: []

        self.service.refreshChecksScanProgressForImage(
            user_key="user",
            check_type="name_conflicts",
            image_path=image_path,
            cookies={},
            base_url="https://example.test",
            shared_folder="/volume1/photo",
            resolved_delta=1,
        )

        self.assertEqual(written["payload"]["findings_count"], 7)
        self.assertEqual(written["payload"]["resolved_count"], 3)
        self.assertEqual(written["payload"]["ignored_count"], 1)

    def test_start_checks_scan_discovery_advances_ignored_name_conflicts_on_next(self):
        current_progress = {
            "check_type": "name_conflicts",
            "source_mode": "scan",
            "running": False,
            "finished": False,
            "save_only": False,
            "files_scanned": 20,
            "total_files": 100,
            "findings_count": 7,
            "resolved_count": 2,
            "ignored_count": 1,
            "result": {
                "entry": {
                    "review_type": "name_conflicts",
                    "image_path": "/volume1/photo/tests/test.jpg",
                    "entry_id": "current",
                },
                "item": {
                    "review_type": "name_conflicts",
                    "image_path": "/volume1/photo/tests/test.jpg",
                },
            },
            "resume_cursor": {
                "check_type": "name_conflicts",
                "path_index": 20,
                "pending_entries": [{"review_type": "name_conflicts", "image_path": "/volume1/photo/tests/test.jpg", "entry_id": "remaining"}],
                "save_only": False,
                "source_mode": "scan",
                "findings_count": 7,
                "resolved_count": 2,
                "ignored_count": 1,
                "metrics_trusted": True,
            },
        }
        self.service.getChecksProgress = lambda user_key, check_type: dict(current_progress)

        class DummyThread:
            def __init__(self, target=None, kwargs=None, daemon=None):
                self.target = target
                self.kwargs = kwargs or {}
                self.daemon = daemon

            def start(self):
                return None

        captured = {}
        original_set = self.service._setChecksProgressMessage
        self.service._setChecksProgressMessage = lambda user_key, check_type, message_key, **updates: captured.update({
            "user_key": user_key,
            "check_type": check_type,
            "message_key": message_key,
            "updates": updates,
        }) or original_set(user_key, check_type, message_key, **updates)

        with patch("imgdata.Thread", DummyThread):
            self.service.startChecksScanDiscovery(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                resume_from_progress=True,
                advance_current_result=True,
            )

        self.assertEqual(captured["updates"]["findings_count"], 7)
        self.assertEqual(captured["updates"]["resolved_count"], 2)
        self.assertEqual(captured["updates"]["ignored_count"], 2)
        self.assertEqual(captured["updates"]["resume_cursor"]["ignored_count"], 2)
        self.assertTrue(captured["updates"]["resume_cursor"]["metrics_trusted"])

    def test_search_next_checks_item_resume_ignores_stale_findings_count_and_counts_pending_entries(self):
        pending_entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "entry_id": "remaining",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Person Remaining",
                "x": 0.11,
                "y": 0.22,
                "w": 0.10,
                "h": 0.10,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Person Other",
                "x": 0.31,
                "y": 0.42,
                "w": 0.12,
                "h": 0.14,
            },
        }
        pending_item = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "entry_id": "remaining-item",
        }

        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]

        with patch.object(self.service, "getChecksReviewItem", return_value=pending_item):
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
                resume_cursor={
                    "check_type": "name_conflicts",
                    "path_index": 945,
                    "pending_entries": [pending_entry],
                    "save_only": False,
                    "source_mode": "scan",
                    "findings_count": 38,
                },
            )

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["result"]["entry"]["entry_id"], "remaining")
        self.assertIsNone(result["result"]["item"])
        self.assertEqual(result["resume_cursor"]["pending_entries"], [])

    def test_search_next_checks_item_refreshes_session_during_long_scan(self):
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service._getChecksCandidatePaths = lambda **kwargs: ["/volume1/photo/tests/test.jpg"]
        self.service.analyzeImageFaceMetadata = lambda image_path: {}
        self.service._buildCheckEntriesForType = lambda **kwargs: []
        self.service.session_manager.keepalive = Mock(return_value={})

        with patch("imgdata.monotonic", side_effect=[0, 181]):
            result = self.service.searchNextChecksItem(
                user_key="user",
                cookies={"_SSID": "sid"},
                base_url="https://example.test",
                check_type="name_conflicts",
                save_only=False,
            )

        self.service.session_manager.keepalive.assert_called_once_with(
            "user",
            base_url="https://example.test",
        )
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(result["message_key"], "checks:progress_finished_no_match")

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
                     side_effect=AssertionError("name_conflicts must not re-read changed image"),
                 ), \
                 patch.object(
                     imgdata_api,
                     "_snapshot_name_conflicts_mutation_state",
                     return_value=(None, {"message": "session_manager_error", "details": {"error": "resume_failed"}}),
                 ) as snapshot_mock:
                response = await imgdata_api.checks_replace_metadata_face_name(object())
                payload = json.loads(response.body.decode("utf-8"))
                self.assertTrue(payload["success"])
                self.assertTrue(payload["data"]["updated"])
                self.assertIsNone(payload["data"]["findings_update"])
                self.assertEqual(payload["data"]["refresh_error"]["message"], "session_manager_error")
                self.assertIsNotNone(snapshot_mock.call_args)

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

    def test_resolve_checks_review_entry_skips_same_conflict_pair_after_name_flip(self):
        initial_entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "ACD",
                "name": "Andreas Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "MWG_REGIONS",
                "name": "Kaire Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        flipped_entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "ACD",
                "name": "Kaire Vilippus",
                "x": 0.63,
                "y": 0.44,
                "w": 0.21,
                "h": 0.46,
            },
            "right_face_signature": {
                "source": "embedded_xmp_exiftool",
                "source_format": "MWG_REGIONS",
                "name": "Andreas Vilippus",
                "x": 0.48,
                "y": 0.60,
                "w": 0.37,
                "h": 0.79,
            },
        }
        items = [
            {
                "review_type": "name_conflicts",
                "image_path": "/volume1/photo/tests/test.jpg",
                "left_name": "Andreas Vilippus",
                "right_name": "Kaire Vilippus",
                "left_state": "suggested",
                "right_state": "alert",
                "left_face_target": dict(initial_entry["left_face_signature"]),
                "right_face_target": dict(initial_entry["right_face_signature"]),
            }
        ]
        applied = {"count": 0}

        with patch.object(self.service, "getChecksReviewItem", side_effect=items), \
             patch.object(self.service, "replaceChecksFaceName", side_effect=lambda **kwargs: applied.update({"count": applied["count"] + 1}) or {
                 "updated": True,
                 "operation": "metadata_write",
             }), \
             patch.object(self.service, "_buildCheckEntriesForType", side_effect=[[flipped_entry]]):
            result = self.service._resolveChecksReviewEntry(
                entry=initial_entry,
                auto_apply_suggested_names=True,
                user_key="user",
                cookies={"_SSID": "session"},
                base_url="https://example.test",
            )

        self.assertIsNone(result["entry"])
        self.assertIsNone(result["item"])
        self.assertEqual(result["auto_applied_count"], 1)
        self.assertEqual(applied["count"], 1)

    def test_resolve_checks_review_entry_returns_empty_item_for_stale_entry(self):
        entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/stale.jpg",
        }

        with patch.object(self.service, "getChecksReviewItem", return_value=None):
            result = self.service._resolveChecksReviewEntry(
                entry=entry,
                user_key="user",
                cookies={"_SSID": "session"},
                base_url="https://example.test",
            )

        self.assertIsNone(result["entry"])
        self.assertIsNone(result["item"])
        self.assertEqual(result["auto_applied_count"], 0)
        self.assertTrue(result["finished"])

    def test_resolve_checks_review_entry_returns_item_when_no_auto_action_applies(self):
        entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/manual.jpg",
        }
        item = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/manual.jpg",
            "left_state": "alert",
            "right_state": "alert",
        }

        with patch.object(self.service, "getChecksReviewItem", return_value=item) as review_mock:
            result = self.service._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=True,
                auto_apply_suggested_duplicates=True,
                user_key="user",
                cookies={"_SSID": "session"},
                base_url="https://example.test",
            )

        self.assertEqual(review_mock.call_count, 1)
        self.assertEqual(result["entry"], entry)
        self.assertEqual(result["item"], item)
        self.assertEqual(result["auto_applied_count"], 0)
        self.assertTrue(result["finished"])

    def test_resolve_checks_review_entry_does_not_rebuild_after_name_change(self):
        entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/loop.jpg",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Person A",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Person B",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
        }
        item = {
            "review_type": "name_conflicts",
            "image_path": entry["image_path"],
            "left_name": "Person A",
            "right_name": "Person B",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(entry["left_face_signature"]),
            "right_face_target": dict(entry["right_face_signature"]),
        }

        with patch.object(self.service, "getChecksReviewItem", return_value=item), \
             patch.object(self.service, "replaceChecksFaceName", return_value={"updated": True}), \
             patch.object(self.service, "_buildCheckEntriesForType", side_effect=AssertionError("must not rebuild after name change")), \
             patch.object(self.service, "_shouldStopChecks", return_value=False):
            result = self.service._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=True,
            )

        self.assertIsNone(result["entry"])
        self.assertIsNone(result["item"])
        self.assertEqual(result["auto_applied_count"], 1)
        self.assertTrue(result["processed_entry_tokens"])

    def test_resolve_checks_review_entry_stops_before_rebuild_after_mutation(self):
        entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/stop.jpg",
            "left_face_signature": {
                "source_format": "ACD",
                "name": "Person A",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "name": "Person B",
                "x": 0.5,
                "y": 0.5,
                "w": 0.2,
                "h": 0.2,
            },
        }
        item = {
            "review_type": "name_conflicts",
            "image_path": entry["image_path"],
            "left_name": "Person A",
            "right_name": "Person B",
            "left_state": "suggested",
            "right_state": "alert",
            "left_face_target": dict(entry["left_face_signature"]),
            "right_face_target": dict(entry["right_face_signature"]),
        }

        with patch.object(self.service, "getChecksReviewItem", return_value=item), \
             patch.object(self.service, "replaceChecksFaceName", return_value={"updated": True}), \
             patch.object(self.service, "_buildCheckEntriesForType", side_effect=AssertionError("must stop before rebuild")), \
             patch.object(self.service, "_shouldStopChecks", side_effect=[False, True]):
            result = self.service._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=True,
            )

        self.assertTrue(result["stop_requested"])
        self.assertEqual(result["auto_applied_count"], 1)

    def test_build_name_conflict_entries_obeys_checks_stop_request(self):
        faces = [
            MetadataFace.from_center_box(
                name="Person A",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="ACD",
            ),
            MetadataFace.from_center_box(
                name="Person B",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MWG_REGIONS",
            ),
        ]
        self.service._readImageMetadata = lambda image_path: MetadataPayload(image_path=image_path, faces=faces)

        with patch.object(self.service, "_raiseIfChecksStopRequested", side_effect=ImgDataOperationError(
            "checks_stop_requested",
            {"code": "checks_stop_requested"},
        )):
            with self.assertRaises(ImgDataOperationError):
                self.service._buildNameConflictReviewEntries("/volume1/photo/tests/stop.jpg")

    def test_build_name_conflict_entries_uses_only_mutual_best_position_match(self):
        faces = [
            MetadataFace.from_center_box(
                name="Person Target",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="ACD",
            ),
            MetadataFace.from_center_box(
                name="Person Target",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MICROSOFT",
            ),
            MetadataFace.from_center_box(
                name="Person Wrong",
                x=0.57,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MWG_REGIONS",
            ),
        ]
        self.service._readImageMetadata = lambda image_path: MetadataPayload(image_path=image_path, faces=faces)

        entries = self.service._buildNameConflictReviewEntries("/volume1/photo/tests/best.jpg")

        self.assertEqual(entries, [])

    def test_build_name_conflict_entries_keeps_best_conflicting_position_match_once(self):
        faces = [
            MetadataFace.from_center_box(
                name="Person Target",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="ACD",
            ),
            MetadataFace.from_center_box(
                name="Person Match",
                x=0.5,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MICROSOFT",
            ),
            MetadataFace.from_center_box(
                name="Person Other",
                x=0.57,
                y=0.5,
                w=0.2,
                h=0.2,
                source="metadata",
                source_format="MWG_REGIONS",
            ),
        ]
        self.service._readImageMetadata = lambda image_path: MetadataPayload(image_path=image_path, faces=faces)

        entries = self.service._buildNameConflictReviewEntries("/volume1/photo/tests/best.jpg")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["left_face_signature"]["name"], "Person Target")
        self.assertEqual(entries[0]["right_face_signature"]["name"], "Person Match")

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

    def test_replace_metadata_face_name_uses_native_embedded_xmp_for_edit_preparation(self):
        payload = MetadataPayload(image_path="dev/test.jpg", has_xmp=True)
        written = {}

        def capture_write(_target_path, xmp_content):
            written["xmp"] = xmp_content
            return {"updated": True}

        with patch.object(self.service, "_readImageMetadata", return_value=payload), \
             patch.object(self.service.exiftool_handler, "isAvailable", return_value=True), \
             patch.object(self.service.files, "loadXmpFromImageParsed", return_value=XMP_MICROSOFT_RENAME), \
             patch.object(self.service.exiftool_handler, "loadEmbeddedXmp", side_effect=AssertionError("native embedded XMP should be used for edit preparation")), \
             patch.object(self.service.exiftool_handler, "writeXmpDetailed", side_effect=capture_write):
            result = self.service.replaceMetadataFaceName(
                image_path="dev/test.jpg",
                face_data={
                    "name": "Person Legacy",
                    "x": 0.25,
                    "y": 0.4,
                    "w": 0.3,
                    "h": 0.4,
                    "source": "embedded_xmp_parsed",
                    "source_format": "MICROSOFT",
                },
                new_name="Person Target",
            )

        self.assertTrue(result["updated"])
        self.assertIn("Person Target", written["xmp"])
        self.assertNotIn("Person Legacy", written["xmp"])

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

    def test_stored_missing_photos_face_entry_is_removed_when_photos_face_exists(self):
        metadata_face = MetadataFace.from_center_box(
            name="Person Known",
            x=0.4,
            y=0.3,
            w=0.2,
            h=0.25,
            source="metadata",
            source_format="MICROSOFT",
        )
        payload = MetadataPayload(
            image_path="/volume1/photo/tests/test.jpg",
            has_xmp=True,
            faces=[metadata_face],
        )
        self.service._readImageMetadata = lambda image_path, **kwargs: payload
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 1234}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: [{
            "face_id": 5678,
            "face_name": "Person Known",
            "person_id": 91,
            "bbox": {
                "top_left": {"x": 0.3, "y": 0.175},
                "bottom_right": {"x": 0.5, "y": 0.425},
            },
        }]

        exists = self.service._storedFaceMatchEntryExists(
            user_key="user",
            cookies={},
            base_url="http://example.test",
            entry={
                "action": "mark_missing_photos_faces",
                "image_path": "/volume1/photo/tests/test.jpg",
                "metadata_face": metadata_face.to_dict(),
            },
            image_faces_cache={},
        )

        self.assertFalse(exists)

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
             patch.object(
                 imgdata_api,
                 "_refresh_checks_mutation_state",
                 side_effect=AssertionError("name_conflicts must not re-read changed image"),
             ) as refresh_mock, \
             patch.object(
                 imgdata_api,
                 "_snapshot_name_conflicts_mutation_state",
                 return_value=({"entries": [], "snapshot_update": True}, None),
             ) as snapshot_mock:
            response = asyncio.run(imgdata_api.checks_replace_metadata_face_name(None))

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertIsNone(refresh_mock.call_args)
        kwargs = snapshot_mock.call_args.kwargs
        self.assertEqual(kwargs["check_type"], "name_conflicts")
        self.assertEqual(kwargs["image_path"], "photo/test.jpg")
        self.assertEqual(kwargs["original_face_data"]["face_id"], 77)
        self.assertEqual(kwargs["replacement_face_data"]["name"], "Person Current")

    def test_checks_replace_metadata_face_name_route_forwards_create_missing_person(self):
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
                "create_missing_person": True,
            }

        with patch.object(imgdata_api, "_prepare_session_request", side_effect=fake_prepare), \
             patch.object(imgdata_api, "_read_request_body", side_effect=fake_body), \
             patch.object(imgdata_api.IMGDATA, "replaceChecksFaceName", return_value={
                 "updated": True,
                 "operation": "photos_create",
                 "resolved_name": "Person Current",
                 "target_person": {"id": 42},
             }) as replace_mock, \
             patch.object(
                 imgdata_api,
                 "_refresh_checks_mutation_state",
                 side_effect=AssertionError("name_conflicts must not re-read changed image"),
             ) as refresh_mock, \
             patch.object(
                 imgdata_api,
                 "_snapshot_name_conflicts_mutation_state",
                 return_value=({"entries": [], "snapshot_update": True}, None),
             ) as snapshot_mock:
            response = asyncio.run(imgdata_api.checks_replace_metadata_face_name(None))

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertTrue(replace_mock.call_args.kwargs["create_missing_person"])
        self.assertIsNone(refresh_mock.call_args)
        kwargs = snapshot_mock.call_args.kwargs
        self.assertEqual(kwargs["check_type"], "name_conflicts")
        self.assertEqual(kwargs["image_path"], "photo/test.jpg")
        self.assertEqual(kwargs["original_face_data"]["face_id"], 77)
        self.assertEqual(kwargs["replacement_face_data"]["name"], "Person Current")

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

    def test_compact_checks_findings_update_keeps_only_image_entries(self):
        refreshed_entry = {
            "review_type": "name_conflicts",
            "image_path": "photo/test.arw",
            "left_face_signature": {"source_format": "ACD", "name": "C"},
            "right_face_signature": {"source_format": "PHOTOS", "name": "D"},
        }
        other_entry = {
            "review_type": "name_conflicts",
            "image_path": "photo/other.jpg",
        }

        update = imgdata_api._compact_checks_findings_update({
            "status": "finished",
            "check_type": "name_conflicts",
            "source_mode": "findings",
            "save_only": False,
            "count": 2,
            "entries": [refreshed_entry, other_entry],
        }, image_path="photo/test.arw")

        self.assertNotIn("entries", update)
        self.assertEqual(update["count"], 2)
        self.assertEqual(update["image_entries"], [refreshed_entry])

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

    def test_start_checks_review_clears_persisted_stop_state_for_findings(self):
        state_key = self.service._checksStateKey("user", "name_conflicts")
        self.service._checks_progress[state_key] = {
            "check_type": "name_conflicts",
            "source_mode": "findings",
            "stop_requested": True,
            "stop_requested_at": "2026-05-08T00:00:00+00:00",
        }

        with patch.object(self.service, "getChecksFindingEntries", return_value={
            "save_only": True,
            "entries": [{"review_type": "name_conflicts", "image_path": "photo/a.jpg"}],
        }):
            result = self.service.startChecksReview(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                source_mode="findings",
                check_type="name_conflicts",
            )

        self.assertEqual(result["count"], 1)
        progress = self.service._checks_progress[state_key]
        self.assertFalse(progress["stop_requested"])
        self.assertNotIn("stop_requested_at", progress)

    def test_start_checks_scan_blocks_parallel_running_scan(self):
        class AliveThread:
            def is_alive(self):
                return True

        running_progress = {
            "running": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
            "files_scanned": 12,
            "total_files": 30,
            "findings_count": 4,
        }
        state_key = self.service._checksStateKey("user", "name_conflicts")
        self.service._checks_progress[state_key] = dict(running_progress)
        self.service._checks_threads[state_key] = AliveThread()

        with patch("imgdata.Thread") as thread_cls:
            result = self.service.startChecksScanDiscovery(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                check_type="duplicate_faces",
            )

        self.assertTrue(result["blocked_by_running_scan"])
        self.assertEqual(result["requested_check_type"], "duplicate_faces")
        self.assertEqual(result["check_type"], "name_conflicts")
        self.assertTrue(result["running"])
        thread_cls.assert_not_called()

    def test_file_analysis_start_blocks_when_face_matching_is_running(self):
        self.service._face_matching_progress["user"] = {
            "operation_id": "face-match-running",
            "running": True,
            "finished": False,
            "action": "search_photo_face_in_file",
        }

        with patch("imgdata.Thread") as thread_cls:
            result = self.service.startFileAnalysisDiscovery(
                user_key="user",
                cookies={},
                base_url="http://example.test",
            )

        self.assertTrue(result["blocked_by_running_operation"])
        self.assertEqual(result["requested_operation"], "file_analysis")
        self.assertEqual(result["running_operation"], "face_match")
        self.assertEqual(result["status"]["schema_version"], 1)
        self.assertEqual(result["status"]["operation"], "file_analysis")
        self.assertEqual(result["status"]["mode"], "none")
        self.assertEqual(result["status"]["phase"], "blocked")
        thread_cls.assert_not_called()

    def test_face_matching_start_blocks_when_file_analysis_is_running(self):
        self.service._file_analysis_progress = {
            "operation_id": "file-analysis-running",
            "running": True,
            "finished": False,
            "status": "running",
        }

        with patch("imgdata.Thread") as thread_cls:
            result = self.service.startFaceMatchingDiscovery(
                user_key="user",
                cookies={},
                base_url="http://example.test",
            )

        self.assertTrue(result["blocked_by_running_operation"])
        self.assertEqual(result["requested_operation"], "face_match")
        self.assertEqual(result["running_operation"], "file_analysis")
        self.assertEqual(result["status"]["schema_version"], 1)
        self.assertEqual(result["status"]["operation"], "face_match")
        self.assertEqual(result["status"]["mode"], "none")
        self.assertEqual(result["status"]["phase"], "blocked")
        thread_cls.assert_not_called()

    def test_checks_scan_start_blocks_when_cleanup_is_running(self):
        state_key = self.service._cleanupStateKey("user", "normalize_names")
        self.service._cleanup_progress[state_key] = {
            "operation_id": "cleanup-running",
            "running": True,
            "finished": False,
            "action": "normalize_names",
        }

        with patch("imgdata.Thread") as thread_cls:
            result = self.service.startChecksScanDiscovery(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                check_type="duplicate_faces",
            )

        self.assertTrue(result["blocked_by_running_operation"])
        self.assertEqual(result["requested_operation"], "checks")
        self.assertEqual(result["running_operation"], "cleanup")
        self.assertEqual(result["status"]["schema_version"], 1)
        self.assertEqual(result["status"]["operation"], "checks")
        self.assertEqual(result["status"]["mode"], "none")
        self.assertEqual(result["status"]["phase"], "blocked")
        thread_cls.assert_not_called()

    def test_cleanup_start_blocks_when_checks_scan_is_running(self):
        state_key = self.service._checksStateKey("user", "name_conflicts")
        self.service._checks_progress[state_key] = {
            "operation_id": "checks-running",
            "running": True,
            "source_mode": "scan",
            "check_type": "name_conflicts",
        }

        with patch("imgdata.Thread") as thread_cls:
            result = self.service.startCleanupRun(
                user_key="user",
                cookies={},
                base_url="http://example.test",
                action="normalize_names",
                targets=["ACD"],
            )

        self.assertTrue(result["blocked_by_running_operation"])
        self.assertEqual(result["requested_operation"], "cleanup")
        self.assertEqual(result["running_operation"], "checks")
        self.assertEqual(result["status"]["schema_version"], 1)
        self.assertEqual(result["status"]["operation"], "cleanup")
        self.assertEqual(result["status"]["mode"], "none")
        self.assertEqual(result["status"]["phase"], "blocked")
        thread_cls.assert_not_called()

    def test_build_check_entries_for_type_excludes_configured_ignore_tokens(self):
        entry = {
            "review_type": "duplicate_faces",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {"source_format": "ACD", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
            "right_face_signature": {"source_format": "ACD", "x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2},
        }
        ignored_token = self.service._checksEntryToken(entry)

        with patch.object(
            self.service,
            "_buildDuplicateFaceReviewEntries",
            return_value=[entry],
        ), patch.object(
            self.service,
            "_configuredChecksIgnoreSettings",
            return_value={
                "DUPLICATE_FACES_ENABLED": True,
            },
        ), patch.object(
            self.service.config,
            "readChecksIgnoreList",
            return_value=[ignored_token],
        ):
            result = self.service._buildCheckEntriesForType(
                image_path="/volume1/photo/tests/test.jpg",
                review_type="duplicate_faces",
            )

        self.assertEqual(result, [])

    def test_stored_name_conflict_review_item_includes_display_faces_for_preview_boxes(self):
        item = self.service._buildStoredChecksReviewItemFromEntry({
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "image_name": "test.jpg",
            "left_face_signature": {
                "source_format": "ACD",
                "source": "embedded_xmp_parsed",
                "name": "Paul Lorenz",
                "x": 0.618125,
                "y": 0.19375,
                "w": 0.20125,
                "h": 0.160833,
            },
            "right_face_signature": {
                "source_format": "MWG_REGIONS",
                "source": "embedded_xmp_parsed",
                "name": "Paul",
                "x": 0.618125,
                "y": 0.19375,
                "w": 0.20125,
                "h": 0.160833,
            },
        })

        self.assertIsNotNone(item)
        self.assertTrue(item["from_stored_finding"])
        self.assertEqual(item["left_face"]["name"], "Paul Lorenz")
        self.assertEqual(item["right_face"]["name"], "Paul")
        self.assertTrue(item["left_face"]["display_normalized"])
        self.assertTrue(item["right_face"]["display_normalized"])
        self.assertIn("bbox", item["left_face"])
        self.assertIn("bbox", item["right_face"])
        self.assertEqual(item["left_alert_faces"], [])
        self.assertEqual(item["right_reference_faces"], [])

    def test_ignore_checks_entry_persists_unique_token(self):
        entry = {
            "review_type": "name_conflicts",
            "image_path": "/volume1/photo/tests/test.jpg",
            "left_face_signature": {"source_format": "ACD", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
            "right_face_signature": {"source_format": "MICROSOFT", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
        }
        ignored_token = self.service._checksEntryToken(entry)

        with patch.object(
            self.service,
            "_configuredChecksIgnoreSettings",
            return_value={
                "NAME_CONFLICTS_ENABLED": True,
            },
        ), patch.object(
            self.service.config,
            "appendChecksIgnoreToken",
            return_value={
                "saved": True,
                "token": ignored_token,
                "count": 1,
            },
        ):
            result = self.service.ignoreChecksEntry(entry=entry)

        self.assertTrue(result["ignored"])
        self.assertEqual(result["token"], ignored_token)

    def test_config_service_migrates_legacy_checks_ignore_lists_to_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = os.path.join(tempdir, "config.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "analysis": {
                            "CHECKS": {
                                "IGNORE_LIST_DUPLICATE_FACES": ["token-a", "token-a", "token-b"],
                            },
                        },
                    },
                    handle,
                )

            config_service = ConfigService(config_path)
            merged = config_service.readMergedConfig()

            self.assertNotIn("IGNORE_LIST_DUPLICATE_FACES", merged["analysis"]["CHECKS"])
            self.assertEqual(config_service.readChecksIgnoreList("duplicate_faces"), ["token-a", "token-b"])

if __name__ == "__main__":
    unittest.main()
