#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload


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


class MetadataParser:
    def parse(
        self,
        *,
        image_path: str,
        xmp_content: Optional[str],
        xmp_path: str = "",
        xmp_source: str = "",
        image_dimensions: Optional[Dict[str, Any]] = None,
        image_orientation: Optional[int] = None,
        use_acd: bool = True,
        use_microsoft: bool = True,
        use_mwg_regions: bool = True,
        include_unnamed_acd: bool = False,
    ) -> MetadataPayload:
        faces: List[MetadataFace] = []
        mwg_context: Dict[str, Any] = {
            "mwg_applied_to_dimensions_present": False,
            "mwg_applied_to_dimensions": {},
        }

        if xmp_content:
            if use_acd:
                faces.extend(
                    self._parseAcdFaces(
                        xmp_content,
                        source=xmp_source or "metadata",
                        filter_unknown=not include_unnamed_acd,
                    )
                )
            if use_microsoft:
                faces.extend(self._parseMicrosoftFaces(xmp_content, source=xmp_source or "metadata"))
            if use_mwg_regions:
                mwg_context = self._extractMwgRegionsContext(xmp_content)
                faces.extend(self._parseMwgRegionsFaces(xmp_content, source=xmp_source or "metadata"))

        xmp_orientation = self._extractXmpTiffOrientation(xmp_content) if xmp_content else None
        if image_orientation is None:
            image_orientation = xmp_orientation

        if image_orientation not in (None, 1):
            for face in faces:
                if face.source_format in {"MWG_REGIONS", "MICROSOFT"}:
                    face.orientation = image_orientation

        applied_dimensions = mwg_context.get("mwg_applied_to_dimensions") if isinstance(mwg_context.get("mwg_applied_to_dimensions"), dict) else {}
        applied_width = applied_dimensions.get("width")
        applied_height = applied_dimensions.get("height")
        applied_unit = str(applied_dimensions.get("unit") or "").strip().lower()
        current_dimensions = image_dimensions or {}
        current_width = current_dimensions.get("width")
        current_height = current_dimensions.get("height")
        mwg_matches_current: Optional[bool] = None
        if mwg_context.get("mwg_applied_to_dimensions_present") and applied_unit == "pixel" and applied_width and applied_height and current_width and current_height:
            mwg_matches_current = applied_width == current_width and applied_height == current_height

        return MetadataPayload(
            image_path=image_path,
            xmp_path=xmp_path,
            has_sidecar=bool(xmp_path),
            xmp_source=xmp_source,
            has_xmp=bool(xmp_content),
            faces=faces,
            image_dimensions=current_dimensions,
            image_orientation=image_orientation,
            mwg_applied_to_dimensions_present=bool(mwg_context.get("mwg_applied_to_dimensions_present")),
            mwg_applied_to_dimensions=applied_dimensions,
            mwg_applied_to_dimensions_matches_current=mwg_matches_current,
            mwg_orientation_transform_required=bool(
                mwg_context.get("mwg_applied_to_dimensions_present")
                and image_orientation not in (None, 1)
            ),
        )

    @staticmethod
    def _parseAcdFaces(
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

    @staticmethod
    def _parseMwgRegionsFaces(xmp_content: str, *, source: str) -> List[MetadataFace]:
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
                x = MetadataParser._readFloatAttributeOrChild(area, "x", NS_MWG_REGIONS["stArea"])
                y = MetadataParser._readFloatAttributeOrChild(area, "y", NS_MWG_REGIONS["stArea"])
                width = MetadataParser._readFloatAttributeOrChild(area, "w", NS_MWG_REGIONS["stArea"])
                height = MetadataParser._readFloatAttributeOrChild(area, "h", NS_MWG_REGIONS["stArea"])
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
    def _extractMwgRegionsContext(xmp_content: str) -> Dict[str, Any]:
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

        width = MetadataParser._readIntAttributeOrChild(applied, "w", NS_MWG_REGIONS["stDim"])
        height = MetadataParser._readIntAttributeOrChild(applied, "h", NS_MWG_REGIONS["stDim"])
        unit = MetadataParser._readTextAttributeOrChild(applied, "unit", NS_MWG_REGIONS["stDim"])
        context["mwg_applied_to_dimensions_present"] = True
        context["mwg_applied_to_dimensions"] = {
            "width": width,
            "height": height,
            "unit": unit,
        }
        return context

    @staticmethod
    def _extractXmpTiffOrientation(xmp_content: str) -> Optional[int]:
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

    @staticmethod
    def _readTextAttributeOrChild(node: ET.Element, local_name: str, namespace: str) -> str:
        value = node.get(f"{{{namespace}}}{local_name}")
        if value:
            return value.strip()
        child = node.find(f"{{{namespace}}}{local_name}")
        if child is not None and child.text:
            return child.text.strip()
        return ""

    @staticmethod
    def _readFloatAttributeOrChild(node: ET.Element, local_name: str, namespace: str) -> float:
        value = MetadataParser._readTextAttributeOrChild(node, local_name, namespace)
        return float(value)

    @staticmethod
    def _readIntAttributeOrChild(node: ET.Element, local_name: str, namespace: str) -> Optional[int]:
        value = MetadataParser._readTextAttributeOrChild(node, local_name, namespace)
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parseMicrosoftFaces(xmp_content: str, *, source: str) -> List[MetadataFace]:
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
