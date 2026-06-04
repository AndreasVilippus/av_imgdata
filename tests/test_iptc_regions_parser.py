#!/usr/bin/env python3

from parser.metadata_parser import MetadataParser
from parser.iptc_regions_parser import IptcRegionsParser


def iptc_xmp(name="Max Mustermann"):
    return f'''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
           xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
           xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#">
    <rdf:Description>
      <Iptc4xmpExt:ImageRegion>
        <rdf:Bag>
          <rdf:li>
            <Iptc4xmpExt:Name>{name}</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role>
              <rdf:Bag>
                <rdf:li>person</rdf:li>
              </rdf:Bag>
            </Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.50" stArea:y="0.40" stArea:w="0.20" stArea:h="0.30" />
          </rdf:li>
        </rdf:Bag>
      </Iptc4xmpExt:ImageRegion>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''


def iptc_xmp_body(body):
    return f'''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
           xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
           xmlns:iptcExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
           xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#"
           xmlns:tiff="http://ns.adobe.com/tiff/1.0/">
    <rdf:Description>
      {body}
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''


def test_iptc_regions_parser_reads_named_person_region():
    faces = IptcRegionsParser.parse_faces(iptc_xmp(), source="sidecar")

    assert len(faces) == 1
    face = faces[0].to_dict()
    assert face["name"] == "Max Mustermann"
    assert face["source"] == "sidecar"
    assert face["source_format"] == "IPTC_EXT_REGIONS"
    assert face["x"] == 0.50
    assert face["y"] == 0.40
    assert face["w"] == 0.20
    assert face["h"] == 0.30
    assert face["focus_usage"] == "person"


def test_metadata_parser_includes_iptc_regions_by_default():
    payload = MetadataParser().parse(
        image_path="/tmp/sample.jpg",
        xmp_content=iptc_xmp("Erika Musterfrau"),
        xmp_source="embedded_xmp_parsed",
    )

    faces = [face.to_dict() for face in payload.faces]
    assert len(faces) == 1
    assert faces[0]["name"] == "Erika Musterfrau"
    assert faces[0]["source_format"] == "IPTC_EXT_REGIONS"


def test_metadata_parser_can_disable_iptc_regions():
    payload = MetadataParser().parse(
        image_path="/tmp/sample.jpg",
        xmp_content=iptc_xmp(),
        xmp_source="embedded_xmp_parsed",
        use_iptc_ext_regions=False,
    )

    assert payload.faces == []


def test_iptc_regions_parser_reads_multiple_regions_without_role_duplicates():
    xmp = iptc_xmp_body('''
      <Iptc4xmpExt:ImageRegion>
        <rdf:Bag>
          <rdf:li>
            <Iptc4xmpExt:Name>Alice</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role><rdf:Bag><rdf:li>person</rdf:li></rdf:Bag></Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.20" stArea:y="0.30" stArea:w="0.10" stArea:h="0.10" />
          </rdf:li>
          <rdf:li>
            <Iptc4xmpExt:Name>Bob</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role><rdf:Bag><rdf:li>face</rdf:li></rdf:Bag></Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.60" stArea:y="0.30" stArea:w="0.10" stArea:h="0.10" />
          </rdf:li>
        </rdf:Bag>
      </Iptc4xmpExt:ImageRegion>
    ''')

    faces = [face.to_dict() for face in IptcRegionsParser.parse_faces(xmp, source="sidecar")]

    assert [face["name"] for face in faces] == ["Alice", "Bob"]


def test_iptc_regions_parser_supports_alt_prefix_container_and_region_names():
    xmp = iptc_xmp_body('''
      <iptcExt:ImageRegions>
        <rdf:Bag>
          <rdf:li>
            <iptcExt:RegionName>Carla</iptcExt:RegionName>
            <iptcExt:RegionRole>portrait</iptcExt:RegionRole>
            <iptcExt:RegionBoundary stArea:x="0.30" stArea:y="0.40" stArea:w="0.20" stArea:h="0.10" />
          </rdf:li>
        </rdf:Bag>
      </iptcExt:ImageRegions>
    ''')

    faces = [face.to_dict() for face in IptcRegionsParser.parse_faces(xmp, source="embedded")]

    assert len(faces) == 1
    assert faces[0]["name"] == "Carla"
    assert faces[0]["x"] == 0.30
    assert faces[0]["source"] == "embedded"


def test_iptc_regions_parser_skips_non_person_or_incomplete_regions():
    xmp = iptc_xmp_body('''
      <Iptc4xmpExt:ImageRegion>
        <rdf:Bag>
          <rdf:li>
            <Iptc4xmpExt:Name>Landscape</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role>object</Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.20" stArea:y="0.30" stArea:w="0.10" stArea:h="0.10" />
          </rdf:li>
          <rdf:li>
            <Iptc4xmpExt:Role>person</Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.40" stArea:y="0.30" stArea:w="0.10" stArea:h="0.10" />
          </rdf:li>
          <rdf:li>
            <Iptc4xmpExt:Name>No Boundary</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role>person</Iptc4xmpExt:Role>
          </rdf:li>
          <rdf:li>
            <Iptc4xmpExt:Name>Circle</Iptc4xmpExt:Name>
            <Iptc4xmpExt:Role>person</Iptc4xmpExt:Role>
            <Iptc4xmpExt:Boundary stArea:x="0.70" stArea:y="0.30" stArea:w="0.10" stArea:h="0.10" stArea:shape="circle" />
          </rdf:li>
        </rdf:Bag>
      </Iptc4xmpExt:ImageRegion>
    ''')

    assert IptcRegionsParser.parse_faces(xmp, source="sidecar") == []


def test_metadata_parser_assigns_orientation_to_iptc_regions():
    payload = MetadataParser().parse(
        image_path="/tmp/sample.jpg",
        xmp_content=iptc_xmp_body('''
          <tiff:Orientation>6</tiff:Orientation>
          <Iptc4xmpExt:ImageRegion>
            <rdf:Bag>
              <rdf:li>
                <Iptc4xmpExt:Name>Rotated</Iptc4xmpExt:Name>
                <Iptc4xmpExt:Role>person</Iptc4xmpExt:Role>
                <Iptc4xmpExt:Boundary stArea:x="0.50" stArea:y="0.40" stArea:w="0.20" stArea:h="0.30" />
              </rdf:li>
            </rdf:Bag>
          </Iptc4xmpExt:ImageRegion>
        '''),
        xmp_source="embedded_xmp_parsed",
    )

    assert len(payload.faces) == 1
    assert payload.image_orientation == 6
    assert payload.faces[0].orientation == 6
