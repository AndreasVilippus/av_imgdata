#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import List

from models.metadata_face import MetadataFace
from parser.xmp_helpers import NS_ACD


class AcdParser:
    @staticmethod
    def parse_faces(
        xmp_content: str,
        *,
        source: str,
        filter_unknown: bool = True,
        filter_denied: bool = True,
    ) -> List[MetadataFace]:
        persons: List[MetadataFace] = []
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return persons

        for description in root.findall(".//rdf:Description", NS_ACD):
            if description.get("{http://ns.acdsee.com/regions/}Type") != "Face":
                continue
            if filter_denied and description.get("{http://ns.acdsee.com/regions/}NameAssignType") == "denied":
                continue

            name = description.get("{http://ns.acdsee.com/regions/}Name")
            if filter_unknown and name is None:
                continue

            area = description.find("acdsee-rs:DLYArea", NS_ACD)
            if area is None:
                continue

            try:
                x = float(area.get("{http://ns.acdsee.com/sType/Area#}x"))
                y = float(area.get("{http://ns.acdsee.com/sType/Area#}y"))
                width = float(area.get("{http://ns.acdsee.com/sType/Area#}w"))
                height = float(area.get("{http://ns.acdsee.com/sType/Area#}h"))
            except (TypeError, ValueError):
                continue

            persons.append(
                MetadataFace.from_center_box(
                    name=str(name or ""),
                    x=x,
                    y=y,
                    w=width,
                    h=height,
                    source=source,
                    source_format="ACD",
                )
            )
        return persons
