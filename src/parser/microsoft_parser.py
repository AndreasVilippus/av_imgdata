#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import List

from models.metadata_face import MetadataFace


class MicrosoftParser:
    @staticmethod
    def parse_faces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        persons: List[MetadataFace] = []
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return persons

        for description in root.iter():
            if description.tag not in {
                "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description",
                "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li",
            }:
                continue

            rectangle = ""
            name = ""
            for key, value in description.attrib.items():
                local_name = key.split("}", 1)[-1]
                if local_name == "Rectangle" and value:
                    rectangle = value.strip()
                elif local_name == "PersonDisplayName" and value:
                    name = value.strip()

            if not rectangle or not name:
                for child in list(description):
                    local_name = child.tag.split("}", 1)[-1]
                    text = child.text.strip() if child.text else ""
                    if local_name == "Rectangle" and text and not rectangle:
                        rectangle = text
                    elif local_name == "PersonDisplayName" and not name:
                        name = text

            if not rectangle:
                continue

            try:
                x, y, width, height = [float(value.strip()) for value in rectangle.split(",")]
            except (TypeError, ValueError):
                continue

            persons.append(
                MetadataFace.from_top_left_box(
                    name=name,
                    left=x,
                    top=y,
                    w=width,
                    h=height,
                    source=source,
                    source_format="MICROSOFT",
                )
            )
        return persons
