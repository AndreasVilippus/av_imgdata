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
       MPReg:PersonDisplayName="Kaire Vilippus"
       MPReg:Rectangle="0.746875, 0.331250, 0.196875, 0.261458"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
   <mwg-rs:Regions rdf:parseType="Resource">
    <mwg-rs:RegionList>
     <rdf:Bag>
      <rdf:li>
       <rdf:Description
        mwg-rs:Name="Kaire Vilippus"
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

    def test_orientation_risk_fallback_prefers_non_risky_side(self):
        risky_face = MetadataFace.from_center_box(
            name="Kaire Vilippus",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        safe_face = MetadataFace.from_center_box(
            name="Kaire Vilippus",
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
            name="Kaire Vilippus",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        safe_face = MetadataFace.from_center_box(
            name="Kaire Vilippus",
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

    def test_duplicate_support_prefers_safe_reinforcement_when_totals_tie(self):
        mwg_bottom = MetadataFace.from_center_box(
            name="Kaire Vilippus",
            x=0.845282,
            y=0.46201,
            w=0.196691,
            h=0.261438,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        mwg_top = MetadataFace.from_center_box(
            name="Kaire Vilippus",
            x=0.154412,
            y=0.537786,
            w=0.308824,
            h=0.435866,
            source="metadata",
            source_format="MWG_REGIONS",
            orientation=6,
        )
        acd_face = MetadataFace.from_center_box(
            name="Kaire Vilippus",
            x=0.471405,
            y=0.146553,
            w=0.309028,
            h=0.280852,
            source="metadata",
            source_format="ACD",
        )
        microsoft_face = MetadataFace.from_top_left_box(
            name="Kaire Vilippus",
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
