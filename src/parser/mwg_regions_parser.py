#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from models.metadata_face import MetadataFace
from parser.xmp_helpers import (
    NS_MWG_REGIONS,
    read_float_attribute_or_child,
    read_int_attribute_or_child,
    read_text_attribute_or_child,
)


class MwgRegionsParser:
    @staticmethod
    def parse_faces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        persons: List[MetadataFace] = []
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return persons

        for description in list(root.findall(".//rdf:Description", NS_MWG_REGIONS)) + list(root.findall(".//rdf:li", NS_MWG_REGIONS)):
            face_type = description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Type")
            if not face_type:
                type_node = description.find("mwg-rs:Type", NS_MWG_REGIONS)
                face_type = type_node.text.strip() if type_node is not None and type_node.text else ""
            if face_type != "Face":
                continue

            area = description.find("mwg-rs:Area", NS_MWG_REGIONS)
            if area is None:
                continue

            try:
                x = read_float_attribute_or_child(area, "x", NS_MWG_REGIONS["stArea"])
                y = read_float_attribute_or_child(area, "y", NS_MWG_REGIONS["stArea"])
                width = read_float_attribute_or_child(area, "w", NS_MWG_REGIONS["stArea"])
                height = read_float_attribute_or_child(area, "h", NS_MWG_REGIONS["stArea"])
            except (TypeError, ValueError):
                continue

            name = description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Name")
            if name is None:
                name_node = description.find("mwg-rs:Name", NS_MWG_REGIONS)
                name = name_node.text.strip() if name_node is not None and name_node.text else ""

            focus_usage = description.get("{http://www.metadataworkinggroup.com/schemas/regions/}FocusUsage")
            if focus_usage is None:
                focus_usage_node = description.find("mwg-rs:FocusUsage", NS_MWG_REGIONS)
                focus_usage = focus_usage_node.text.strip() if focus_usage_node is not None and focus_usage_node.text else ""

            persons.append(
                MetadataFace.from_center_box(
                    name=str(name or ""),
                    x=x,
                    y=y,
                    w=width,
                    h=height,
                    source=source,
                    source_format="MWG_REGIONS",
                    focus_usage=str(focus_usage or ""),
                )
            )
        return persons

    @staticmethod
    def extract_context(xmp_content: str) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "mwg_applied_to_dimensions_present": False,
            "mwg_applied_to_dimensions": {},
        }
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return context

        applied = root.find(".//mwg-rs:AppliedToDimensions", NS_MWG_REGIONS)
        if applied is None:
            return context

        width = read_int_attribute_or_child(applied, "w", NS_MWG_REGIONS["stDim"])
        height = read_int_attribute_or_child(applied, "h", NS_MWG_REGIONS["stDim"])
        unit = read_text_attribute_or_child(applied, "unit", NS_MWG_REGIONS["stDim"])
        context["mwg_applied_to_dimensions_present"] = True
        context["mwg_applied_to_dimensions"] = {
            "width": width,
            "height": height,
            "unit": unit,
        }
        return context
