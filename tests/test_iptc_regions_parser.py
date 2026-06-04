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
