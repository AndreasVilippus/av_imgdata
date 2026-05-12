from pytest import approx

from parser.metadata_parser import MetadataParser


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


XMP_ACD_DENIED = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:acdsee-rs="http://ns.acdsee.com/regions/"
    xmlns:acdsee-stArea="http://ns.acdsee.com/sType/Area#"
    acdsee-rs:Type="Face"
    acdsee-rs:Name="Person Denied"
    acdsee-rs:NameAssignType="denied">
   <acdsee-rs:DLYArea
    acdsee-stArea:x="0.4"
    acdsee-stArea:y="0.3"
    acdsee-stArea:w="0.2"
    acdsee-stArea:h="0.25"/>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


XMP_MICROSOFT_ATTRIBUTE_RECTANGLE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
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
       MPReg:Rectangle="0.192515, 0.341564, 0.109954, 0.146605"/>
     </rdf:Bag>
    </MPRI:Regions>
   </MP:RegionInfo>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


XMP_MICROSOFT_CHILD_RECTANGLE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:MPReg="http://ns.microsoft.com/photo/1.2/t/Region#">
   <MPReg:PersonDisplayName>Person Child</MPReg:PersonDisplayName>
   <MPReg:Rectangle>0.1, 0.2, 0.3, 0.4</MPReg:Rectangle>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


XMP_MWG_CONTEXT = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"
    xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#"
    xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/">
   <tiff:Orientation>6</tiff:Orientation>
   <mwg-rs:AppliedToDimensions
    stDim:w="4000"
    stDim:h="3000"
    stDim:unit="pixel"/>
   <mwg-rs:Regions rdf:parseType="Resource">
    <mwg-rs:RegionList>
     <rdf:Bag>
      <rdf:li>
       <rdf:Description
        mwg-rs:Name="Person MWG"
        mwg-rs:Type="Face"
        mwg-rs:FocusUsage="EvaluatedNotUsed">
        <mwg-rs:Area
         stArea:x="0.25"
         stArea:y="0.35"
         stArea:w="0.2"
         stArea:h="0.1"
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


def parse_metadata(xmp_content, **kwargs):
    return MetadataParser().parse(
        image_path="dev/test.jpg",
        xmp_content=xmp_content,
        image_dimensions={"width": 4000, "height": 3000, "unit": "pixel"},
        **kwargs,
    )


def test_acd_unnamed_faces_are_skipped_by_default_and_optional_when_requested():
    default_payload = parse_metadata(
        XMP_ACD_UNNAMED,
        use_acd=True,
        use_microsoft=False,
        use_mwg_regions=False,
    )
    extended_payload = parse_metadata(
        XMP_ACD_UNNAMED,
        use_acd=True,
        use_microsoft=False,
        use_mwg_regions=False,
        include_unnamed_acd=True,
    )

    assert default_payload.faces == []
    assert len(extended_payload.faces) == 1
    assert extended_payload.faces[0].source_format == "ACD"
    assert extended_payload.faces[0].name == ""


def test_acd_denied_faces_are_filtered_even_when_unnamed_faces_are_included():
    payload = parse_metadata(
        XMP_ACD_DENIED,
        use_acd=True,
        use_microsoft=False,
        use_mwg_regions=False,
        include_unnamed_acd=True,
    )

    assert payload.faces == []


def test_microsoft_rectangle_attributes_are_parsed_as_top_left_box():
    payload = parse_metadata(
        XMP_MICROSOFT_ATTRIBUTE_RECTANGLE,
        image_orientation=1,
        use_acd=False,
        use_microsoft=True,
        use_mwg_regions=False,
    )

    assert len(payload.faces) == 1
    face = payload.faces[0]
    assert face.name == "Person Legacy"
    assert face.source_format == "MICROSOFT"
    assert face.x == approx(0.247492)
    assert face.y == approx(0.4148665)
    assert face.w == approx(0.109954)
    assert face.h == approx(0.146605)


def test_microsoft_rectangle_child_elements_are_parsed():
    payload = parse_metadata(
        XMP_MICROSOFT_CHILD_RECTANGLE,
        image_orientation=1,
        use_acd=False,
        use_microsoft=True,
        use_mwg_regions=False,
    )

    assert len(payload.faces) == 1
    face = payload.faces[0]
    assert face.name == "Person Child"
    assert face.x == approx(0.25)
    assert face.y == approx(0.4)
    assert face.w == approx(0.3)
    assert face.h == approx(0.4)


def test_microsoft_faces_receive_non_default_orientation():
    payload = parse_metadata(
        XMP_MICROSOFT_ATTRIBUTE_RECTANGLE,
        image_orientation=6,
        use_acd=False,
        use_microsoft=True,
        use_mwg_regions=False,
    )

    assert len(payload.faces) == 1
    assert payload.faces[0].orientation == 6


def test_mwg_regions_extract_context_orientation_and_focus_usage():
    payload = parse_metadata(
        XMP_MWG_CONTEXT,
        image_orientation=None,
        use_acd=False,
        use_microsoft=False,
        use_mwg_regions=True,
    )

    assert len(payload.faces) == 1
    face = payload.faces[0]
    assert face.name == "Person MWG"
    assert face.source_format == "MWG_REGIONS"
    assert face.focus_usage == "EvaluatedNotUsed"
    assert face.orientation == 6
    assert payload.image_orientation == 6
    assert payload.mwg_applied_to_dimensions_present is True
    assert payload.mwg_applied_to_dimensions == {
        "width": 4000,
        "height": 3000,
        "unit": "pixel",
    }
    assert payload.mwg_applied_to_dimensions_matches_current is True
    assert payload.mwg_orientation_transform_required is True


def test_invalid_xml_returns_empty_payload_without_raising():
    payload = parse_metadata(
        "<x:xmpmeta><broken>",
        image_orientation=None,
        use_acd=True,
        use_microsoft=True,
        use_mwg_regions=True,
    )

    assert payload.has_xmp is True
    assert payload.faces == []
    assert payload.image_orientation is None
