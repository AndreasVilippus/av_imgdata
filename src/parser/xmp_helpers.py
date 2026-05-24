#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import Optional


NS_ACD = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "acdsee-rs": "http://ns.acdsee.com/regions/",
    "acdsee-stArea": "http://ns.acdsee.com/sType/Area#",
}

NS_MWG_REGIONS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#",
    "stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
}

NS_MICROSOFT = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "MP": "http://ns.microsoft.com/photo/1.2/",
    "MPRI": "http://ns.microsoft.com/photo/1.2/t/RegionInfo#",
    "MPReg": "http://ns.microsoft.com/photo/1.2/t/Region#",
}


def read_text_attribute_or_child(node: ET.Element, local_name: str, namespace: str) -> str:
    value = node.get(f"{{{namespace}}}{local_name}")
    if value:
        return value.strip()
    child = node.find(f"{{{namespace}}}{local_name}")
    if child is not None and child.text:
        return child.text.strip()
    return ""


def read_float_attribute_or_child(node: ET.Element, local_name: str, namespace: str) -> float:
    value = read_text_attribute_or_child(node, local_name, namespace)
    return float(value)


def read_int_attribute_or_child(node: ET.Element, local_name: str, namespace: str) -> Optional[int]:
    value = read_text_attribute_or_child(node, local_name, namespace)
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def extract_xmp_tiff_orientation(xmp_content: str) -> Optional[int]:
    try:
        root = ET.fromstring(xmp_content)
    except Exception:
        return None

    for description in root.findall(".//rdf:Description", NS_MWG_REGIONS):
        value = description.get("{http://ns.adobe.com/tiff/1.0/}Orientation")
        if value:
            try:
                return int(value.strip())
            except (TypeError, ValueError):
                pass

        orientation_node = description.find("tiff:Orientation", NS_MWG_REGIONS)
        if orientation_node is not None and orientation_node.text:
            try:
                return int(orientation_node.text.strip())
            except (TypeError, ValueError):
                return None
    return None
