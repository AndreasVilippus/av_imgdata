import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from parser.metadata_parser import MetadataParser
from services.bbox_normalizer import normalize_xmp_face


XMP_MICROSOFT = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
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
       MPReg:PersonDisplayName="Andreas Schulz"
       MPReg:Rectangle="0.192515, 0.341564, 0.109954, 0.146605"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


class MicrosoftFaceParsingTests(unittest.TestCase):
    def test_microsoft_rectangle_is_parsed_as_top_left_box(self):
        parser = MetadataParser()
        payload = parser.parse(
            image_path="dev/IMG_2234.JPG",
            xmp_content=XMP_MICROSOFT,
            image_orientation=1,
            use_acd=False,
            use_microsoft=True,
            use_mwg_regions=False,
        )

        self.assertEqual(len(payload.faces), 1)
        face = payload.faces[0]
        self.assertAlmostEqual(face.x, 0.247492)
        self.assertAlmostEqual(face.y, 0.4148665)
        self.assertAlmostEqual(face.w, 0.109954)
        self.assertAlmostEqual(face.h, 0.146605)

    def test_microsoft_face_is_orientation_normalized_like_other_xmp_faces(self):
        parser = MetadataParser()
        payload = parser.parse(
            image_path="dev/IMG_2234.JPG",
            xmp_content=XMP_MICROSOFT,
            image_orientation=6,
            use_acd=False,
            use_microsoft=True,
            use_mwg_regions=False,
        )

        self.assertEqual(len(payload.faces), 1)
        face = payload.faces[0]
        self.assertEqual(face.orientation, 6)

        normalized = normalize_xmp_face(face.to_dict())
        self.assertAlmostEqual(normalized["x"], 0.5851335)
        self.assertAlmostEqual(normalized["y"], 0.247492)
        self.assertAlmostEqual(normalized["w"], 0.146605)
        self.assertAlmostEqual(normalized["h"], 0.109954)


if __name__ == "__main__":
    unittest.main()
