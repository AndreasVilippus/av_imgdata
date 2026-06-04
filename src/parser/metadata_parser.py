#!/usr/bin/env python3
from typing import Any, Dict, List, Optional

from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from parser.acd_parser import AcdParser
from parser.iptc_regions_parser import IptcRegionsParser
from parser.microsoft_parser import MicrosoftParser
from parser.mwg_regions_parser import MwgRegionsParser
from parser.xmp_helpers import (
    NS_ACD,
    NS_MICROSOFT,
    NS_MWG_REGIONS,
    extract_xmp_tiff_orientation,
    read_float_attribute_or_child,
    read_int_attribute_or_child,
    read_text_attribute_or_child,
)


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
        use_iptc_ext_regions: bool = True,
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
            if use_iptc_ext_regions:
                faces.extend(self._parseIptcExtRegionsFaces(xmp_content, source=xmp_source or "metadata"))

        xmp_orientation = self._extractXmpTiffOrientation(xmp_content) if xmp_content else None
        if image_orientation is None:
            image_orientation = xmp_orientation

        if image_orientation not in (None, 1):
            for face in faces:
                if face.source_format in {"MWG_REGIONS", "MICROSOFT", "IPTC_EXT_REGIONS"}:
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
        return AcdParser.parse_faces(
            xmp_content,
            source=source,
            filter_unknown=filter_unknown,
            filter_denied=filter_denied,
        )

    @staticmethod
    def _parseMwgRegionsFaces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        return MwgRegionsParser.parse_faces(xmp_content, source=source)

    @staticmethod
    def _parseIptcExtRegionsFaces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        return IptcRegionsParser.parse_faces(xmp_content, source=source)

    @staticmethod
    def _extractMwgRegionsContext(xmp_content: str) -> Dict[str, Any]:
        return MwgRegionsParser.extract_context(xmp_content)

    @staticmethod
    def _extractXmpTiffOrientation(xmp_content: str) -> Optional[int]:
        return extract_xmp_tiff_orientation(xmp_content)

    @staticmethod
    def _readTextAttributeOrChild(node: Any, local_name: str, namespace: str) -> str:
        return read_text_attribute_or_child(node, local_name, namespace)

    @staticmethod
    def _readFloatAttributeOrChild(node: Any, local_name: str, namespace: str) -> float:
        return read_float_attribute_or_child(node, local_name, namespace)

    @staticmethod
    def _readIntAttributeOrChild(node: Any, local_name: str, namespace: str) -> Optional[int]:
        return read_int_attribute_or_child(node, local_name, namespace)

    @staticmethod
    def _parseMicrosoftFaces(xmp_content: str, *, source: str) -> List[MetadataFace]:
        return MicrosoftParser.parse_faces(xmp_content, source=source)
