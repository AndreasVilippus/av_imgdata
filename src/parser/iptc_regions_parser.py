#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import List, Optional

from models.metadata_face import MetadataFace
from parser.xmp_helpers import NS_IPTC_EXT, read_float_attribute_or_child, read_text_attribute_or_child


class IptcRegionsParser:
    """Parse IPTC Extension Image Region entries from XMP.

    The parser is intentionally read-only and conservative. It accepts rectangular
    IPTC image regions with a usable name and boundary. Unsupported or incomplete
    regions are ignored so the existing analysis run can safely count supported
    face/person regions without changing files.
    """

    @staticmethod
    def parse_faces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        faces: List[MetadataFace] = []
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return faces

        for region in IptcRegionsParser._iter_region_nodes(root):
            name = IptcRegionsParser._read_region_name(region)
            if not name:
                continue
            if not IptcRegionsParser._is_face_or_person_region(region):
                continue
            boundary = IptcRegionsParser._find_boundary(region)
            if boundary is None:
                continue
            shape = IptcRegionsParser._read_shape(boundary)
            if shape and shape.lower() not in {"rectangle", "rect"}:
                continue
            try:
                x = read_float_attribute_or_child(boundary, "x", NS_IPTC_EXT["stArea"])
                y = read_float_attribute_or_child(boundary, "y", NS_IPTC_EXT["stArea"])
                width = read_float_attribute_or_child(boundary, "w", NS_IPTC_EXT["stArea"])
                height = read_float_attribute_or_child(boundary, "h", NS_IPTC_EXT["stArea"])
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            faces.append(
                MetadataFace.from_center_box(
                    name=name,
                    x=x,
                    y=y,
                    w=width,
                    h=height,
                    source=source,
                    source_format="IPTC_EXT_REGIONS",
                    focus_usage=IptcRegionsParser._read_region_role(region),
                )
            )
        return faces

    @staticmethod
    def _iter_region_nodes(root: ET.Element) -> List[ET.Element]:
        nodes: List[ET.Element] = []
        for tag_name in ("ImageRegion", "ImageRegions"):
            for container in root.findall(f".//Iptc4xmpExt:{tag_name}", NS_IPTC_EXT):
                nodes.extend(IptcRegionsParser._region_items_from_container(container))
            for container in root.findall(f".//iptcExt:{tag_name}", NS_IPTC_EXT):
                nodes.extend(IptcRegionsParser._region_items_from_container(container))
        return nodes

    @staticmethod
    def _region_items_from_container(container: ET.Element) -> List[ET.Element]:
        items = container.findall(".//rdf:li", NS_IPTC_EXT)
        if items:
            return items
        return [container]

    @staticmethod
    def _read_region_name(region: ET.Element) -> str:
        for local_name in ("Name", "RegionName"):
            value = read_text_attribute_or_child(region, local_name, NS_IPTC_EXT["Iptc4xmpExt"])
            if value:
                return value
        return ""

    @staticmethod
    def _read_region_role(region: ET.Element) -> str:
        values: List[str] = []
        for local_name in ("Role", "RegionRole"):
            value = read_text_attribute_or_child(region, local_name, NS_IPTC_EXT["Iptc4xmpExt"])
            if value:
                values.append(value)
        for role_node in region.findall(".//Iptc4xmpExt:Role//rdf:li", NS_IPTC_EXT):
            if role_node.text and role_node.text.strip():
                values.append(role_node.text.strip())
        for role_node in region.findall(".//iptcExt:Role//rdf:li", NS_IPTC_EXT):
            if role_node.text and role_node.text.strip():
                values.append(role_node.text.strip())
        return values[0] if values else ""

    @staticmethod
    def _is_face_or_person_region(region: ET.Element) -> bool:
        candidates: List[str] = []
        for local_name in ("Type", "RegionType", "Role", "RegionRole"):
            value = read_text_attribute_or_child(region, local_name, NS_IPTC_EXT["Iptc4xmpExt"])
            if value:
                candidates.append(value)
        for node in region.findall(".//rdf:li", NS_IPTC_EXT):
            if node.text and node.text.strip():
                candidates.append(node.text.strip())
        if not candidates:
            return True
        normalized = {value.strip().casefold() for value in candidates if value.strip()}
        return bool(normalized.intersection({"face", "person", "people", "human", "portrait"}))

    @staticmethod
    def _find_boundary(region: ET.Element) -> Optional[ET.Element]:
        for local_name in ("Boundary", "RegionBoundary", "Area"):
            direct = region.find(f"Iptc4xmpExt:{local_name}", NS_IPTC_EXT)
            if direct is not None:
                return direct
            direct = region.find(f"iptcExt:{local_name}", NS_IPTC_EXT)
            if direct is not None:
                return direct
        for candidate in region.findall(".//*"):
            local_name = candidate.tag.rsplit("}", 1)[-1] if "}" in candidate.tag else candidate.tag
            if local_name in {"Boundary", "RegionBoundary", "Area"}:
                return candidate
        return None

    @staticmethod
    def _read_shape(boundary: ET.Element) -> str:
        for local_name in ("unit", "type", "shape"):
            value = read_text_attribute_or_child(boundary, local_name, NS_IPTC_EXT["stArea"])
            if local_name == "shape" and value:
                return value
        value = boundary.get("shape") or boundary.get("Shape")
        return str(value or "").strip()
