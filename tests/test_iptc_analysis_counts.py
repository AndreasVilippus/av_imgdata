#!/usr/bin/env python3

from handler.file_handler import FileHandler
from parser.metadata_parser import MetadataParser


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


def test_file_analysis_counts_iptc_region_faces_in_formats():
    payload = MetadataParser().parse(
        image_path="/tmp/sample.jpg",
        xmp_content=iptc_xmp(),
        xmp_source="xmp_file",
    )

    analysis = FileHandler().analyzeMetadata(payload)

    assert analysis["files_with_face_metadata"] == 1
    assert analysis["faces_total"] == 1
    assert analysis["faces_named"] == 1
    assert analysis["formats"] == {"IPTC_EXT_REGIONS": 1}
    assert analysis["sources"] == {"xmp_file": 1}
