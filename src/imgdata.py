#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from time import monotonic
from threading import Lock, Thread
from typing import Any, Callable, Dict, List, Optional, Tuple

from api.session_manager import SessionBootstrapRequired, SessionManager, SessionManagerError
from handler.core_handler import CoreHandler
from handler.exiftool_handler import ExifToolHandler
from handler.file_handler import FileHandler
from handler.photos_handler import PhotosHandler
from models.file_face import FileFace
from models.metadata_face import MetadataFace
from models.metadata_payload import MetadataPayload
from models.photos_face import PhotosFace
from parser.metadata_parser import MetadataParser, NS_ACD, NS_MICROSOFT, NS_MWG_REGIONS
from services.bbox_normalizer import denormalize_xmp_face, from_photos, from_xmp, to_display_face
from services.config_service import ConfigService
from services.exiftool_service import ExifToolService
from services.face_matcher import FaceMatcher, compute
from services.file_analysis_service import FileAnalysisService
from services.name_mapping_service import NameMappingService


class ImgDataService:
    """Orchestrates business use-cases across Photos and file handlers."""
    FACE_MATCH_KEEPALIVE_INTERVAL_SECONDS = 180

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.config = ConfigService()
        self.exiftool = ExifToolService(self.config)
        self.exiftool_handler = ExifToolHandler(self.config)
        self.core = CoreHandler(session_manager)
        self.photos = PhotosHandler(session_manager, self.config)
        self.files = FileHandler(self.config)
        self.metadata_parser = MetadataParser()
        self.name_mappings = NameMappingService()
        self.face_matcher = FaceMatcher()
        self.file_analysis = FileAnalysisService()
        self._face_matching_progress: Dict[str, Dict[str, Any]] = {}
        self._face_matching_progress_lock = Lock()
        self._face_matching_threads: Dict[str, Thread] = {}
        self._checks_progress: Dict[str, Dict[str, Any]] = {}
        self._checks_progress_lock = Lock()
        self._checks_threads: Dict[str, Thread] = {}
        self._checks_candidate_paths_cache: Dict[str, Dict[str, Any]] = {}
        self._checks_candidate_paths_cache_lock = Lock()
        self._cleanup_progress: Dict[str, Dict[str, Any]] = {}
        self._cleanup_progress_lock = Lock()
        self._cleanup_threads: Dict[str, Thread] = {}
        self._file_analysis_progress: Dict[str, Any] = {}
        self._file_analysis_progress_lock = Lock()
        self._file_analysis_thread: Optional[Thread] = None

    def update_session_context(
        self,
        *,
        user_key: str,
        base_url: str,
        kk_message: Optional[str] = None,
        synotoken: Optional[str] = None,
        account: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        self.session_manager.update_context(
            user_key,
            base_url=base_url,
            kk_message=kk_message,
            synotoken=synotoken,
            account=account,
            cookies=cookies,
        )

    def status_persons(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, int]:
        status = self.photos.person_status(user_key=user_key, cookies=cookies, base_url=base_url)
        status["mappings"] = len(self.name_mappings.readNameMappings())
        return status

    def status_system(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, str]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        return {"shared_folder": shared_folder or ""}

    def exiftool_status(self) -> Dict[str, Any]:
        return self.exiftool.getStatus()

    def exiftool_extensions(self) -> Dict[str, Any]:
        return self.exiftool.getSupportedReadableExtensions()

    def install_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.installLatest()

    def remove_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.removeInstalled()

    def _readImageMetadata(self, image_path: str, *, include_unnamed_acd: bool = False) -> MetadataPayload:
        config = self.config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))
        use_exiftool_for_sidecars = bool(files_config.get("USE_EXIFTOOL_FOR_SIDECARS", False))
        prefer_exiftool_for_context = bool(files_config.get("PREFER_EXIFTOOL_FOR_CONTEXT", False))
        exiftool_available = use_exiftool and self.exiftool_handler.isAvailable()

        xmp_path = self.files.findXmpForImage(image_path)
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path and use_exiftool_for_sidecars and exiftool_available else self.files.loadXmpFromFile(xmp_path)
        xmp_source = "xmp_file" if xmp_content else ""

        if not xmp_content and exiftool_available:
            xmp_content = self.exiftool_handler.loadEmbeddedXmp(image_path)
            xmp_source = "embedded_xmp_exiftool" if xmp_content else ""

        if not xmp_content:
            xmp_content = self.files.loadXmpFromImageParsed(image_path)
            xmp_source = "embedded_xmp_parsed" if xmp_content else ""

        if prefer_exiftool_for_context and exiftool_available:
            image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
            image_orientation = self.exiftool_handler.readImageOrientation(image_path)
            if not image_dimensions.get("width") or not image_dimensions.get("height"):
                image_dimensions = self.files.readImageDimensions(image_path)
            if image_orientation is None:
                image_orientation = self.files.readJpegExifOrientation(image_path)
        else:
            image_dimensions = self.files.readImageDimensions(image_path)
            image_orientation = self.files.readJpegExifOrientation(image_path)
            if (not image_dimensions.get("width") or not image_dimensions.get("height")) and exiftool_available:
                image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
            if image_orientation is None and exiftool_available:
                image_orientation = self.exiftool_handler.readImageOrientation(image_path)
        schemas = self.files.configuredMetadataSchemas()
        return self.metadata_parser.parse(
            image_path=image_path,
            xmp_content=xmp_content,
            xmp_path=xmp_path or "",
            xmp_source=xmp_source,
            image_dimensions=image_dimensions,
            image_orientation=image_orientation,
            use_acd=schemas["ACD"],
            use_microsoft=schemas["MICROSOFT"],
            use_mwg_regions=schemas["MWG_REGIONS"],
            include_unnamed_acd=include_unnamed_acd,
        )

    def analyzeImageFaceMetadata(self, image_path: str) -> Dict[str, Any]:
        return self.files.analyzeMetadata(self._readImageMetadata(image_path))

    def readAllPersonsFromImage(self, image_path: str) -> List[Dict[str, Any]]:
        return self.files.readAllPersonsFromMetadata(self._readImageMetadata(image_path))

    @staticmethod
    def _sameMetadataFaceCandidate(left: MetadataFace, right: MetadataFace, *, tolerance: float = 1e-6) -> bool:
        if str(left.source_format or "").strip().upper() != str(right.source_format or "").strip().upper():
            return False
        if str(left.name or "").strip() != str(right.name or "").strip():
            return False
        return all(
            abs(float(getattr(left, key, 0.0)) - float(getattr(right, key, 0.0))) <= tolerance
            for key in ("x", "y", "w", "h")
        )

    @staticmethod
    def _findParentMap(root: ET.Element) -> Dict[ET.Element, ET.Element]:
        return {child: parent for parent in root.iter() for child in parent}

    def _acdFaceElements(self, root: ET.Element, *, source: str) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        for description in root.findall(".//rdf:Description", NS_ACD):
            if description.get("{http://ns.acdsee.com/regions/}Type") != "Face":
                continue
            if description.get("{http://ns.acdsee.com/regions/}NameAssignType") == "denied":
                continue
            name = description.get("{http://ns.acdsee.com/regions/}Name")
            if name is None:
                continue
            area = description.find("acdsee-rs:DLYArea", NS_ACD)
            if area is None:
                continue
            try:
                face = MetadataFace.from_center_box(
                    name=str(name or ""),
                    x=float(area.get("{http://ns.acdsee.com/sType/Area#}x")),
                    y=float(area.get("{http://ns.acdsee.com/sType/Area#}y")),
                    w=float(area.get("{http://ns.acdsee.com/sType/Area#}w")),
                    h=float(area.get("{http://ns.acdsee.com/sType/Area#}h")),
                    source=source,
                    source_format="ACD",
                )
            except (TypeError, ValueError):
                continue
            elements.append({"element": description, "face": face})
        return elements

    def _mwgFaceElements(self, root: ET.Element, *, source: str, orientation: Optional[int]) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
        candidates = list(root.findall(".//rdf:Description", NS_MWG_REGIONS)) + list(root.findall(".//rdf:li", NS_MWG_REGIONS))
        for description in candidates:
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
                face = MetadataFace.from_center_box(
                    name=str(
                        description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Name")
                        or (description.findtext("mwg-rs:Name", default="", namespaces=NS_MWG_REGIONS) or "")
                    ),
                    x=MetadataParser._readFloatAttributeOrChild(area, "x", NS_MWG_REGIONS["stArea"]),
                    y=MetadataParser._readFloatAttributeOrChild(area, "y", NS_MWG_REGIONS["stArea"]),
                    w=MetadataParser._readFloatAttributeOrChild(area, "w", NS_MWG_REGIONS["stArea"]),
                    h=MetadataParser._readFloatAttributeOrChild(area, "h", NS_MWG_REGIONS["stArea"]),
                    source=source,
                    source_format="MWG_REGIONS",
                    focus_usage=str(
                        description.get("{http://www.metadataworkinggroup.com/schemas/regions/}FocusUsage")
                        or (description.findtext("mwg-rs:FocusUsage", default="", namespaces=NS_MWG_REGIONS) or "")
                    ),
                    orientation=orientation,
                )
            except (TypeError, ValueError):
                continue
            if orientation not in (None, 1):
                face = MetadataFace.from_dict(face.to_dict())
            elements.append({"element": description, "face": face})
        return elements

    def _microsoftFaceElements(self, root: ET.Element, *, source: str) -> List[Dict[str, Any]]:
        elements: List[Dict[str, Any]] = []
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
                    elif local_name == "PersonDisplayName" and text and not name:
                        name = text
            if not rectangle:
                continue
            try:
                x, y, width, height = [float(value.strip()) for value in rectangle.split(",")]
            except (TypeError, ValueError):
                continue
            face = MetadataFace.from_top_left_box(
                name=name,
                left=x,
                top=y,
                w=width,
                h=height,
                source=source,
                source_format="MICROSOFT",
            )
            elements.append({"element": description, "face": face})
        return elements

    def deleteMetadataFace(self, *, image_path: str, face_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.exiftool_handler.isAvailable():
            return {"deleted": False, "warning": "checks:warning_exiftool_required"}

        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        xmp_path = payload.xmp_path or ""
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path else self.exiftool_handler.loadEmbeddedXmp(image_path)
        if not xmp_content:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        target = MetadataFace.from_dict(face_data if isinstance(face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()
        orientation = MetadataParser._extractXmpTiffOrientation(xmp_content)
        parent_map = self._findParentMap(root)

        if source_format == "ACD":
            candidates = self._acdFaceElements(root, source="metadata")
        elif source_format == "MICROSOFT":
            candidates = self._microsoftFaceElements(root, source="metadata")
        elif source_format == "MWG_REGIONS":
            candidates = self._mwgFaceElements(root, source="metadata", orientation=orientation)
        else:
            candidates = []

        removed = False
        for candidate in candidates:
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            parent = parent_map.get(candidate["element"])
            if parent is None:
                continue
            parent.remove(candidate["element"])
            removed = True
            break

        if not removed:
            return {"deleted": False, "warning": "checks:warning_face_delete_not_found"}

        write_result = self.exiftool_handler.writeXmpDetailed(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "deleted": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_delete_failed",
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
            "details": write_result if not write_result.get("updated") else None,
        }

    @staticmethod
    def _setExistingElementValueByLocalName(element: ET.Element, local_name: str, value: str) -> bool:
        updated = False
        replacement_value = str(value or "").strip()
        for key in list(element.attrib.keys()):
            if key.split("}", 1)[-1] != local_name:
                continue
            element.set(key, replacement_value)
            updated = True
        for child in list(element):
            if child.tag.split("}", 1)[-1] != local_name:
                continue
            child.text = replacement_value
            updated = True
        return updated

    @staticmethod
    def _setMetadataFaceName(element: ET.Element, source_format: str, new_name: str) -> None:
        normalized_format = str(source_format or "").strip().upper()
        replacement_name = str(new_name or "").strip()
        if normalized_format == "ACD":
            if not ImgDataService._setExistingElementValueByLocalName(element, "Name", replacement_name):
                element.set("{http://ns.acdsee.com/regions/}Name", replacement_name)
            return
        if normalized_format == "MICROSOFT":
            if not ImgDataService._setExistingElementValueByLocalName(element, "PersonDisplayName", replacement_name):
                element.append(ET.Element(f"{{{NS_MICROSOFT['MPReg']}}}PersonDisplayName"))
                element[-1].text = replacement_name
            return
        if normalized_format == "MWG_REGIONS":
            if not ImgDataService._setExistingElementValueByLocalName(element, "Name", replacement_name):
                element.set("{http://www.metadataworkinggroup.com/schemas/regions/}Name", replacement_name)

    @staticmethod
    def _formatMetadataFaceCoordinate(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "0"
        formatted = f"{numeric:.6f}".rstrip("0").rstrip(".")
        return formatted or "0"

    @staticmethod
    def _setMetadataFacePosition(
        element: ET.Element,
        source_format: str,
        new_face: MetadataFace,
        *,
        target_orientation: Optional[int] = None,
    ) -> bool:
        normalized_format = str(source_format or "").strip().upper()
        write_face = new_face
        if normalized_format in {"MICROSOFT", "MWG_REGIONS"} and target_orientation not in (None, 1):
            oriented_face = dict(new_face.to_dict())
            oriented_face["orientation"] = target_orientation
            write_face = MetadataFace.from_dict(denormalize_xmp_face(oriented_face))
        w = ImgDataService._formatMetadataFaceCoordinate(write_face.w)
        h = ImgDataService._formatMetadataFaceCoordinate(write_face.h)
        x = ImgDataService._formatMetadataFaceCoordinate(write_face.x)
        y = ImgDataService._formatMetadataFaceCoordinate(write_face.y)

        if normalized_format == "ACD":
            area = element.find("acdsee-rs:DLYArea", NS_ACD)
            if area is None:
                return False
            updated = False
            updated = ImgDataService._setExistingElementValueByLocalName(area, "x", x) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "y", y) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "w", w) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "h", h) or updated
            return updated

        if normalized_format == "MICROSOFT":
            left = ImgDataService._formatMetadataFaceCoordinate(write_face.x - (write_face.w / 2))
            top = ImgDataService._formatMetadataFaceCoordinate(write_face.y - (write_face.h / 2))
            rectangle = ",".join((left, top, w, h))
            if ImgDataService._setExistingElementValueByLocalName(element, "Rectangle", rectangle):
                return True
            element.append(ET.Element(f"{{{NS_MICROSOFT['MPReg']}}}Rectangle"))
            element[-1].text = rectangle
            return True

        if normalized_format == "MWG_REGIONS":
            area = element.find("mwg-rs:Area", NS_MWG_REGIONS)
            if area is None:
                return False
            updated = False
            updated = ImgDataService._setExistingElementValueByLocalName(area, "x", x) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "y", y) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "w", w) or updated
            updated = ImgDataService._setExistingElementValueByLocalName(area, "h", h) or updated
            return updated

        return False

    def replaceMetadataFaceName(self, *, image_path: str, face_data: Dict[str, Any], new_name: str) -> Dict[str, Any]:
        if not self.exiftool_handler.isAvailable():
            return {"updated": False, "warning": "checks:warning_exiftool_required"}

        replacement_name = str(new_name or "").strip()
        if not replacement_name:
            return {"updated": False, "warning": "checks:warning_face_replace_failed"}

        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        xmp_path = payload.xmp_path or ""
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path else self.exiftool_handler.loadEmbeddedXmp(image_path)
        if not xmp_content:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        target = MetadataFace.from_dict(face_data if isinstance(face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()
        orientation = MetadataParser._extractXmpTiffOrientation(xmp_content)

        if source_format == "ACD":
            candidates = self._acdFaceElements(root, source="metadata")
        elif source_format == "MICROSOFT":
            candidates = self._microsoftFaceElements(root, source="metadata")
        elif source_format == "MWG_REGIONS":
            candidates = self._mwgFaceElements(root, source="metadata", orientation=orientation)
        else:
            candidates = []

        updated = False
        for candidate in candidates:
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            self._setMetadataFaceName(candidate["element"], source_format, replacement_name)
            updated = True
            break

        if not updated:
            return {"updated": False, "warning": "checks:warning_face_replace_not_found"}

        write_result = self.exiftool_handler.writeXmpDetailed(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "updated": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_replace_failed",
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
            "details": write_result if not write_result.get("updated") else None,
        }

    @staticmethod
    def _normalizedNameMappingTable(mappings: List[Dict[str, Any]]) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for item in mappings:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or "").strip()
            target_name = str(item.get("target_name") or "").strip()
            if not source_name or not target_name:
                continue
            source_key = NameMappingService._normalize_name_value(source_name)
            if not source_key:
                continue
            lookup[source_key] = target_name
        return lookup

    def normalizeMetadataFaceNamesFromMappings(
        self,
        *,
        image_path: str,
        target_formats: List[str],
        mapping_lookup: Dict[str, str],
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        selected_formats = {
            str(fmt or "").strip().upper()
            for fmt in list(target_formats or [])
            if str(fmt or "").strip()
        }
        selected_formats &= {"ACD", "MICROSOFT", "MWG_REGIONS"}
        if not selected_formats:
            return {"updated": False, "updated_faces": 0, "formats": {}}
        if not self.exiftool_handler.isAvailable():
            return {
                "updated": False,
                "updated_faces": 0,
                "formats": {},
                "warning": "checks:warning_exiftool_required",
            }

        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        xmp_path = payload.xmp_path or ""
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path else self.exiftool_handler.loadEmbeddedXmp(image_path)
        if not xmp_content:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return {"updated": False, "updated_faces": 0, "formats": {}}

        orientation = MetadataParser._extractXmpTiffOrientation(xmp_content)
        candidates: List[Dict[str, Any]] = []
        if "ACD" in selected_formats:
            candidates.extend(self._acdFaceElements(root, source="cleanup"))
        if "MICROSOFT" in selected_formats:
            candidates.extend(self._microsoftFaceElements(root, source="cleanup"))
        if "MWG_REGIONS" in selected_formats:
            candidates.extend(self._mwgFaceElements(root, source="cleanup", orientation=orientation))

        updated_faces = 0
        updated_formats: Dict[str, int] = {}
        for candidate in candidates:
            if callable(should_stop) and should_stop():
                return {"updated": False, "updated_faces": 0, "formats": {}, "stopped": True}
            face = candidate.get("face")
            element = candidate.get("element")
            if not isinstance(face, MetadataFace) or not isinstance(element, ET.Element):
                continue
            current_name = str(face.name or "").strip()
            if not current_name:
                continue
            source_key = NameMappingService._normalize_name_value(current_name)
            target_name = str(mapping_lookup.get(source_key) or "").strip()
            if not target_name:
                continue
            if NameMappingService._normalize_name_value(target_name) == source_key:
                continue
            source_format = str(face.source_format or "").strip().upper()
            self._setMetadataFaceName(element, source_format, target_name)
            updated_faces += 1
            updated_formats[source_format] = updated_formats.get(source_format, 0) + 1

        if updated_faces == 0:
            return {"updated": False, "updated_faces": 0, "formats": {}}
        if callable(should_stop) and should_stop():
            return {"updated": False, "updated_faces": 0, "formats": {}, "stopped": True}

        write_result = self.exiftool_handler.writeXmpDetailed(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "updated": bool(write_result.get("updated")),
            "updated_faces": updated_faces if write_result.get("updated") else 0,
            "formats": updated_formats if write_result.get("updated") else {},
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
            "details": write_result if not write_result.get("updated") else None,
        }

    def replaceMetadataFacePosition(
        self,
        *,
        image_path: str,
        face_data: Dict[str, Any],
        source_face_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.exiftool_handler.isAvailable():
            return {"updated": False, "warning": "checks:warning_exiftool_required"}

        payload = self._readImageMetadata(image_path)
        if not payload.has_xmp:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        xmp_path = payload.xmp_path or ""
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path else self.exiftool_handler.loadEmbeddedXmp(image_path)
        if not xmp_content:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        try:
            root = ET.fromstring(xmp_content)
        except ET.ParseError:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        target = MetadataFace.from_dict(face_data if isinstance(face_data, dict) else {})
        source_face = MetadataFace.from_dict(source_face_data if isinstance(source_face_data, dict) else {})
        source_format = str(target.source_format or "").strip().upper()
        orientation = MetadataParser._extractXmpTiffOrientation(xmp_content)

        if source_format == "ACD":
            candidates = self._acdFaceElements(root, source="metadata")
        elif source_format == "MICROSOFT":
            candidates = self._microsoftFaceElements(root, source="metadata")
        elif source_format == "MWG_REGIONS":
            candidates = self._mwgFaceElements(root, source="metadata", orientation=orientation)
        else:
            candidates = []

        updated = False
        for candidate in candidates:
            if not self._sameMetadataFaceCandidate(candidate["face"], target):
                continue
            updated = self._setMetadataFacePosition(
                candidate["element"],
                source_format,
                source_face,
                target_orientation=target.orientation,
            )
            break

        if not updated:
            return {"updated": False, "warning": "checks:warning_face_position_replace_not_found"}

        write_result = self.exiftool_handler.writeXmpDetailed(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "updated": bool(write_result.get("updated")),
            "warning": "" if write_result.get("updated") else "checks:warning_face_position_replace_failed",
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
            "details": write_result if not write_result.get("updated") else None,
        }

    def _setFaceMatchingProgress(self, user_key: str, **updates: Any) -> None:
        with self._face_matching_progress_lock:
            current = dict(self._face_matching_progress.get(user_key, {}))
            current.update(updates)
            self._face_matching_progress[user_key] = current

    def _setFaceMatchingProgressMessage(
        self,
        user_key: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
        }
        payload.update(updates)
        self._setFaceMatchingProgress(user_key, **payload)

    def _buildFaceMatchResumeCursor(
        self,
        *,
        skip_face_ids: List[int],
        skip_targets: Optional[List[str]] = None,
        transferred_count: int,
        auto: bool,
        save_only: bool,
        action: str = "search_photo_face_in_file",
    ) -> Dict[str, Any]:
        return {
            "skip_face_ids": sorted({int(face_id) for face_id in skip_face_ids if isinstance(face_id, int)}),
            "skip_targets": [str(value) for value in (skip_targets or []) if str(value or "").strip()],
            "transferred_count": int(transferred_count),
            "auto": bool(auto),
            "save_only": bool(save_only),
            "action": str(action or "search_photo_face_in_file"),
        }

    def getFaceMatchingProgress(self, user_key: str) -> Dict[str, Any]:
        with self._face_matching_progress_lock:
            current = self._face_matching_progress.get(user_key, {})
        payload = dict(current) if isinstance(current, dict) else {}
        return self._normalizeFaceMatchingProgress(user_key, payload)

    def _normalizeFaceMatchingProgress(self, user_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        worker = self._face_matching_threads.get(user_key)
        worker_alive = bool(worker and worker.is_alive())
        if current.get("running") and not worker_alive:
            current["running"] = False
            current["stop_requested"] = False
            if "finished" not in current:
                current["finished"] = True
            if not current.get("message"):
                current["message"] = "Last face matching job is no longer running."
        return current

    def requestStopFaceMatching(self, user_key: str) -> Dict[str, Any]:
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:progress_stopping",
            stop_requested=True,
        )
        return self.getFaceMatchingProgress(user_key)

    def _shouldStopFaceMatching(self, user_key: str) -> bool:
        progress = self.getFaceMatchingProgress(user_key)
        return bool(progress.get("stop_requested"))

    def _refreshFaceMatchingSessionIfNeeded(
        self,
        *,
        user_key: str,
        base_url: str,
        last_keepalive_at: float,
    ) -> float:
        now = monotonic()
        if now - last_keepalive_at < self.FACE_MATCH_KEEPALIVE_INTERVAL_SECONDS:
            return last_keepalive_at
        self.session_manager.keepalive(user_key, base_url=base_url)
        return now

    def _setChecksProgress(self, user_key: str, **updates: Any) -> None:
        check_type = self._normalizeChecksType(updates.get("check_type"))
        state_key = self._checksStateKey(user_key, check_type)
        with self._checks_progress_lock:
            current = dict(self._checks_progress.get(state_key, {}))
            current.update(updates)
            current["check_type"] = check_type
            current["last_updated_at"] = self._timestamp_now()
            self._checks_progress[state_key] = current
        self.file_analysis.writeRuntimeState("checks_progress", state_key, current)

    def _setChecksProgressMessage(
        self,
        user_key: str,
        check_type: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
            "check_type": self._normalizeChecksType(check_type),
        }
        payload.update(updates)
        self._setChecksProgress(user_key, **payload)

    @staticmethod
    def _normalizeChecksType(check_type: Any) -> str:
        normalized = str(check_type or "dimension_issues").strip().lower()
        if normalized not in {"dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts"}:
            return "dimension_issues"
        return normalized

    def _checksStateKey(self, user_key: str, check_type: Any) -> str:
        return f"{user_key}_{self._normalizeChecksType(check_type)}"

    def _invalidateChecksCandidatePathsCache(self, user_key: str, check_type: Any) -> None:
        state_key = self._checksStateKey(user_key, check_type)
        with self._checks_candidate_paths_cache_lock:
            self._checks_candidate_paths_cache.pop(state_key, None)

    def _getChecksCandidatePaths(
        self,
        *,
        user_key: str,
        check_type: Any,
        shared_folder: str,
        use_cache: bool = True,
    ) -> List[str]:
        state_key = self._checksStateKey(user_key, check_type)
        normalized_shared_folder = str(shared_folder or "").strip()
        if not normalized_shared_folder:
            return []

        if use_cache:
            with self._checks_candidate_paths_cache_lock:
                cached = self._checks_candidate_paths_cache.get(state_key)
                if (
                    isinstance(cached, dict)
                    and str(cached.get("shared_folder") or "") == normalized_shared_folder
                    and isinstance(cached.get("paths"), list)
                ):
                    return list(cached.get("paths") or [])

        candidate_paths = self.files.listImageFiles(normalized_shared_folder)
        with self._checks_candidate_paths_cache_lock:
            self._checks_candidate_paths_cache[state_key] = {
                "shared_folder": normalized_shared_folder,
                "paths": list(candidate_paths),
            }
        return candidate_paths

    def _normalizeChecksProgress(self, user_key: str, check_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        normalized_type = self._normalizeChecksType(check_type or current.get("check_type"))
        current["check_type"] = normalized_type
        worker = self._checks_threads.get(self._checksStateKey(user_key, normalized_type))
        if current.get("running") and worker is not None and not worker.is_alive():
            current["running"] = False
            current["finished"] = True
            if not current.get("message"):
                current["message"] = "Last checks scan is no longer running."
            self.file_analysis.writeRuntimeState("checks_progress", self._checksStateKey(user_key, normalized_type), current)
        return current

    def getChecksProgress(self, user_key: str, check_type: str) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        state_key = self._checksStateKey(user_key, normalized_type)
        current = self.file_analysis.readRuntimeState("checks_progress", state_key)
        if not isinstance(current, dict) or not current:
            with self._checks_progress_lock:
                current = self._checks_progress.get(state_key, {})
        return self._normalizeChecksProgress(user_key, normalized_type, dict(current) if isinstance(current, dict) else {})

    def requestStopChecks(self, user_key: str, check_type: str) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        self._setChecksProgressMessage(
            user_key,
            normalized_type,
            "checks:progress_stopping",
            stop_requested=True,
        )
        return self.getChecksProgress(user_key, normalized_type)

    def _shouldStopChecks(self, user_key: str, check_type: str) -> bool:
        progress = self.getChecksProgress(user_key, check_type)
        return bool(progress.get("stop_requested"))

    @staticmethod
    def _normalizeCleanupAction(action: Any) -> str:
        normalized = str(action or "normalize_names").strip().lower()
        return normalized if normalized in {"normalize_names"} else "normalize_names"

    @staticmethod
    def _normalizeCleanupTargets(targets: Any) -> List[str]:
        # Cleanup name normalization must never rewrite or merge Photos persons.
        allowed = {"ACD", "MICROSOFT", "MWG_REGIONS"}
        normalized: List[str] = []
        for item in list(targets or []):
            target = str(item or "").strip().upper()
            if target not in allowed or target in normalized:
                continue
            normalized.append(target)
        return normalized

    def _cleanupStateKey(self, user_key: str, action: Any) -> str:
        return f"{user_key}_{self._normalizeCleanupAction(action)}"

    def _normalizeCleanupProgress(self, user_key: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        normalized_action = self._normalizeCleanupAction(action or current.get("action"))
        current["action"] = normalized_action
        current["targets"] = self._normalizeCleanupTargets(current.get("targets"))
        worker = self._cleanup_threads.get(self._cleanupStateKey(user_key, normalized_action))
        worker_alive = worker.is_alive() if worker is not None else False
        if current.get("running") and not worker_alive:
            current["running"] = False
            current["finished"] = True
            if not current.get("message"):
                current["message"] = "Last cleanup job is no longer running."
            self.file_analysis.writeRuntimeState("cleanup_progress", self._cleanupStateKey(user_key, normalized_action), current)
        return current

    def _setCleanupProgress(self, user_key: str, **updates: Any) -> Dict[str, Any]:
        action = self._normalizeCleanupAction(updates.get("action"))
        state_key = self._cleanupStateKey(user_key, action)
        with self._cleanup_progress_lock:
            current = dict(self._cleanup_progress.get(state_key, {}))
            current.update(updates)
            current["action"] = action
            current["targets"] = self._normalizeCleanupTargets(current.get("targets"))
            self._cleanup_progress[state_key] = current
        self.file_analysis.writeRuntimeState("cleanup_progress", state_key, current)
        return current

    def _setCleanupProgressMessage(
        self,
        user_key: str,
        action: str,
        message_key: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **updates: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "message_key": message_key,
            "message_params": message_params or {},
            "message": message or message_key,
            "action": self._normalizeCleanupAction(action),
        }
        payload.update(updates)
        self._setCleanupProgress(user_key, **payload)

    def getCleanupProgress(self, user_key: str, action: str = "normalize_names") -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        state_key = self._cleanupStateKey(user_key, normalized_action)
        current = self.file_analysis.readRuntimeState("cleanup_progress", state_key)
        if not isinstance(current, dict) or not current:
            with self._cleanup_progress_lock:
                current = self._cleanup_progress.get(state_key, {})
        return self._normalizeCleanupProgress(user_key, normalized_action, dict(current) if isinstance(current, dict) else {})

    def requestStopCleanup(self, user_key: str, action: str = "normalize_names") -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        self._setCleanupProgressMessage(
            user_key,
            normalized_action,
            "cleanup:progress_stopping",
            stop_requested=True,
        )
        return self.getCleanupProgress(user_key, normalized_action)

    def _shouldStopCleanup(self, user_key: str, action: str) -> bool:
        progress = self.getCleanupProgress(user_key, action)
        return bool(progress.get("stop_requested"))

    @staticmethod
    def _buildChecksResumeCursor(
        *,
        path_index: int,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
        source_mode: str,
        check_type: str,
        save_only: bool,
        findings_count: int,
    ) -> Dict[str, Any]:
        return {
            "path_index": max(0, int(path_index)),
            "pending_entries": list(pending_entries or []),
            "source_mode": str(source_mode or "scan"),
            "check_type": str(check_type or "dimension_issues"),
            "save_only": bool(save_only),
            "findings_count": max(0, int(findings_count)),
        }

    def _buildChecksScanPayload(
        self,
        *,
        check_type: str,
        save_only: bool,
        files_scanned: int,
        total_files: int,
        findings_count: int,
        path_index: int,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
        current_path: str = "",
        result: Optional[Dict[str, Any]] = None,
        message_key: str = "",
        message: str = "",
        message_params: Optional[Dict[str, Any]] = None,
        running: bool = False,
        finished: bool = True,
        stop_requested: bool = False,
    ) -> Dict[str, Any]:
        return {
            "running": running,
            "finished": finished,
            "stop_requested": stop_requested,
            "source_mode": "scan",
            "check_type": check_type,
            "save_only": save_only,
            "files_scanned": files_scanned,
            "total_files": total_files,
            "findings_count": findings_count,
            "current_path": current_path,
            "result": result,
            "resume_cursor": self._buildChecksResumeCursor(
                path_index=path_index,
                pending_entries=pending_entries,
                source_mode="scan",
                check_type=check_type,
                save_only=save_only,
                findings_count=findings_count,
            ),
            "message_key": message_key,
            "message": message,
            "message_params": message_params or {},
        }

    def _buildCheckEntriesForType(
        self,
        *,
        image_path: str,
        review_type: str,
        analysis: Optional[Dict[str, Any]] = None,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        normalized_type = str(review_type or "").strip().lower()
        if normalized_type == "dimension_issues":
            entry = self._buildDimensionMismatchReviewEntry(image_path, analysis)
            return [entry] if entry else []
        if normalized_type == "duplicate_faces":
            return self._buildDuplicateFaceReviewEntries(image_path, analysis)
        if normalized_type == "position_deviations":
            comparison_faces = photo_faces
            if comparison_faces is None and self._configuredAnalysisChecks().get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"):
                comparison_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                )
            return self._buildPositionDeviationReviewEntries(image_path, analysis, comparison_faces)
        if normalized_type == "name_conflicts":
            comparison_faces = photo_faces
            if comparison_faces is None and self._configuredAnalysisChecks().get("NAME_CONFLICTS_INCLUDE_PHOTOS"):
                comparison_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                )
            return self._buildNameConflictReviewEntries(image_path, analysis, comparison_faces)
        return []

    def _writeChecksFindings(
        self,
        *,
        check_type: str,
        status: str,
        shared_folder: str,
        source_mode: str,
        save_only: bool,
        entries: List[Dict[str, Any]],
    ) -> bool:
        payload = {
            "status": status,
            "shared_folder": shared_folder,
            "source_mode": source_mode,
            "check_type": check_type,
            "save_only": save_only,
            "count": len(entries),
            "paths": sorted({
                str(entry.get("image_path") or "").strip()
                for entry in entries
                if isinstance(entry, dict) and str(entry.get("image_path") or "").strip()
            }),
            "entries": entries,
            "finished_at": self._timestamp_now(),
        }
        return self.file_analysis.writeCheckFindings(check_type, payload)

    def getChecksFindingEntries(self, *, check_type: str) -> Dict[str, Any]:
        findings = self.file_analysis.readCheckFindings(check_type)
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        return {
            "status": str(findings.get("status") or ""),
            "check_type": str(findings.get("check_type") or check_type),
            "source_mode": str(findings.get("source_mode") or "findings"),
            "save_only": bool(findings.get("save_only")),
            "count": len(entries),
            "entries": entries,
        }

    def refreshChecksFindingEntries(
        self,
        *,
        check_type: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        findings = self.file_analysis.readCheckFindings(normalized_type)
        if not isinstance(findings, dict) or not isinstance(findings.get("entries"), list):
            return self.getChecksFindingEntries(check_type=normalized_type)

        shared_folder = str(findings.get("shared_folder") or "")
        status = str(findings.get("status") or "finished")
        source_mode = str(findings.get("source_mode") or "findings")
        save_only = bool(findings.get("save_only"))
        stored_entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        candidate_paths: List[str] = []
        seen_paths = set()
        for entry in stored_entries:
            if not isinstance(entry, dict):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            if not image_path or image_path in seen_paths:
                continue
            seen_paths.add(image_path)
            candidate_paths.append(image_path)

        refreshed_entries: List[Dict[str, Any]] = []
        for image_path in candidate_paths:
            refreshed_entries.extend(
                self._buildCheckEntriesForType(
                    image_path=image_path,
                    review_type=normalized_type,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
            )

        self._writeChecksFindings(
            check_type=normalized_type,
            status=status,
            shared_folder=shared_folder,
            source_mode=source_mode,
            save_only=save_only,
            entries=refreshed_entries,
        )
        return self.getChecksFindingEntries(check_type=normalized_type)

    def refreshChecksFindingEntriesForImage(
        self,
        *,
        check_type: str,
        image_path: str,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        normalized_path = str(image_path or "").strip()
        if not normalized_path:
            return self.getChecksFindingEntries(check_type=normalized_type)

        findings = self.file_analysis.readCheckFindings(normalized_type)
        existing_entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        if not existing_entries:
            return self.getChecksFindingEntries(check_type=normalized_type)

        photo_faces = self._loadPhotoFacesForImageWithOverride(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=normalized_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )
        rebuilt_entries = self._buildCheckEntriesForType(
            image_path=normalized_path,
            review_type=normalized_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            photo_faces=photo_faces,
        )

        updated_entries: List[Dict[str, Any]] = []
        replaced = False
        for entry in existing_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("image_path") or "").strip() == normalized_path:
                if not replaced:
                    updated_entries.extend(rebuilt_entries)
                    replaced = True
                continue
            updated_entries.append(entry)

        if not replaced:
            return self.getChecksFindingEntries(check_type=normalized_type)

        self._writeChecksFindings(
            check_type=normalized_type,
            status=str(findings.get("status") or "finished"),
            shared_folder=str(findings.get("shared_folder") or ""),
            source_mode=str(findings.get("source_mode") or "findings"),
            save_only=bool(findings.get("save_only")),
            entries=updated_entries,
        )
        return self.getChecksFindingEntries(check_type=normalized_type)

    def refreshChecksScanProgressForImage(
        self,
        *,
        user_key: str,
        check_type: str,
        image_path: str,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_type = self._normalizeChecksType(check_type)
        normalized_path = str(image_path or "").strip()
        if not normalized_path:
            return self.getChecksProgress(user_key, normalized_type)

        current = self.getChecksProgress(user_key, normalized_type)
        if not isinstance(current, dict) or str(current.get("source_mode") or "").strip().lower() != "scan":
            return current

        resume_cursor = current.get("resume_cursor") if isinstance(current.get("resume_cursor"), dict) else {}
        pending_entries = resume_cursor.get("pending_entries") if isinstance(resume_cursor.get("pending_entries"), list) else []
        current_result = current.get("result") if isinstance(current.get("result"), dict) else {}
        current_entry = current_result.get("entry") if isinstance(current_result.get("entry"), dict) else {}

        old_image_entries_count = 0
        if str(current_entry.get("image_path") or "").strip() == normalized_path:
            old_image_entries_count += 1
        for entry in pending_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("image_path") or "").strip() == normalized_path:
                old_image_entries_count += 1

        photo_faces = self._loadPhotoFacesForImageWithOverride(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=normalized_path,
            original_face_data=original_face_data,
            replacement_face_data=replacement_face_data,
        )
        rebuilt_entries = self._buildCheckEntriesForType(
            image_path=normalized_path,
            review_type=normalized_type,
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            photo_faces=photo_faces,
        )

        remaining_pending_entries: List[Dict[str, Any]] = []
        for entry in pending_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("image_path") or "").strip() == normalized_path:
                continue
            remaining_pending_entries.append(entry)
        remaining_pending_entries = rebuilt_entries + remaining_pending_entries

        findings_count = int(current.get("findings_count") or 0)
        findings_count = max(0, findings_count - old_image_entries_count + len(rebuilt_entries))

        updated_resume_cursor = self._buildChecksResumeCursor(
            path_index=int(resume_cursor.get("path_index") or 0),
            pending_entries=remaining_pending_entries,
            source_mode=str(resume_cursor.get("source_mode") or "scan"),
            check_type=str(resume_cursor.get("check_type") or normalized_type),
            save_only=bool(resume_cursor.get("save_only", current.get("save_only"))),
            findings_count=findings_count,
        )

        updated_progress = dict(current)
        updated_progress.update({
            "check_type": normalized_type,
            "findings_count": findings_count,
            "result": None,
            "resume_cursor": updated_resume_cursor,
        })
        self._setChecksProgress(user_key, **updated_progress)
        return self.getChecksProgress(user_key, normalized_type)

    def _getSuggestedNameConflictRename(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict) or str(item.get("review_type") or "").strip().lower() != "name_conflicts":
            return None

        left_state = str(item.get("left_state") or "").strip().lower()
        right_state = str(item.get("right_state") or "").strip().lower()
        left_face = item.get("left_face_target") if isinstance(item.get("left_face_target"), dict) else item.get("left_face")
        right_face = item.get("right_face_target") if isinstance(item.get("right_face_target"), dict) else item.get("right_face")
        left_name = str(item.get("left_name") or "").strip()
        right_name = str(item.get("right_name") or "").strip()

        if right_state == "suggested" and isinstance(left_face, dict) and right_name:
            return {
                "face": left_face,
                "new_name": right_name,
                "source_name": str(left_face.get("name") or "").strip(),
            }
        if left_state == "suggested" and isinstance(right_face, dict) and left_name:
            return {
                "face": right_face,
                "new_name": left_name,
                "source_name": str(right_face.get("name") or "").strip(),
            }
        return None

    def _getSuggestedDuplicateFaceDeletion(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict) or str(item.get("review_type") or "").strip().lower() != "duplicate_faces":
            return None

        left_state = str(item.get("left_state") or "").strip().lower()
        right_state = str(item.get("right_state") or "").strip().lower()
        left_face = item.get("left_face_target") if isinstance(item.get("left_face_target"), dict) else item.get("left_face")
        right_face = item.get("right_face_target") if isinstance(item.get("right_face_target"), dict) else item.get("right_face")

        if left_state == "suggested" and right_state != "suggested" and isinstance(right_face, dict):
            return {
                "face": right_face,
                "kept_side": "left",
                "removed_side": "right",
            }
        if right_state == "suggested" and left_state != "suggested" and isinstance(left_face, dict):
            return {
                "face": left_face,
                "kept_side": "right",
                "removed_side": "left",
            }
        return None

    def _resolveChecksReviewEntry(
        self,
        *,
        entry: Dict[str, Any],
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Dict[str, Any]:
        normalized_entry = dict(entry or {})
        auto_applied_count = 0

        while True:
            item = self.getChecksReviewItem(
                entry=normalized_entry,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if not item:
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                }

            action = (
                self._getSuggestedNameConflictRename(item)
                if auto_apply_suggested_names
                else None
            )
            delete_action = (
                self._getSuggestedDuplicateFaceDeletion(item)
                if auto_apply_suggested_duplicates
                else None
            )
            if not action:
                if not delete_action:
                    return {
                        "entry": normalized_entry,
                        "item": item,
                        "auto_applied_count": auto_applied_count,
                    }
            if delete_action:
                result = self.deleteMetadataFace(
                    image_path=str(item.get("image_path") or ""),
                    face_data=delete_action["face"],
                )
                if not result.get("deleted"):
                    return {
                        "entry": normalized_entry,
                        "item": item,
                        "auto_applied_count": auto_applied_count,
                        "auto_apply_warning": str(result.get("warning") or ""),
                    }
                auto_applied_count += 1
                next_entry = next(
                    iter(
                        self._buildCheckEntriesForType(
                            image_path=str(item.get("image_path") or ""),
                            review_type=str(item.get("review_type") or ""),
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            shared_folder=shared_folder,
                        )
                    ),
                    None,
                )
                if not next_entry:
                    return {
                        "entry": None,
                        "item": None,
                        "auto_applied_count": auto_applied_count,
                    }
                normalized_entry = next_entry
                continue
            if not action:
                return {
                    "entry": normalized_entry,
                    "item": item,
                    "auto_applied_count": auto_applied_count,
                }

            result = self.replaceChecksFaceName(
                user_key=str(user_key or ""),
                cookies=dict(cookies or {}),
                base_url=base_url,
                image_path=str(item.get("image_path") or ""),
                face_data=action["face"],
                new_name=str(action["new_name"] or ""),
            )
            if not result.get("updated"):
                return {
                    "entry": normalized_entry,
                    "item": item,
                    "auto_applied_count": auto_applied_count,
                    "auto_apply_warning": str(result.get("warning") or ""),
                }

            auto_applied_count += 1
            next_entry = next(
                iter(
                    self._buildCheckEntriesForType(
                        image_path=str(item.get("image_path") or ""),
                        review_type=str(item.get("review_type") or ""),
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                    )
                ),
                None,
            )
            if not next_entry:
                return {
                    "entry": None,
                    "item": None,
                    "auto_applied_count": auto_applied_count,
                }
            normalized_entry = next_entry

    def _runFaceMatching(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        limit: int,
        offset: int,
        skip_face_ids: Optional[List[int]],
        skip_targets: Optional[List[str]],
        auto: bool,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            self.session_manager.keepalive(user_key, base_url=base_url)
            if action == "search_file_face_in_sources":
                result = self.searchFileFaceInSources(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    skip_targets=skip_targets,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            elif action == "mark_missing_photos_faces":
                result = self.searchMissingPhotosFaces(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    skip_targets=skip_targets,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            else:
                result = self.searchPhotoFaceInFile(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    limit=limit,
                    offset=offset,
                    skip_face_ids=skip_face_ids,
                    auto=auto,
                    save_only=save_only,
                    resume_cursor=resume_cursor,
                )
            self._setFaceMatchingProgress(
                user_key,
                result=result,
                finished=True,
                action=action,
                auto=auto,
                save_only=save_only,
            )
        except (SessionBootstrapRequired, SessionManagerError) as exc:
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_auth_required",
                message=str(exc),
                running=False,
                finished=False,
                paused=True,
                auth_required=True,
                error=str(exc),
                action=action,
                auto=auto,
                save_only=save_only,
                resume_cursor=resume_cursor or self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids or []),
                    skip_targets=list(skip_targets or []),
                    transferred_count=0,
                    auto=auto,
                    save_only=save_only,
                    action=action,
                ),
            )
        except Exception as exc:
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_failed",
                message="Face matching failed.",
                running=False,
                finished=True,
                paused=False,
                auth_required=False,
                error=str(exc),
                action=action,
                auto=auto,
                save_only=save_only,
            )
        finally:
            self._face_matching_threads.pop(user_key, None)

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def _setFileAnalysisProgress(self, **updates: Any) -> None:
        with self._file_analysis_progress_lock:
            current = dict(self._file_analysis_progress)
            current.update(updates)
            self._file_analysis_progress = current

    def _normalizeFileAnalysisProgress(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        worker_alive = bool(self._file_analysis_thread and self._file_analysis_thread.is_alive())
        if current.get("running") and not worker_alive:
            current["running"] = False
            current["finished"] = True
            current["stopped"] = bool(current.get("stopped")) or current.get("status") != "finished"
            current["stop_requested"] = False
            if current.get("status") == "running":
                current["status"] = "stopped"
            if not current.get("finished_at"):
                current["finished_at"] = current.get("last_updated_at") or self._timestamp_now()
            if not current.get("message"):
                current["message"] = "Last file analysis is no longer running."
        return current

    def _enrichFileAnalysisProgressWithFindings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload) if isinstance(payload, dict) else {}
        field_map = {
            "dimension_issues": ["files_with_mwg_dimension_mismatch", "files_with_dimension_issues"],
            "duplicate_faces": ["files_with_duplicate_faces"],
            "position_deviations": ["files_with_face_position_deviations"],
            "name_conflicts": ["files_with_name_conflicts"],
        }
        for finding_type, fields in field_map.items():
            findings = self.file_analysis.readCheckFindings(finding_type)
            if not isinstance(findings, dict):
                continue
            findings_count = int(findings.get("count") or 0)
            same_job = (
                not current.get("job_id")
                or not findings.get("job_id")
                or str(current.get("job_id")) == str(findings.get("job_id"))
            )
            if not same_job:
                continue
            for field in fields:
                if field not in current and findings_count >= 0:
                    current[field] = findings_count
        return current

    def getFileAnalysisProgress(self) -> Dict[str, Any]:
        with self._file_analysis_progress_lock:
            current = dict(self._file_analysis_progress)
        if current:
            return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(current))
        latest = self.file_analysis.readLatestResult()
        if not isinstance(latest, dict):
            return {}
        return self._enrichFileAnalysisProgressWithFindings(self._normalizeFileAnalysisProgress(latest))

    def getFaceMatchFindings(self) -> Dict[str, Any]:
        findings = self.file_analysis.readCheckFindings("face_match")
        return findings if isinstance(findings, dict) else {}

    def requestStopFileAnalysis(self) -> Dict[str, Any]:
        self._setFileAnalysisProgress(stop_requested=True, message="Stopping file analysis...")
        return self.getFileAnalysisProgress()

    def _shouldStopFileAnalysis(self) -> bool:
        progress = self.getFileAnalysisProgress()
        return bool(progress.get("stop_requested"))

    def _persistFileAnalysisResult(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.file_analysis.writeLatestResult(payload)
        self._setFileAnalysisProgress(**payload)
        return payload

    def _writeFileAnalysisCheckFindings(
        self,
        *,
        finding_type: str,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        findings: List[Any],
    ) -> None:
        paths: List[str] = []
        entries: List[Dict[str, Any]] = []
        seen_paths = set()
        for finding in findings:
            if isinstance(finding, dict):
                entries.append(finding)
                image_path = str(finding.get("image_path") or "").strip()
                if image_path and image_path not in seen_paths:
                    seen_paths.add(image_path)
                    paths.append(image_path)
                continue
            image_path = str(finding or "").strip()
            if image_path and image_path not in seen_paths:
                seen_paths.add(image_path)
                paths.append(image_path)
        self.file_analysis.writeCheckFindings(
            finding_type,
            {
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": self._timestamp_now() if finished else "",
                "last_updated_at": self._timestamp_now(),
                "status": status,
                "shared_folder": shared_folder,
                "count": len(entries) if entries else len(paths),
                "paths": paths,
                "entries": entries,
            }
        )

    def _writeAllFileAnalysisCheckFindings(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        findings_by_type: Dict[str, List[Any]],
    ) -> None:
        for finding_type, findings in findings_by_type.items():
            self._writeFileAnalysisCheckFindings(
                finding_type=finding_type,
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status=status,
                finished=finished,
                findings=findings,
            )

    def _writeFaceMatchFindings(
        self,
        *,
        status: str,
        shared_folder: str,
        action: str,
        auto: bool,
        save_only: bool,
        transferred_count: int,
        entries: List[Dict[str, Any]],
    ) -> None:
        timestamp = self._timestamp_now()
        self.file_analysis.writeCheckFindings(
            "face_match",
            {
                "job_id": timestamp,
                "started_at": timestamp,
                "finished_at": timestamp,
                "last_updated_at": timestamp,
                "status": status,
                "shared_folder": shared_folder,
                "action": action,
                "auto": auto,
                "save_only": save_only,
                "transferred_count": transferred_count,
                "count": len(entries),
                "entries": entries,
            }
        )

    def _writeReverseFaceMatchCandidates(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        status: str,
        finished: bool,
        entries: List[Dict[str, Any]],
    ) -> None:
        self.file_analysis.writeCheckFindings(
            "face_match_candidates",
            {
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": self._timestamp_now() if finished else "",
                "last_updated_at": self._timestamp_now(),
                "status": status,
                "shared_folder": shared_folder,
                "count": len(entries),
                "entries": entries,
            }
        )

    def _getReverseFaceMatchCandidateEntries(self) -> List[Dict[str, Any]]:
        findings = self.file_analysis.readCheckFindings("face_match_candidates")
        entries = findings.get("entries") if isinstance(findings, dict) and isinstance(findings.get("entries"), list) else []
        normalized_entries: List[Dict[str, Any]] = []
        seen_tokens = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                continue
            token = self._faceMatchTargetToken(image_path=image_path, face=metadata_face)
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            normalized_entries.append({
                "action": "search_file_face_in_sources",
                "image_path": image_path,
                "metadata_face": metadata_face,
            })
        return normalized_entries

    def _buildReverseFaceMatchCandidateEntry(self, *, image_path: str, metadata_face: MetadataFace) -> Dict[str, Any]:
        return {
            "action": "search_file_face_in_sources",
            "image_path": image_path,
            "metadata_face": metadata_face.to_dict(),
        }

    @staticmethod
    def _normalizeFaceMatchEntry(entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(entry or {})
        metadata_face = normalized.get("metadata_face")
        if hasattr(metadata_face, "to_dict"):
            normalized["metadata_face"] = metadata_face.to_dict()
        return normalized

    def _resolveStoredFaceMatchEntry(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        entry: Dict[str, Any],
        known_persons_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalizeFaceMatchEntry(entry)
        resolved = dict(normalized)
        action = str(resolved.get("action") or "search_photo_face_in_file").strip().lower()
        if action in {"search_file_face_in_sources", "mark_missing_photos_faces"}:
            image_path = str(resolved.get("image_path") or "").strip()
            metadata_face = resolved.get("metadata_face")
            if action == "mark_missing_photos_faces":
                source_name = str(resolved.get("source_name") or (metadata_face.get("name") if isinstance(metadata_face, dict) else "") or "").strip()
                matched_person, mapped_assignment, lookup_debug = self._lookupMatchedPersonBySourceName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    source_name=source_name,
                    known_persons_cache=known_persons_cache,
                )
                resolved["source_name"] = source_name
                resolved["matched_person"] = matched_person
                resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
                resolved["name_mapping"] = mapped_assignment
                resolved["lookup_debug"] = lookup_debug
                return resolved
            if image_path and isinstance(metadata_face, dict) and not str(resolved.get("source_name") or "").strip():
                payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
                target_face = self._findFaceBySignature(payload.faces, metadata_face)
                if not target_face or str(target_face.name or "").strip():
                    resolved["matched_person"] = None
                    resolved["matched_person_id"] = None
                    resolved["lookup_debug"] = {}
                    return resolved
                source_scope = self._fileFaceMatchSourceScope()
                use_photos = source_scope in {"both", "photos"}
                use_metadata = source_scope in {"both", "metadata"}
                photo_sources: List[Dict[str, Any]] = []
                if use_photos:
                    known_persons = known_persons_cache if isinstance(known_persons_cache, list) else self.photos.sortPersonsForFaceMatch(
                        self.photos.listFotoTeamPersonKnown(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            show_more=True,
                            show_hidden=False,
                            additional=["thumbnail"],
                        )
                    )
                    shared_folder = self.core.getSharedFolder(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        folder_name="photo",
                    )
                    if shared_folder:
                        for person in known_persons:
                            person_id = person.get("id")
                            try:
                                person_id_int = int(person_id)
                            except (TypeError, ValueError):
                                continue
                            images = self.photos.listFotoTeamItems(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                person_id=person_id_int,
                                additional=["thumbnail"],
                            )
                            for image in images:
                                image_id = image.get("id")
                                folder_id = image.get("folder_id")
                                filename = image.get("filename")
                                try:
                                    image_id_int = int(image_id)
                                    folder_id_int = int(folder_id)
                                except (TypeError, ValueError):
                                    continue
                                if not isinstance(filename, str) or not filename:
                                    continue
                                folder_payload = self.photos.getFotoTeamFolder(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    id_folder=folder_id_int,
                                )
                                folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                                folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                                if not isinstance(folder_name, str) or not folder_name:
                                    continue
                                photo_image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                                if photo_image_path != image_path:
                                    continue
                                faces = self.photos.list_faceFotoTeamItems(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    id_item=image_id_int,
                                )
                                for face in faces:
                                    face_name = str(face.get("face_name") or "").strip()
                                    face_id = face.get("face_id")
                                    if not face_name or face_id is None:
                                        continue
                                    photo_face = dict(face)
                                    photo_face["image"] = image
                                    photo_face["person"] = person
                                    photo_sources.append(photo_face)
                metadata_sources = [
                    face for face in payload.faces
                    if str(face.name or "").strip()
                ] if use_metadata else []
                matched_entry = self._matchFileFaceInSources(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    image_path=image_path,
                    target_face=target_face,
                    photo_sources=photo_sources,
                    metadata_sources=metadata_sources,
                )
                if isinstance(matched_entry, dict):
                    resolved.update(matched_entry)
            source_name = str(resolved.get("source_name") or "").strip()
            if not source_name:
                source_face = resolved.get("source_face")
                if isinstance(source_face, dict):
                    source_name = str(source_face.get("name") or "").strip()
            matched_person = None
            lookup_debug: Dict[str, Any] = {}
            if source_name:
                matched_person = self.photos.findKnownPersonByName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    name=source_name,
                    known_persons=known_persons_cache,
                )
                lookup_debug = self.photos.debugKnownPersonLookup(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    name=source_name,
                    known_persons=known_persons_cache,
                )
            resolved["matched_person"] = matched_person
            resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
            resolved["lookup_debug"] = lookup_debug
            return resolved

        mapped_assignment = resolved.get("name_mapping")
        mapped_target_name = ""
        if isinstance(mapped_assignment, dict):
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()

        metadata_face = resolved.get("metadata_face")
        metadata_name = ""
        if isinstance(metadata_face, dict):
            metadata_name = str(metadata_face.get("name") or "").strip()

        match = resolved.get("match")
        match_name = ""
        if isinstance(match, dict):
            match_name = str(match.get("file_name") or "").strip()

        lookup_name = mapped_target_name or metadata_name or match_name
        if not lookup_name:
            resolved["matched_person"] = None
            resolved["matched_person_id"] = None
            resolved["lookup_debug"] = {}
            return resolved

        matched_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        lookup_debug = self.photos.debugKnownPersonLookup(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        resolved["matched_person"] = matched_person
        resolved["matched_person_id"] = matched_person.get("id") if isinstance(matched_person, dict) else None
        resolved["lookup_debug"] = lookup_debug
        return resolved

    def _persistFaceMatchFindingsEntries(
        self,
        *,
        findings: Dict[str, Any],
        entries: List[Dict[str, Any]],
        transferred_count: int,
    ) -> None:
        if not entries:
            self.file_analysis.deleteCheckFindings("face_match")
            return

        timestamp = self._timestamp_now()
        self.file_analysis.writeCheckFindings(
            "face_match",
            {
                "job_id": str(findings.get("job_id") or timestamp),
                "started_at": str(findings.get("started_at") or timestamp),
                "finished_at": str(findings.get("finished_at") or timestamp),
                "last_updated_at": timestamp,
                "status": str(findings.get("status") or "finished"),
                "shared_folder": str(findings.get("shared_folder") or ""),
                "action": str(findings.get("action") or "search_photo_face_in_file"),
                "auto": bool(findings.get("auto")),
                "save_only": bool(findings.get("save_only")),
                "transferred_count": int(transferred_count),
                "count": len(entries),
                "entries": entries,
            },
        )

    def _fileFaceMatchSourceScope(self) -> str:
        config = self.config.readMergedConfig()
        face_match_config = config.get("face_match") if isinstance(config.get("face_match"), dict) else {}
        value = str(face_match_config.get("FILE_MATCH_SOURCE_SCOPE") or "both").strip().lower()
        return value if value in {"both", "photos", "metadata"} else "both"

    def _matchFileFaceInSources(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        target_face: MetadataFace,
        photo_sources: List[Dict[str, Any]],
        metadata_sources: List[MetadataFace],
    ) -> Optional[Dict[str, Any]]:
        target_photo_face = PhotosFace(face_id=0, person_id=0, bbox=from_xmp(target_face))
        source_candidates: List[Dict[str, Any]] = []

        photo_file_faces: List[FileFace] = []
        photo_lookup: List[Dict[str, Any]] = []
        for photo_face in photo_sources:
            face_name = str(photo_face.get("face_name") or "").strip()
            if not face_name:
                continue
            photo_file_faces.append(
                FileFace(
                    name=face_name,
                    bbox=from_photos(photo_face),
                    source="photos",
                    source_format="PHOTOS",
                )
            )
            photo_lookup.append(photo_face)
        for match in self.face_matcher.match([target_photo_face], photo_file_faces):
            matched_photo = photo_lookup[match["file_face_index"]]
            matched_bbox = from_photos(matched_photo)
            source_candidates.append({
                **match,
                "source_type": "photos",
                "source_face": to_display_face({
                    "name": str(matched_photo.get("face_name") or ""),
                    "x": (matched_bbox.x1 + matched_bbox.x2) / 2,
                    "y": (matched_bbox.y1 + matched_bbox.y2) / 2,
                    "w": matched_bbox.x2 - matched_bbox.x1,
                    "h": matched_bbox.y2 - matched_bbox.y1,
                    "source": "photos",
                    "source_format": "PHOTOS",
                }),
                "matched_person": matched_photo.get("person"),
                "image": matched_photo.get("image"),
            })

        metadata_file_faces: List[FileFace] = []
        metadata_lookup: List[MetadataFace] = []
        for metadata_face in metadata_sources:
            if self._sameMetadataFaceCandidate(metadata_face, target_face):
                continue
            metadata_file_faces.append(
                FileFace(
                    name=str(metadata_face.name or ""),
                    bbox=from_xmp(metadata_face),
                    source=metadata_face.source,
                    source_format=metadata_face.source_format,
                )
            )
            metadata_lookup.append(metadata_face)
        for match in self.face_matcher.match([target_photo_face], metadata_file_faces):
            matched_metadata = metadata_lookup[match["file_face_index"]]
            source_candidates.append({
                **match,
                "source_type": "metadata",
                "source_face": to_display_face(matched_metadata),
                "matched_person": None,
                "image": None,
            })

        if not source_candidates:
            return None

        matched = max(source_candidates, key=self._preferredFaceMatchCandidate)
        source_face = matched.get("source_face") if isinstance(matched.get("source_face"), dict) else None
        source_name = str((source_face or {}).get("name") or matched.get("file_name") or "").strip()
        if not source_name:
            return None

        matched_person = matched.get("matched_person") if isinstance(matched.get("matched_person"), dict) else None
        if matched_person is None:
            matched_person = self.photos.findKnownPersonByName(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                name=source_name,
            )

        return {
            "action": "search_file_face_in_sources",
            "searched": True,
            "person": matched_person if isinstance(matched_person, dict) else None,
            "image": matched.get("image") if isinstance(matched.get("image"), dict) else None,
            "face": source_face,
            "source_face": source_face,
            "source_name": source_name,
            "source_type": str(matched.get("source_type") or ""),
            "metadata_face": to_display_face(target_face),
            "image_path": image_path,
            "match": matched,
            "matched_person": matched_person,
            "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
        }

    def _lookupMatchedPersonBySourceName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        source_name: str,
        known_persons_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
        normalized_source_name = str(source_name or "").strip()
        if not normalized_source_name:
            return None, None, {}

        mapped_assignment = self.name_mappings.findNameMapping(normalized_source_name)
        lookup_name = normalized_source_name
        if mapped_assignment:
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
            if mapped_target_name:
                lookup_name = mapped_target_name

        matched_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        lookup_debug = self.photos.debugKnownPersonLookup(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
            known_persons=known_persons_cache,
        )
        return matched_person, mapped_assignment, lookup_debug

    @staticmethod
    def _faceMatchTargetToken(*, image_path: str, face: Any) -> str:
        payload = face.to_dict() if hasattr(face, "to_dict") else (dict(face) if isinstance(face, dict) else {})
        return "|".join([
            str(image_path or "").strip(),
            str(payload.get("source_format") or "").strip().upper(),
            f"{float(payload.get('x') or 0):.6f}",
            f"{float(payload.get('y') or 0):.6f}",
            f"{float(payload.get('w') or 0):.6f}",
            f"{float(payload.get('h') or 0):.6f}",
        ])

    @staticmethod
    def _preferredFaceMatchCandidate(candidate: Dict[str, Any]) -> Tuple[float, int]:
        source_type = str(candidate.get("source_type") or "").strip().lower()
        return (
            float(candidate.get("iou") or 0),
            1 if source_type == "photos" else 0,
        )

    def _storedFaceMatchEntryExists(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        entry: Dict[str, Any],
        image_faces_cache: Dict[int, List[Dict[str, Any]]],
    ) -> bool:
        if not isinstance(entry, dict):
            return False
        action = str(entry.get("action") or "search_photo_face_in_file").strip().lower()
        if action == "search_file_face_in_sources":
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                return False
            payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
            existing = self._findFaceBySignature(payload.faces, metadata_face)
            return bool(existing and not str(existing.name or "").strip())
        if action == "mark_missing_photos_faces":
            image_path = str(entry.get("image_path") or "").strip()
            metadata_face = entry.get("metadata_face")
            if not image_path or not isinstance(metadata_face, dict):
                return False
            payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
            existing = self._findFaceBySignature(payload.faces, metadata_face)
            return bool(existing and str(existing.name or "").strip())
        image = entry.get("image")
        face = entry.get("face")
        if not isinstance(image, dict) or not isinstance(face, dict):
            return False
        try:
            image_id = int(image.get("id"))
            face_id = int(face.get("face_id"))
        except (TypeError, ValueError):
            return False

        if image_id not in image_faces_cache:
            image_faces_cache[image_id] = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=image_id,
            )

        for image_face in image_faces_cache[image_id]:
            try:
                if int(image_face.get("face_id")) == face_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _pickReviewFace(faces: List[MetadataFace]) -> Optional[MetadataFace]:
        if not isinstance(faces, list):
            return None
        mwg_faces = [face for face in faces if isinstance(face, MetadataFace) and face.source_format == "MWG_REGIONS"]
        if not mwg_faces:
            return None
        named = [face for face in mwg_faces if str(face.name or "").strip()]
        return named[0] if named else mwg_faces[0]

    @staticmethod
    def _isSameFace(left: Any, right: Any) -> bool:
        if isinstance(left, MetadataFace):
            left = left.to_dict()
        if isinstance(right, MetadataFace):
            right = right.to_dict()
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        left_face_id = left.get("face_id")
        right_face_id = right.get("face_id")
        if left_face_id not in (None, "") and right_face_id not in (None, ""):
            try:
                return int(left_face_id) == int(right_face_id)
            except (TypeError, ValueError):
                return False
        keys = ("source_format", "source", "name", "x", "y", "w", "h", "orientation")
        return all(left.get(key) == right.get(key) for key in keys)

    @staticmethod
    def _faceSignature(face: Any) -> Dict[str, Any]:
        if isinstance(face, MetadataFace):
            payload = face.to_dict()
            for key in ("face_id", "person_id"):
                value = getattr(face, key, None)
                if value not in (None, ""):
                    payload[key] = value
            face = payload
        if not isinstance(face, dict):
            return {}
        payload = {
            "source_format": face.get("source_format"),
            "source": face.get("source"),
            "name": face.get("name"),
            "x": face.get("x"),
            "y": face.get("y"),
            "w": face.get("w"),
            "h": face.get("h"),
            "orientation": face.get("orientation"),
        }
        for key in ("face_id", "person_id"):
            value = face.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    def _findFaceBySignature(self, faces: List[MetadataFace], signature: Dict[str, Any]) -> Optional[MetadataFace]:
        if not isinstance(signature, dict):
            return None
        for face in faces:
            if self._isSameFace(face, signature):
                return face
        return None

    def _buildCheckEntry(
        self,
        *,
        review_type: str,
        image_path: str,
        face_name: str = "",
        left_face: Optional[MetadataFace] = None,
        right_face: Optional[MetadataFace] = None,
    ) -> Dict[str, Any]:
        return {
            "review_type": review_type,
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": face_name,
            "left_face_signature": self._faceSignature(left_face or {}),
            "right_face_signature": self._faceSignature(right_face or {}),
        }

    @staticmethod
    def _hasFaceSignature(signature: Any) -> bool:
        return isinstance(signature, dict) and any(bool(signature.get(key)) for key in ("name", "source", "source_format", "bbox"))

    def _buildDimensionMismatchReviewEntry(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        if analysis.get("files_with_mwg_dimension_mismatch") != 1:
            return None

        mwg_faces = [face for face in payload.faces if face.source_format == "MWG_REGIONS"]
        if not mwg_faces:
            return None

        review_face = self._pickReviewFace(mwg_faces) or mwg_faces[0]
        return self._buildCheckEntry(
            review_type="dimension_issues",
            image_path=image_path,
            face_name=str(review_face.name or ""),
            left_face=review_face,
        )

    def _buildDimensionMismatchReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        if analysis.get("files_with_mwg_dimension_mismatch") != 1:
            return None

        mwg_faces = [face for face in payload.faces if face.source_format == "MWG_REGIONS"]
        reference_faces = [face for face in payload.faces if face.source_format != "MWG_REGIONS"]
        if not mwg_faces:
            return None

        review_face = self._findFaceBySignature(mwg_faces, (entry or {}).get("left_face_signature") or {})
        review_face = review_face or self._pickReviewFace(mwg_faces) or mwg_faces[0]
        applied_face = to_display_face(review_face)
        reference_face = self._findBestReferenceFace(review_face, reference_faces) or review_face

        return {
            "review_type": "dimension_issues",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "left_face": applied_face,
            "left_face_target": self._faceSignature(review_face),
            "right_face": to_display_face(reference_face),
            "right_face_target": self._faceSignature(reference_face),
            "left_alert_faces": [
                to_display_face(face) for face in mwg_faces
                if not self._isSameFace(face, review_face)
            ],
            "left_reference_faces": [to_display_face(face) for face in reference_faces],
            "right_alert_faces": [],
            "right_reference_faces": [],
            "face_name": str(review_face.name or ""),
            "left_name": str(review_face.name or ""),
            "right_name": str(reference_face.name or ""),
            "left_format": str(review_face.source_format or ""),
            "right_format": str(reference_face.source_format or ""),
            "image_dimensions": analysis.get("image_dimensions") if isinstance(analysis.get("image_dimensions"), dict) else {},
            "applied_to_dimensions": analysis.get("mwg_applied_to_dimensions") if isinstance(analysis.get("mwg_applied_to_dimensions"), dict) else {},
            "image_orientation": analysis.get("image_orientation"),
            "mwg_applied_to_dimensions_matches_current": analysis.get("mwg_applied_to_dimensions_matches_current"),
        }

    def _findBestReferenceFace(self, review_face: MetadataFace, candidates: List[MetadataFace]) -> Optional[MetadataFace]:
        review_name = str(review_face.name or "").strip().casefold()
        prioritized_candidates = candidates
        if review_name:
            same_name = [face for face in candidates if str(face.name or "").strip().casefold() == review_name]
            if same_name:
                prioritized_candidates = same_name

        for preferred_format in ("ACD", "PHOTOS", "MICROSOFT"):
            for face in prioritized_candidates:
                if str(face.source_format or "").strip().upper() == preferred_format:
                    return face
        return prioritized_candidates[0] if prioritized_candidates else None

    def _configuredReviewOptions(self) -> Dict[str, bool]:
        config = self.config.readMergedConfig()
        review_config = config.get("review") if isinstance(config.get("review"), dict) else {}
        review_options = review_config.get("OPTIONS") if isinstance(review_config.get("OPTIONS"), dict) else {}
        legacy_analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        legacy_checks = legacy_analysis.get("CHECKS") if isinstance(legacy_analysis.get("CHECKS"), dict) else {}
        default_options = ConfigService.defaultConfig()["review"]["OPTIONS"]
        return {
            "DUPLICATE_FACE_SUGGESTIONS": bool(
                review_options.get(
                    "DUPLICATE_FACE_SUGGESTIONS",
                    legacy_checks.get("DUPLICATE_FACE_SUGGESTIONS", default_options["DUPLICATE_FACE_SUGGESTIONS"]),
                )
            ),
        }

    def _buildDuplicateFaceReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        grouped: Dict[tuple, List[MetadataFace]] = {}
        for face in payload.faces:
            name = str(face.name or "").strip()
            source_format = str(face.source_format or "").strip()
            if not name or not source_format:
                continue
            grouped.setdefault((source_format, name.casefold()), []).append(face)

        entries: List[Dict[str, Any]] = []
        for (_, _), grouped_faces in grouped.items():
            if len(grouped_faces) < 2:
                continue
            for index in range(len(grouped_faces) - 1):
                left = grouped_faces[index]
                right = grouped_faces[index + 1]
                entries.append(
                    self._buildCheckEntry(
                        review_type="duplicate_faces",
                        image_path=image_path,
                        face_name=str(left.name or ""),
                        left_face=left,
                        right_face=right,
                    )
                )
        return entries

    def _buildDuplicateFaceReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        analysis = analysis or self.files.analyzeMetadata(payload)
        review_options = self._configuredReviewOptions()
        faces = payload.faces
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None

        left_state = "alert"
        right_state = "alert"
        if review_options.get("DUPLICATE_FACE_SUGGESTIONS", True):
            left_state, right_state = self._getDuplicateSuggestionStates(
                left_face=left,
                right_face=right,
                faces=faces,
            )
        left_state, right_state = self._applySingleSourceOfTruthSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )
        left_state, right_state = self._applyOrientationRiskSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )

        return {
            "review_type": "duplicate_faces",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _getDuplicateSuggestionStates(
        self,
        *,
        left_face: MetadataFace,
        right_face: MetadataFace,
        faces: List[MetadataFace],
    ) -> Tuple[str, str]:
        left_state = "alert"
        right_state = "alert"

        containment = self._duplicateContainmentSuggestion(left_face, right_face)
        if containment == "left":
            return "suggested", right_state
        if containment == "right":
            return left_state, "suggested"

        left_matches, left_safe_matches = self._duplicateSuggestionSupportStats(left_face, faces)
        right_matches, right_safe_matches = self._duplicateSuggestionSupportStats(right_face, faces)
        if left_matches > right_matches:
            return "suggested", right_state
        if right_matches > left_matches:
            return left_state, "suggested"
        if left_safe_matches > right_safe_matches:
            return "suggested", right_state
        if right_safe_matches > left_safe_matches:
            return left_state, "suggested"
        return left_state, right_state

    def _duplicateSuggestionSupportStats(self, candidate: MetadataFace, faces: List[MetadataFace]) -> Tuple[int, int]:
        candidate_name = str(candidate.name or "").strip().casefold()
        candidate_format = str(candidate.source_format or "").strip().upper()
        if not candidate_name or not candidate_format:
            return 0, 0

        normalized_candidate = to_display_face(candidate)
        matches = 0
        safe_matches = 0
        for face in faces:
            face_name = str(face.name or "").strip().casefold()
            face_format = str(face.source_format or "").strip().upper()
            if face_name != candidate_name or face_format == candidate_format:
                continue
            normalized_face = to_display_face(face)
            if self.files._boxesOverlapStrongly(normalized_candidate, normalized_face):
                matches += 1
                if not self._faceHasOrientationRisk(face):
                    safe_matches += 1
        return matches, safe_matches

    def _duplicateContainmentSuggestion(
        self,
        left_face: MetadataFace,
        right_face: MetadataFace,
    ) -> str:
        left_bbox = from_xmp(left_face)
        right_bbox = from_xmp(right_face)
        if self._boundingBoxContains(left_bbox, right_bbox) and left_bbox.area() > right_bbox.area():
            return "left"
        if self._boundingBoxContains(right_bbox, left_bbox) and right_bbox.area() > left_bbox.area():
            return "right"
        return ""

    @staticmethod
    def _boundingBoxContains(container: Any, inner: Any, *, epsilon: float = 1e-9) -> bool:
        try:
            return (
                float(container.x1) <= float(inner.x1) + epsilon and
                float(container.y1) <= float(inner.y1) + epsilon and
                float(container.x2) >= float(inner.x2) - epsilon and
                float(container.y2) >= float(inner.y2) - epsilon
            )
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _faceHasOrientationRisk(face: Optional[MetadataFace]) -> bool:
        if not isinstance(face, MetadataFace):
            return False
        source_format = str(face.source_format or "").strip().upper()
        if source_format not in {"MWG_REGIONS", "MICROSOFT"}:
            return False
        return face.orientation not in (None, 1)

    def _applyOrientationRiskSuggestion(
        self,
        *,
        left_state: str,
        right_state: str,
        left_face: Optional[MetadataFace],
        right_face: Optional[MetadataFace],
    ) -> Tuple[str, str]:
        if left_state == "suggested" or right_state == "suggested":
            return left_state, right_state

        left_risk = self._faceHasOrientationRisk(left_face)
        right_risk = self._faceHasOrientationRisk(right_face)
        if left_risk == right_risk:
            return left_state, right_state
        if left_risk:
            return left_state, "suggested"
        return "suggested", right_state

    @staticmethod
    def _faceMatchesSingleSourceOfTruth(face: Optional[MetadataFace], source_of_truth: str) -> bool:
        if not isinstance(face, MetadataFace) or not source_of_truth:
            return False
        if source_of_truth == "photos":
            return str(face.source_format or "").strip().upper() == "PHOTOS"
        parts = source_of_truth.split(":")
        if len(parts) != 3 or parts[0] != "metadata":
            return False
        requested_format = parts[1]
        requested_location = parts[2]
        face_format = str(face.source_format or "").strip().lower()
        if face_format == "photos":
            return False
        source = str(face.source or "").strip().lower()
        face_location = "sidecar" if source == "xmp_file" else "embedded"
        format_matches = requested_format == "any" or face_format == requested_format
        location_matches = requested_location == "any" or face_location == requested_location
        return format_matches and location_matches

    def _applySingleSourceOfTruthSuggestion(
        self,
        *,
        left_state: str,
        right_state: str,
        left_face: Optional[MetadataFace],
        right_face: Optional[MetadataFace],
    ) -> Tuple[str, str]:
        source_of_truth = str(self._configuredAnalysisChecks().get("SINGLE_SOURCE_OF_TRUTH") or "").strip().lower()
        if not source_of_truth:
            return left_state, right_state

        left_matches = self._faceMatchesSingleSourceOfTruth(left_face, source_of_truth)
        right_matches = self._faceMatchesSingleSourceOfTruth(right_face, source_of_truth)
        if left_matches == right_matches:
            return left_state, right_state
        if left_matches:
            return "suggested", "alert"
        return "alert", "suggested"

    def _getNameConflictSuggestionStates(
        self,
        left_name: str,
        right_name: str,
        *,
        left_face: Optional[MetadataFace] = None,
        right_face: Optional[MetadataFace] = None,
    ) -> Tuple[str, str]:
        left_state = "alert"
        right_state = "alert"

        normalized_left = self.name_mappings._normalize_name_value(left_name)
        normalized_right = self.name_mappings._normalize_name_value(right_name)
        if not normalized_left or not normalized_right:
            return self._applySingleSourceOfTruthSuggestion(
                left_state=left_state,
                right_state=right_state,
                left_face=left_face,
                right_face=right_face,
            )

        left_mapping = self.name_mappings.findNameMapping(left_name)
        if left_mapping and self.name_mappings._normalize_name_value(left_mapping.get("target_name")) == normalized_right:
            right_state = "suggested"
            return self._applySingleSourceOfTruthSuggestion(
                left_state=left_state,
                right_state=right_state,
                left_face=left_face,
                right_face=right_face,
            )

        right_mapping = self.name_mappings.findNameMapping(right_name)
        if right_mapping and self.name_mappings._normalize_name_value(right_mapping.get("target_name")) == normalized_left:
            left_state = "suggested"

        return self._applySingleSourceOfTruthSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left_face,
            right_face=right_face,
        )

    @staticmethod
    def _metadataFaceFromPhotoFace(face: Dict[str, Any]) -> Optional[MetadataFace]:
        if not isinstance(face, dict):
            return None
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
        top_left = bbox.get("top_left") if isinstance(bbox.get("top_left"), dict) else {}
        bottom_right = bbox.get("bottom_right") if isinstance(bbox.get("bottom_right"), dict) else {}
        try:
            left = float(top_left.get("x"))
            top = float(top_left.get("y"))
            right = float(bottom_right.get("x"))
            bottom = float(bottom_right.get("y"))
        except (TypeError, ValueError):
            return None
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        normalized_face = MetadataFace.from_center_box(
            name=str(face.get("face_name") or ""),
            x=left + (width / 2),
            y=top + (height / 2),
            w=width,
            h=height,
            source="photos",
            source_format="PHOTOS",
        )
        for key in ("face_id", "person_id"):
            value = face.get(key)
            if value not in (None, ""):
                setattr(normalized_face, key, value)
        return normalized_face

    def _loadPhotoFacesForImage(
        self,
        *,
        user_key: Optional[str],
        cookies: Optional[Dict[str, str]],
        base_url: str,
        shared_folder: str,
        image_path: str,
    ) -> List[MetadataFace]:
        normalized_path = str(image_path or "").strip()
        if not user_key or not isinstance(cookies, dict) or not base_url or not normalized_path:
            return []
        resolved_shared_folder = str(shared_folder or "").strip()
        if not resolved_shared_folder:
            resolved_shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
        if not resolved_shared_folder:
            return []
        try:
            item = self.photos.findFotoTeamItemByPath(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=resolved_shared_folder,
                image_path=normalized_path,
                additional=["thumbnail"],
            )
            item_id = item.get("id") if isinstance(item, dict) else None
            item_id_int = int(item_id)
        except (TypeError, ValueError):
            return []
        except Exception:
            return []

        try:
            raw_faces = self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id_int,
            )
        except Exception:
            return []

        normalized_faces: List[MetadataFace] = []
        for face in raw_faces:
            mapped = self._metadataFaceFromPhotoFace(face)
            if mapped is not None:
                normalized_faces.append(mapped)
        return normalized_faces

    def _loadPhotoFacesForImageWithOverride(
        self,
        *,
        user_key: Optional[str],
        cookies: Optional[Dict[str, str]],
        base_url: str,
        shared_folder: str,
        image_path: str,
        original_face_data: Optional[Dict[str, Any]] = None,
        replacement_face_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[MetadataFace]]:
        if not original_face_data or not replacement_face_data:
            return None
        if str(original_face_data.get("source_format") or "").strip().upper() != "PHOTOS":
            return None

        photo_faces = self._loadPhotoFacesForImage(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=image_path,
        )
        replacement_face = MetadataFace.from_dict(replacement_face_data)
        for key in ("face_id", "person_id"):
            value = replacement_face_data.get(key)
            if value not in (None, ""):
                setattr(replacement_face, key, value)

        original_signature = self._faceSignature(original_face_data)
        index_to_replace = None
        for index, face in enumerate(photo_faces):
            if self._isSameFace(face, original_signature):
                index_to_replace = index
                break
            face_signature = self._faceSignature(face)
            geometry_keys = ("source_format", "source", "x", "y", "w", "h", "orientation")
            if all(face_signature.get(key) == original_signature.get(key) for key in geometry_keys):
                index_to_replace = index
                break

        if index_to_replace is None:
            photo_faces.append(replacement_face)
        else:
            photo_faces[index_to_replace] = replacement_face
        return photo_faces

    def _buildPositionDeviationReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        entries: List[Dict[str, Any]] = []
        for index, left in enumerate(faces):
            left_name = str(left.name or "").strip().casefold()
            left_format = str(left.source_format or "").strip().upper()
            if not left_name or not left_format:
                continue
            normalized_left = to_display_face(left)
            for right in faces[index + 1:]:
                right_name = str(right.name or "").strip().casefold()
                right_format = str(right.source_format or "").strip().upper()
                if left_name != right_name or left_format == right_format:
                    continue
                normalized_right = to_display_face(right)
                if self.files._boxesOverlapStrongly(normalized_left, normalized_right):
                    continue
                entries.append(
                    self._buildCheckEntry(
                        review_type="position_deviations",
                        image_path=image_path,
                        face_name=str(left.name or ""),
                        left_face=left,
                        right_face=right,
                    )
                )
        return entries

    def _buildPositionDeviationReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        left_state, right_state = self._applySingleSourceOfTruthSuggestion(
            left_state="alert",
            right_state="alert",
            left_face=left,
            right_face=right,
        )
        return {
            "review_type": "position_deviations",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _buildNameConflictReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        entries: List[Dict[str, Any]] = []
        for index, left in enumerate(faces):
            left_name = str(left.name or "").strip()
            if not left_name:
                continue
            normalized_left = to_display_face(left)
            for right in faces[index + 1:]:
                right_name = str(right.name or "").strip()
                if not right_name or left_name.casefold() == right_name.casefold():
                    continue
                normalized_right = to_display_face(right)
                if not self.files._boxesOverlapStrongly(normalized_left, normalized_right):
                    continue
                entries.append(
                    self._buildCheckEntry(
                        review_type="name_conflicts",
                        image_path=image_path,
                        face_name=left_name,
                        left_face=left,
                        right_face=right,
                    )
                )
        return entries

    def _buildNameConflictReviewItem(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
        entry: Optional[Dict[str, Any]] = None,
        photo_faces: Optional[List[MetadataFace]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = list(payload.faces)
        if photo_faces:
            faces.extend(photo_faces)
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        left_name = str(left.name or "")
        right_name = str(right.name or "")
        left_state, right_state = self._getNameConflictSuggestionStates(
            left_name,
            right_name,
            left_face=left,
            right_face=right,
        )
        left_state, right_state = self._applyOrientationRiskSuggestion(
            left_state=left_state,
            right_state=right_state,
            left_face=left,
            right_face=right,
        )
        return {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": left_name,
            "left_name": left_name,
            "right_name": right_name,
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": to_display_face(left),
            "left_face_target": self._faceSignature(left),
            "right_face": to_display_face(right),
            "right_face_target": self._faceSignature(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def startChecksReview(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        source_mode: str,
        check_type: str,
        save_only: bool = False,
        resume_from_progress: bool = False,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
    ) -> Dict[str, Any]:
        source_mode_normalized = str(source_mode or "findings").strip().lower()
        if source_mode_normalized not in {"findings", "scan"}:
            source_mode_normalized = "findings"

        check_type_normalized = str(check_type or "dimension_issues").strip().lower()
        supported_types = {"dimension_issues", "duplicate_faces", "position_deviations", "name_conflicts"}
        if check_type_normalized not in supported_types:
            check_type_normalized = "dimension_issues"

        if source_mode_normalized == "scan":
            return self.startChecksScanDiscovery(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                check_type=check_type_normalized,
                save_only=save_only,
                resume_from_progress=resume_from_progress,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
            )

        if source_mode_normalized == "findings":
            findings_payload = self.getChecksFindingEntries(check_type=check_type_normalized)
            stored_entries = findings_payload.get("entries") if isinstance(findings_payload.get("entries"), list) else []
            if stored_entries:
                entries = [entry for entry in stored_entries if isinstance(entry, dict)]
                return {
                    "check_type": check_type_normalized,
                    "source_mode": source_mode_normalized,
                    "save_only": bool(findings_payload.get("save_only")),
                    "count": len(entries),
                    "entries": entries,
                }
            return {
                "check_type": check_type_normalized,
                "source_mode": source_mode_normalized,
                "save_only": bool(findings_payload.get("save_only")),
                "count": 0,
                "entries": [],
            }

    def startChecksScanDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool = False,
        resume_from_progress: bool = False,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
    ) -> Dict[str, Any]:
        check_type = self._normalizeChecksType(check_type)
        current = self.getChecksProgress(user_key, check_type)
        state_key = self._checksStateKey(user_key, check_type)
        worker = self._checks_threads.get(state_key)
        if current.get("running") and worker and worker.is_alive():
            return current

        resume_cursor = current.get("resume_cursor") if resume_from_progress and isinstance(current.get("resume_cursor"), dict) else {}
        if resume_cursor:
            save_only = bool(resume_cursor.get("save_only", save_only))
            check_type = str(resume_cursor.get("check_type") or check_type or "dimension_issues").strip().lower()
        else:
            self._invalidateChecksCandidatePathsCache(user_key, check_type)

        self._setChecksProgressMessage(
            user_key,
            check_type,
            "checks:status_preparing_scan",
            running=True,
            finished=False,
            stop_requested=False,
            source_mode="scan",
            save_only=save_only,
            files_scanned=0,
            total_files=0,
            findings_count=int(resume_cursor.get("findings_count") or 0) if resume_cursor else 0,
            current_path="",
            result=None,
            resume_cursor=resume_cursor or self._buildChecksResumeCursor(
                path_index=0,
                pending_entries=[],
                source_mode="scan",
                check_type=check_type,
                save_only=save_only,
                findings_count=0,
            ),
        )
        worker = Thread(
            target=self._runChecksScan,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "check_type": check_type,
                "save_only": save_only,
                "auto_apply_suggested_names": auto_apply_suggested_names,
                "auto_apply_suggested_duplicates": auto_apply_suggested_duplicates,
                "resume_cursor": resume_cursor if resume_cursor else None,
            },
            daemon=True,
        )
        self._checks_threads[state_key] = worker
        worker.start()
        return self.getChecksProgress(user_key, check_type)

    def _runChecksScan(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]] = None,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
    ) -> None:
        try:
            result = self.searchNextChecksItem(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                check_type=check_type,
                save_only=save_only,
                resume_cursor=resume_cursor,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
            )
            self._setChecksProgress(
                user_key,
                **result,
            )
        except (SessionBootstrapRequired, SessionManagerError) as exc:
            current_progress = self.getChecksProgress(user_key, check_type)
            current_resume_cursor = current_progress.get("resume_cursor") if isinstance(current_progress.get("resume_cursor"), dict) else {}
            self._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_failed",
                message=str(exc),
                running=False,
                finished=False,
                stop_requested=False,
                error=str(exc),
                save_only=save_only,
                source_mode="scan",
                files_scanned=int(current_progress.get("files_scanned") or 0),
                total_files=int(current_progress.get("total_files") or 0),
                findings_count=int(current_progress.get("findings_count") or 0),
                current_path=str(current_progress.get("current_path") or ""),
                resume_cursor=current_resume_cursor or resume_cursor or self._buildChecksResumeCursor(
                    path_index=0,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=0,
                ),
            )
        except Exception as exc:
            self._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_failed",
                message="Checks scan failed.",
                running=False,
                finished=True,
                stop_requested=False,
                error=str(exc),
                save_only=save_only,
                source_mode="scan",
            )
        finally:
            self._checks_threads.pop(self._checksStateKey(user_key, check_type), None)

    def searchNextChecksItem(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        check_type: str,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
        auto_apply_suggested_names: bool = False,
        auto_apply_suggested_duplicates: bool = False,
    ) -> Dict[str, Any]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        if not shared_folder:
            return self._buildChecksScanPayload(
                check_type=check_type,
                save_only=save_only,
                files_scanned=0,
                total_files=0,
                findings_count=0,
                path_index=0,
                pending_entries=[],
                message_key="checks:progress_shared_folder_missing",
                message="Shared folder could not be resolved.",
            )

        path_index = int(resume_cursor.get("path_index") or 0) if isinstance(resume_cursor, dict) else 0
        pending_entries = resume_cursor.get("pending_entries") if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("pending_entries"), list) else []
        findings_count = int(resume_cursor.get("findings_count") or 0) if isinstance(resume_cursor, dict) else 0
        saved_entries: List[Dict[str, Any]] = []
        candidate_paths = self._getChecksCandidatePaths(
            user_key=user_key,
            check_type=check_type,
            shared_folder=shared_folder,
            use_cache=True,
        )
        total_files = len(candidate_paths)
        self._setChecksProgressMessage(
            user_key,
            check_type,
            "checks:progress_scanning",
            message_params={"current": max(0, path_index), "total": total_files, "findings": findings_count},
            running=True,
            finished=False,
            stop_requested=False,
            source_mode="scan",
            save_only=save_only,
            files_scanned=max(0, path_index),
            total_files=total_files,
            findings_count=findings_count,
            current_path="",
            resume_cursor=self._buildChecksResumeCursor(
                path_index=path_index,
                pending_entries=pending_entries,
                source_mode="scan",
                check_type=check_type,
                save_only=save_only,
                findings_count=findings_count,
            ),
        )

        if pending_entries and not save_only:
            entry = pending_entries[0]
            remaining_entries = pending_entries[1:]
            resolved = self._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            entry = resolved.get("entry")
            item = resolved.get("item")
            auto_applied_count = int(resolved.get("auto_applied_count") or 0)
            if auto_applied_count:
                findings_count = max(0, findings_count - auto_applied_count)
            if resolved.get("auto_apply_warning"):
                return self._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=min(path_index, total_files),
                    total_files=total_files,
                    findings_count=findings_count,
                    path_index=path_index,
                    pending_entries=remaining_entries,
                    current_path=str((entry or {}).get("image_path") or ""),
                    result={"entry": entry, "item": item} if entry and item else None,
                    message_key=str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                    message="Suggested name could not be applied automatically.",
                    message_params={"count": findings_count},
                )
            if not entry or not item:
                pending_entries = remaining_entries
            else:
                findings_count = max(findings_count, 1)
                return self._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=min(path_index, total_files),
                    total_files=total_files,
                    findings_count=findings_count,
                    path_index=path_index,
                    pending_entries=remaining_entries,
                    current_path=str(entry.get("image_path") or ""),
                    result={
                        "entry": entry,
                        "item": item,
                    },
                    message_key="checks:progress_result_found",
                    message="Check finding found.",
                    message_params={"count": findings_count},
                )

        for index in range(max(0, path_index), total_files):
            if self._shouldStopChecks(user_key, check_type):
                return self._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=save_only,
                    files_scanned=index,
                    total_files=total_files,
                    findings_count=findings_count,
                    path_index=index,
                    pending_entries=[],
                    message_key="checks:progress_stopped",
                    message="Checks scan stopped.",
                    message_params={"count": findings_count},
                )
            image_path = candidate_paths[index]
            scanned_count = index + 1
            self._setChecksProgressMessage(
                user_key,
                check_type,
                "checks:progress_scanning",
                message_params={"current": scanned_count, "total": total_files, "findings": findings_count},
                running=True,
                finished=False,
                stop_requested=False,
                source_mode="scan",
                save_only=save_only,
                files_scanned=scanned_count,
                total_files=total_files,
                findings_count=findings_count,
                current_path=image_path,
                resume_cursor=self._buildChecksResumeCursor(
                    path_index=index,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=findings_count,
                ),
            )
            analysis = self.analyzeImageFaceMetadata(image_path)
            entries = self._buildCheckEntriesForType(
                image_path=image_path,
                review_type=check_type,
                analysis=analysis,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            if not entries:
                continue

            findings_count += len(entries)
            if save_only:
                entry = entries[0]
                resolved = self._resolveChecksReviewEntry(
                    entry=entry,
                    auto_apply_suggested_names=auto_apply_suggested_names,
                    auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
                auto_applied_count = int(resolved.get("auto_applied_count") or 0)
                if auto_applied_count:
                    findings_count = max(0, findings_count - auto_applied_count)
                if resolved.get("auto_apply_warning"):
                    return {
                        "running": False,
                        "finished": True,
                        "stop_requested": False,
                        "source_mode": "scan",
                        "check_type": check_type,
                        "save_only": True,
                        "files_scanned": scanned_count,
                        "total_files": total_files,
                        "findings_count": findings_count,
                        "current_path": image_path,
                        "result": None,
                        "resume_cursor": self._buildChecksResumeCursor(
                            path_index=index + 1,
                            pending_entries=[],
                            source_mode="scan",
                            check_type=check_type,
                            save_only=True,
                            findings_count=findings_count,
                        ),
                        "message_key": str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                        "message": "Suggested solution could not be applied automatically.",
                        "message_params": {"count": findings_count},
                    }

                refreshed_entries = entries
                if auto_applied_count:
                    refreshed_entries = self._buildCheckEntriesForType(
                        image_path=image_path,
                        review_type=check_type,
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        shared_folder=shared_folder,
                    )

                if refreshed_entries:
                    saved_entries.extend(refreshed_entries)
                self._setChecksProgressMessage(
                    user_key,
                    check_type,
                    "checks:progress_scanning",
                    message_params={"current": scanned_count, "total": total_files, "findings": findings_count},
                    running=True,
                    finished=False,
                    source_mode="scan",
                    save_only=True,
                    files_scanned=scanned_count,
                    total_files=total_files,
                    findings_count=findings_count,
                    current_path=image_path,
                    resume_cursor=self._buildChecksResumeCursor(
                        path_index=index + 1,
                        pending_entries=[],
                        source_mode="scan",
                        check_type=check_type,
                        save_only=True,
                        findings_count=findings_count,
                    ),
                )
                continue

            entry = entries[0]
            item = None
            remaining_entries = entries[1:]
            resolved = self._resolveChecksReviewEntry(
                entry=entry,
                auto_apply_suggested_names=auto_apply_suggested_names,
                auto_apply_suggested_duplicates=auto_apply_suggested_duplicates,
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
            )
            entry = resolved.get("entry")
            item = resolved.get("item")
            auto_applied_count = int(resolved.get("auto_applied_count") or 0)
            if auto_applied_count:
                refreshed_entries = self._buildCheckEntriesForType(
                    image_path=image_path,
                    review_type=check_type,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
                findings_count = max(0, findings_count - auto_applied_count)
                if not refreshed_entries:
                    continue
                entry = refreshed_entries[0]
                remaining_entries = refreshed_entries[1:]
                item = self.getChecksReviewItem(
                    entry=entry,
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                )
            if resolved.get("auto_apply_warning"):
                return self._buildChecksScanPayload(
                    check_type=check_type,
                    save_only=False,
                    files_scanned=scanned_count,
                    total_files=total_files,
                    findings_count=findings_count,
                    path_index=index + 1,
                    pending_entries=remaining_entries,
                    current_path=image_path,
                    result={"entry": entry, "item": item} if entry and item else None,
                    message_key=str(resolved.get("auto_apply_warning") or "checks:progress_result_found"),
                    message="Suggested name could not be applied automatically.",
                    message_params={"count": findings_count},
                )
            if not entry or not item:
                continue
            return self._buildChecksScanPayload(
                check_type=check_type,
                save_only=False,
                files_scanned=scanned_count,
                total_files=total_files,
                findings_count=findings_count,
                path_index=index + 1,
                pending_entries=remaining_entries,
                current_path=image_path,
                result={
                    "entry": entry,
                    "item": item,
                },
                message_key="checks:progress_result_found",
                message="Check finding found.",
                message_params={"count": findings_count},
            )

        if save_only:
            self._writeChecksFindings(
                check_type=check_type,
                status="finished",
                shared_folder=shared_folder,
                source_mode="scan",
                save_only=True,
                entries=saved_entries,
            )
            return self._buildChecksScanPayload(
                check_type=check_type,
                save_only=True,
                files_scanned=total_files,
                total_files=total_files,
                findings_count=len(saved_entries),
                path_index=total_files,
                pending_entries=[],
                message_key="checks:progress_findings_saved" if saved_entries else "checks:progress_findings_empty",
                message="Checks findings saved." if saved_entries else "No checks findings were saved.",
                message_params={"count": len(saved_entries)},
            )

        return self._buildChecksScanPayload(
            check_type=check_type,
            save_only=False,
            files_scanned=total_files,
            total_files=total_files,
            findings_count=findings_count,
            path_index=total_files,
            pending_entries=[],
            message_key="checks:progress_finished_no_match",
            message="No further checks findings found.",
            message_params={"count": findings_count},
        )

    def getChecksReviewItem(
        self,
        *,
        entry: Dict[str, Any],
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: str = "",
        shared_folder: str = "",
    ) -> Optional[Dict[str, Any]]:
        image_path = str(entry.get("image_path") or "").strip()
        review_type = str(entry.get("review_type") or "").strip().lower()
        if not image_path or not review_type:
            return None
        photo_faces: Optional[List[MetadataFace]] = None
        analysis_checks = self._configuredAnalysisChecks()
        if review_type == "position_deviations" and analysis_checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"):
            photo_faces = self._loadPhotoFacesForImage(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
            )
        elif review_type == "name_conflicts" and analysis_checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS"):
            photo_faces = self._loadPhotoFacesForImage(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                shared_folder=shared_folder,
                image_path=image_path,
            )
        if review_type == "dimension_issues":
            if not self._hasFaceSignature(entry.get("left_face_signature")):
                return None
        elif review_type in {"duplicate_faces", "position_deviations", "name_conflicts"}:
            if not self._hasFaceSignature(entry.get("left_face_signature")) or not self._hasFaceSignature(entry.get("right_face_signature")):
                return None
        analysis = self.analyzeImageFaceMetadata(image_path)
        if review_type == "dimension_issues":
            return self._buildDimensionMismatchReviewItem(image_path, analysis, entry)
        if review_type == "duplicate_faces":
            return self._buildDuplicateFaceReviewItem(image_path, analysis, entry)
        if review_type == "position_deviations":
            return self._buildPositionDeviationReviewItem(image_path, analysis, entry, photo_faces)
        if review_type == "name_conflicts":
            return self._buildNameConflictReviewItem(image_path, analysis, entry, photo_faces)
        return None

    @staticmethod
    def _incrementCounter(counter: Dict[str, int], key: str, amount: int = 1) -> None:
        normalized = str(key or "").strip()
        if not normalized:
            return
        counter[normalized] = counter.get(normalized, 0) + amount

    @staticmethod
    def _nonZeroCounters(counter: Dict[str, int]) -> Dict[str, int]:
        return {key: value for key, value in counter.items() if value > 0}

    def _buildFileAnalysisPayload(
        self,
        *,
        job_id: str,
        started_at: str,
        shared_folder: str,
        configured_extensions: List[str],
        status: str,
        phase: str,
        message: str,
        directories_read: int,
        files_seen_total: int,
        files_matched_total: int,
        files_analyzed: int,
        files_with_sidecar: int,
        files_with_embedded_xmp: int,
        files_with_face_metadata: int,
        files_with_mwg_applied_to_dimensions: int,
        files_with_mwg_dimension_mismatch: int,
        files_with_mwg_orientation_transform_risk: int,
        faces_total: int,
        faces_named: int,
        faces_unnamed: int,
        persons_distinct_names: set,
        files_with_duplicate_faces: Optional[int] = None,
        files_with_face_position_deviations: Optional[int] = None,
        files_with_dimension_issues: Optional[int] = None,
        files_with_name_conflicts: Optional[int] = None,
        focus_usages: Dict[str, int],
        extensions: Dict[str, int],
        formats: Dict[str, int],
        sources: Dict[str, int],
        current_path: str,
        running: bool,
        finished: bool,
        stopped: bool,
        stop_requested: bool,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": self._timestamp_now() if finished else "",
            "last_updated_at": self._timestamp_now(),
            "status": status,
            "phase": phase,
            "message": message,
            "shared_folder": shared_folder,
            "configured_extensions": configured_extensions,
            "directories_read": directories_read,
            "files_seen_total": files_seen_total,
            "files_matched_total": files_matched_total,
            "files_analyzed": files_analyzed,
            "files_with_sidecar": files_with_sidecar,
            "files_with_embedded_xmp": files_with_embedded_xmp,
            "files_with_face_metadata": files_with_face_metadata,
            "files_with_mwg_applied_to_dimensions": files_with_mwg_applied_to_dimensions,
            "files_with_mwg_dimension_mismatch": files_with_mwg_dimension_mismatch,
            "files_with_mwg_orientation_transform_risk": files_with_mwg_orientation_transform_risk,
            "analysis_progress": {"current": files_analyzed, "total": files_matched_total},
            "faces_total": faces_total,
            "faces_named": faces_named,
            "faces_unnamed": faces_unnamed,
            "persons_distinct_by_name": len(persons_distinct_names),
            "files_with_duplicate_faces": files_with_duplicate_faces,
            "files_with_face_position_deviations": files_with_face_position_deviations,
            "files_with_dimension_issues": files_with_dimension_issues,
            "files_with_name_conflicts": files_with_name_conflicts,
            "focus_usages": self._nonZeroCounters(focus_usages),
            "running": running,
            "finished": finished,
            "stopped": stopped,
            "stop_requested": stop_requested,
            "current_path": current_path,
            "extensions": self._nonZeroCounters(extensions),
            "formats": self._nonZeroCounters(formats),
            "sources": self._nonZeroCounters(sources),
        }
        if error:
            payload["error"] = error
        return payload

    @staticmethod
    def _normalizeChecksSingleSourceOfTruth(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "photos":
            return normalized
        metadata_formats = {"acd", "microsoft", "mwg_regions"}
        metadata_locations = {"any", "embedded", "sidecar"}
        if normalized.startswith("metadata:"):
            parts = normalized.split(":")
            if len(parts) == 3 and parts[1] in metadata_formats and parts[2] in metadata_locations:
                return normalized
        return ""

    def _configuredAnalysisChecks(self) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks = analysis.get("CHECKS") if isinstance(analysis.get("CHECKS"), dict) else {}
        defaults = ConfigService.defaultConfig()["analysis"]["CHECKS"]
        return {
            "DUPLICATE_FACES": bool(checks.get("DUPLICATE_FACES", defaults["DUPLICATE_FACES"])),
            "POSITION_DEVIATIONS": bool(checks.get("POSITION_DEVIATIONS", defaults["POSITION_DEVIATIONS"])),
            "POSITION_DEVIATIONS_INCLUDE_PHOTOS": bool(checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS", defaults["POSITION_DEVIATIONS_INCLUDE_PHOTOS"])),
            "DIMENSION_ISSUES": bool(checks.get("DIMENSION_ISSUES", defaults["DIMENSION_ISSUES"])),
            "NAME_CONFLICTS": bool(checks.get("NAME_CONFLICTS", defaults["NAME_CONFLICTS"])),
            "NAME_CONFLICTS_INCLUDE_PHOTOS": bool(checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS", defaults["NAME_CONFLICTS_INCLUDE_PHOTOS"])),
            "SINGLE_SOURCE_OF_TRUTH": self._normalizeChecksSingleSourceOfTruth(
                checks.get("SINGLE_SOURCE_OF_TRUTH", defaults["SINGLE_SOURCE_OF_TRUTH"])
            ),
        }

    def _runFileAnalysis(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        job_id: str,
    ) -> None:
        started_at = self._timestamp_now()
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        configured_extensions = self.files.effectiveImageExtensions()
        analysis_checks = self._configuredAnalysisChecks()
        extension_counts: Dict[str, int] = {ext: 0 for ext in configured_extensions}
        source_counts: Dict[str, int] = {}
        format_counts: Dict[str, int] = {}
        focus_usage_counts: Dict[str, int] = {}
        matching_files: List[str] = []
        distinct_person_names = set()
        files_seen_total = 0
        files_matched_total = 0
        files_analyzed = 0
        files_with_sidecar = 0
        files_with_embedded_xmp = 0
        files_with_face_metadata = 0
        files_with_mwg_applied_to_dimensions = 0
        files_with_mwg_dimension_mismatch = 0
        files_with_mwg_orientation_transform_risk = 0
        faces_total = 0
        faces_named = 0
        faces_unnamed = 0
        directories_read = 0
        dimension_mismatch_paths: List[str] = []
        duplicate_faces_paths: List[str] = []
        position_deviation_paths: List[str] = []
        name_conflict_paths: List[str] = []
        dimension_mismatch_entries: List[Dict[str, Any]] = []
        duplicate_face_entries: List[Dict[str, Any]] = []
        position_deviation_entries: List[Dict[str, Any]] = []
        name_conflict_entries: List[Dict[str, Any]] = []
        reverse_face_match_entries: List[Dict[str, Any]] = []
        files_with_duplicate_faces: Optional[int] = None
        files_with_face_position_deviations: Optional[int] = None
        files_with_dimension_issues: Optional[int] = 0 if analysis_checks["DIMENSION_ISSUES"] else None
        files_with_name_conflicts: Optional[int] = 0 if analysis_checks["NAME_CONFLICTS"] else None

        if not shared_folder:
            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder="",
                status="failed",
                finished=True,
                findings_by_type={
                    "dimension_issues": [],
                    "duplicate_faces": [],
                    "position_deviations": [],
                    "name_conflicts": [],
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder="",
                status="failed",
                finished=True,
                entries=[],
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder="",
                    configured_extensions=configured_extensions,
                    status="failed",
                    phase="discovery",
                    message="Shared folder not found.",
                    directories_read=0,
                    files_seen_total=0,
                    files_matched_total=0,
                    files_analyzed=0,
                    files_with_sidecar=0,
                    files_with_embedded_xmp=0,
                    files_with_face_metadata=0,
                    files_with_mwg_applied_to_dimensions=0,
                    files_with_mwg_dimension_mismatch=0,
                    files_with_mwg_orientation_transform_risk=0,
                    faces_total=0,
                    faces_named=0,
                    faces_unnamed=0,
                    persons_distinct_names=set(),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages={},
                    extensions={},
                    formats={},
                    sources={},
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                )
            )
            self._file_analysis_thread = None
            return

        self._setFileAnalysisProgress(
            running=True,
            finished=False,
            stopped=False,
            status="running",
            phase="discovery",
            message="Scanning files...",
            job_id=job_id,
            started_at=started_at,
            last_updated_at=started_at,
            shared_folder=shared_folder,
            configured_extensions=configured_extensions,
            directories_read=0,
            files_seen_total=0,
            files_matched_total=0,
            files_analyzed=0,
            files_with_sidecar=0,
            files_with_embedded_xmp=0,
            files_with_face_metadata=0,
            files_with_mwg_applied_to_dimensions=0,
            files_with_mwg_dimension_mismatch=0,
            files_with_mwg_orientation_transform_risk=0,
            analysis_progress={"current": 0, "total": 0},
            faces_total=0,
            faces_named=0,
            faces_unnamed=0,
            persons_distinct_by_name=0,
            files_with_duplicate_faces=files_with_duplicate_faces,
            files_with_face_position_deviations=files_with_face_position_deviations,
            files_with_dimension_issues=files_with_dimension_issues,
            files_with_name_conflicts=files_with_name_conflicts,
            current_path="",
            extensions={},
            focus_usages={},
            formats={},
            sources={},
        )
        self._writeAllFileAnalysisCheckFindings(
            job_id=job_id,
            started_at=started_at,
            shared_folder=shared_folder,
            status="running",
            finished=False,
            findings_by_type={
                "dimension_issues": [],
                "duplicate_faces": [],
                "position_deviations": [],
                "name_conflicts": [],
            },
        )
        self._writeReverseFaceMatchCandidates(
            job_id=job_id,
            started_at=started_at,
            shared_folder=shared_folder,
            status="running",
            finished=False,
            entries=[],
        )

        try:
            for dirpath, dirnames, filenames in os.walk(shared_folder):
                dirnames[:] = [dirname for dirname in dirnames if dirname != "@eaDir"]
                directories_read += 1
                self._setFileAnalysisProgress(
                    directories_read=directories_read,
                    current_path=str(dirpath),
                    last_updated_at=self._timestamp_now(),
                )
                if self._shouldStopFileAnalysis():
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        entries=reverse_face_match_entries,
                    )
                    self._persistFileAnalysisResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="stopped",
                            phase="discovery",
                            message=f"Discovery stopped. 0 of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=0,
                            files_with_sidecar=0,
                            files_with_embedded_xmp=0,
                            files_with_face_metadata=0,
                            files_with_mwg_applied_to_dimensions=0,
                            files_with_mwg_dimension_mismatch=0,
                            files_with_mwg_orientation_transform_risk=0,
                            faces_total=0,
                            faces_named=0,
                            faces_unnamed=0,
                            persons_distinct_names=set(),
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages={},
                            extensions=extension_counts,
                            formats={},
                            sources={},
                            current_path=str(dirpath),
                            running=False,
                            finished=True,
                            stopped=True,
                            stop_requested=False,
                        )
                    )
                    self._file_analysis_thread = None
                    return
                for filename in filenames:
                    current_path = str(Path(dirpath) / filename)
                    if "@eaDir" in Path(current_path).parts:
                        continue
                    files_seen_total += 1
                    extension = Path(filename).suffix.lower().lstrip(".")
                    if extension in extension_counts:
                        files_matched_total += 1
                        extension_counts[extension] += 1
                        matching_files.append(current_path)
                    self._setFileAnalysisProgress(
                        files_seen_total=files_seen_total,
                        files_matched_total=files_matched_total,
                        current_path=current_path,
                        last_updated_at=self._timestamp_now(),
                        extensions=self._nonZeroCounters(extension_counts),
                    )
                    if self._shouldStopFileAnalysis():
                        self._writeAllFileAnalysisCheckFindings(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            status="stopped",
                            finished=True,
                            findings_by_type={
                                "dimension_issues": dimension_mismatch_entries,
                                "duplicate_faces": duplicate_face_entries,
                                "position_deviations": position_deviation_entries,
                                "name_conflicts": name_conflict_entries,
                            },
                        )
                        self._writeReverseFaceMatchCandidates(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            status="stopped",
                            finished=True,
                            entries=reverse_face_match_entries,
                        )
                        self._persistFileAnalysisResult(
                            self._buildFileAnalysisPayload(
                                job_id=job_id,
                                started_at=started_at,
                                shared_folder=shared_folder,
                                configured_extensions=configured_extensions,
                                status="stopped",
                                phase="discovery",
                                message=f"Discovery stopped. 0 of {files_matched_total} files analyzed.",
                                directories_read=directories_read,
                                files_seen_total=files_seen_total,
                                files_matched_total=files_matched_total,
                                files_analyzed=0,
                                files_with_sidecar=0,
                                files_with_embedded_xmp=0,
                                files_with_face_metadata=0,
                                files_with_mwg_applied_to_dimensions=0,
                                files_with_mwg_dimension_mismatch=0,
                                files_with_mwg_orientation_transform_risk=0,
                                faces_total=0,
                                faces_named=0,
                                faces_unnamed=0,
                                persons_distinct_names=set(),
                                files_with_duplicate_faces=files_with_duplicate_faces,
                                files_with_face_position_deviations=files_with_face_position_deviations,
                                files_with_dimension_issues=files_with_dimension_issues,
                                files_with_name_conflicts=files_with_name_conflicts,
                                focus_usages={},
                                extensions=extension_counts,
                                formats={},
                                sources={},
                                current_path=current_path,
                                running=False,
                                finished=True,
                                stopped=True,
                                stop_requested=False,
                            )
                        )
                        self._file_analysis_thread = None
                        return

            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="running",
                    phase="analysis",
                    message=f"Analyzing face metadata in {files_matched_total} matching files...",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=0,
                    files_with_sidecar=0,
                    files_with_embedded_xmp=0,
                    files_with_face_metadata=0,
                    files_with_mwg_applied_to_dimensions=0,
                    files_with_mwg_dimension_mismatch=0,
                    files_with_mwg_orientation_transform_risk=0,
                    faces_total=0,
                    faces_named=0,
                    faces_unnamed=0,
                    persons_distinct_names=set(),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages={},
                    extensions=extension_counts,
                    formats={},
                    sources={},
                    current_path="",
                    running=True,
                    finished=False,
                    stopped=False,
                    stop_requested=self._shouldStopFileAnalysis(),
                )
            )

            for image_path in matching_files:
                if self._shouldStopFileAnalysis():
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="stopped",
                        finished=True,
                        entries=reverse_face_match_entries,
                    )
                    self._persistFileAnalysisResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="stopped",
                            phase="analysis",
                            message=f"Analysis stopped. {files_analyzed} of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=files_analyzed,
                            files_with_sidecar=files_with_sidecar,
                            files_with_embedded_xmp=files_with_embedded_xmp,
                            files_with_face_metadata=files_with_face_metadata,
                            files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                            files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                            files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                            faces_total=faces_total,
                            faces_named=faces_named,
                            faces_unnamed=faces_unnamed,
                            persons_distinct_names=distinct_person_names,
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages=focus_usage_counts,
                            extensions=extension_counts,
                            formats=format_counts,
                            sources=source_counts,
                            current_path=image_path,
                            running=False,
                            finished=True,
                            stopped=True,
                            stop_requested=False,
                        )
                    )
                    self._file_analysis_thread = None
                    return

                metadata_payload = self._readImageMetadata(image_path, include_unnamed_acd=True)
                include_photos_for_position_deviations = bool(analysis_checks.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS"))
                include_photos_for_name_conflicts = bool(analysis_checks.get("NAME_CONFLICTS_INCLUDE_PHOTOS"))
                include_photos_for_checks = include_photos_for_position_deviations or include_photos_for_name_conflicts
                photo_faces = self._loadPhotoFacesForImage(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                ) if include_photos_for_checks else []
                analysis = self.files.analyzeMetadata(
                    metadata_payload,
                    comparison_faces=[face.to_dict() for face in photo_faces],
                    include_position_deviation_comparison_faces=include_photos_for_position_deviations,
                    include_name_conflict_comparison_faces=include_photos_for_name_conflicts,
                )
                reverse_face_match_entries.extend(
                    self._buildReverseFaceMatchCandidateEntry(image_path=image_path, metadata_face=face)
                    for face in metadata_payload.faces
                    if not str(face.name or "").strip()
                )
                files_analyzed += 1
                if analysis.get("has_sidecar"):
                    files_with_sidecar += 1
                if str(analysis.get("xmp_source") or "").startswith("embedded_xmp_"):
                    files_with_embedded_xmp += 1
                if analysis.get("files_with_face_metadata"):
                    files_with_face_metadata += 1
                files_with_mwg_applied_to_dimensions += int(analysis.get("files_with_mwg_applied_to_dimensions") or 0)
                files_with_mwg_dimension_mismatch += int(analysis.get("files_with_mwg_dimension_mismatch") or 0)
                files_with_mwg_orientation_transform_risk += int(analysis.get("files_with_mwg_orientation_transform_risk") or 0)
                if analysis_checks["DIMENSION_ISSUES"]:
                    files_with_dimension_issues = files_with_mwg_dimension_mismatch
                if analysis_checks["DUPLICATE_FACES"]:
                    files_with_duplicate_faces = (files_with_duplicate_faces or 0) + int(analysis.get("files_with_duplicate_faces") or 0)
                    if analysis.get("files_with_duplicate_faces"):
                        duplicate_faces_paths.append(image_path)
                        duplicate_face_entries.extend(self._buildDuplicateFaceReviewEntries(image_path, analysis))
                if analysis_checks["POSITION_DEVIATIONS"]:
                    files_with_face_position_deviations = (files_with_face_position_deviations or 0) + int(analysis.get("files_with_face_position_deviations") or 0)
                    if analysis.get("files_with_face_position_deviations"):
                        position_deviation_paths.append(image_path)
                        position_deviation_entries.extend(self._buildPositionDeviationReviewEntries(image_path, analysis, photo_faces))
                if analysis_checks["NAME_CONFLICTS"]:
                    files_with_name_conflicts = (files_with_name_conflicts or 0) + int(analysis.get("files_with_name_conflicts") or 0)
                    if analysis.get("files_with_name_conflicts"):
                        name_conflict_paths.append(image_path)
                        name_conflict_entries.extend(self._buildNameConflictReviewEntries(image_path, analysis, photo_faces))
                if analysis.get("files_with_mwg_dimension_mismatch"):
                    dimension_mismatch_paths.append(image_path)
                    review_entry = self._buildDimensionMismatchReviewEntry(image_path, analysis)
                    if review_entry:
                        dimension_mismatch_entries.append(review_entry)
                    self._writeFileAnalysisCheckFindings(
                        finding_type="dimension_issues",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=dimension_mismatch_entries,
                    )
                if analysis.get("files_with_duplicate_faces"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="duplicate_faces",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=duplicate_face_entries,
                    )
                if analysis.get("files_with_face_position_deviations"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="position_deviations",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=position_deviation_entries,
                    )
                if analysis.get("files_with_name_conflicts"):
                    self._writeFileAnalysisCheckFindings(
                        finding_type="name_conflicts",
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings=name_conflict_entries,
                    )

                faces_total += int(analysis.get("faces_total") or 0)
                faces_named += int(analysis.get("faces_named") or 0)
                faces_unnamed += int(analysis.get("faces_unnamed") or 0)
                for key, value in (analysis.get("focus_usages") or {}).items():
                    self._incrementCounter(focus_usage_counts, str(key), int(value))

                for face in metadata_payload.faces:
                    name = str(face.name or "").strip()
                    if name:
                        distinct_person_names.add(name.casefold())
                    self._incrementCounter(source_counts, str(face.source or analysis.get("xmp_source") or "metadata"))
                    self._incrementCounter(format_counts, str(face.source_format or ""))

                self._setFileAnalysisProgress(
                    running=True,
                    finished=False,
                    stopped=False,
                    status="running",
                    phase="analysis",
                    message=f"Analyzing face metadata... {files_analyzed} of {files_matched_total} files analyzed.",
                    current_path=image_path,
                    last_updated_at=self._timestamp_now(),
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    analysis_progress={"current": files_analyzed, "total": files_matched_total},
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_by_name=len(distinct_person_names),
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=self._nonZeroCounters(focus_usage_counts),
                    formats=self._nonZeroCounters(format_counts),
                    sources=self._nonZeroCounters(source_counts),
                )

                if files_analyzed % 25 == 0:
                    self._writeAllFileAnalysisCheckFindings(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        findings_by_type={
                            "dimension_issues": dimension_mismatch_entries,
                            "duplicate_faces": duplicate_face_entries,
                            "position_deviations": position_deviation_entries,
                            "name_conflicts": name_conflict_entries,
                        },
                    )
                    self._writeReverseFaceMatchCandidates(
                        job_id=job_id,
                        started_at=started_at,
                        shared_folder=shared_folder,
                        status="running",
                        finished=False,
                        entries=reverse_face_match_entries,
                    )
                    self.file_analysis.writeLatestResult(
                        self._buildFileAnalysisPayload(
                            job_id=job_id,
                            started_at=started_at,
                            shared_folder=shared_folder,
                            configured_extensions=configured_extensions,
                            status="running",
                            phase="analysis",
                            message=f"Analyzing face metadata... {files_analyzed} of {files_matched_total} files analyzed.",
                            directories_read=directories_read,
                            files_seen_total=files_seen_total,
                            files_matched_total=files_matched_total,
                            files_analyzed=files_analyzed,
                            files_with_sidecar=files_with_sidecar,
                            files_with_embedded_xmp=files_with_embedded_xmp,
                            files_with_face_metadata=files_with_face_metadata,
                            files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                            files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                            files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                            faces_total=faces_total,
                            faces_named=faces_named,
                            faces_unnamed=faces_unnamed,
                            persons_distinct_names=distinct_person_names,
                            files_with_duplicate_faces=files_with_duplicate_faces,
                            files_with_face_position_deviations=files_with_face_position_deviations,
                            files_with_dimension_issues=files_with_dimension_issues,
                            files_with_name_conflicts=files_with_name_conflicts,
                            focus_usages=focus_usage_counts,
                            extensions=extension_counts,
                            formats=format_counts,
                            sources=source_counts,
                            current_path=image_path,
                            running=True,
                            finished=False,
                            stopped=False,
                            stop_requested=self._shouldStopFileAnalysis(),
                        )
                    )

            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="finished",
                finished=True,
                findings_by_type={
                    "dimension_issues": dimension_mismatch_entries,
                    "duplicate_faces": duplicate_face_entries,
                    "position_deviations": position_deviation_entries,
                    "name_conflicts": name_conflict_entries,
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="finished",
                finished=True,
                entries=reverse_face_match_entries,
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="finished",
                    phase="analysis",
                    message=f"Analysis finished. {files_analyzed} of {files_matched_total} files analyzed.",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_names=distinct_person_names,
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=focus_usage_counts,
                    extensions=extension_counts,
                    formats=format_counts,
                    sources=source_counts,
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                )
            )
        except Exception as exc:
            failure_phase = "analysis" if files_matched_total else "discovery"
            self._writeAllFileAnalysisCheckFindings(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="failed",
                finished=True,
                findings_by_type={
                    "dimension_issues": dimension_mismatch_entries,
                    "duplicate_faces": duplicate_face_entries,
                    "position_deviations": position_deviation_entries,
                    "name_conflicts": name_conflict_entries,
                },
            )
            self._writeReverseFaceMatchCandidates(
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status="failed",
                finished=True,
                entries=reverse_face_match_entries,
            )
            self._persistFileAnalysisResult(
                self._buildFileAnalysisPayload(
                    job_id=job_id,
                    started_at=started_at,
                    shared_folder=shared_folder,
                    configured_extensions=configured_extensions,
                    status="failed",
                    phase=failure_phase,
                    message="File analysis failed.",
                    directories_read=directories_read,
                    files_seen_total=files_seen_total,
                    files_matched_total=files_matched_total,
                    files_analyzed=files_analyzed,
                    files_with_sidecar=files_with_sidecar,
                    files_with_embedded_xmp=files_with_embedded_xmp,
                    files_with_face_metadata=files_with_face_metadata,
                    files_with_mwg_applied_to_dimensions=files_with_mwg_applied_to_dimensions,
                    files_with_mwg_dimension_mismatch=files_with_mwg_dimension_mismatch,
                    files_with_mwg_orientation_transform_risk=files_with_mwg_orientation_transform_risk,
                    faces_total=faces_total,
                    faces_named=faces_named,
                    faces_unnamed=faces_unnamed,
                    persons_distinct_names=distinct_person_names,
                    files_with_duplicate_faces=files_with_duplicate_faces,
                    files_with_face_position_deviations=files_with_face_position_deviations,
                    files_with_dimension_issues=files_with_dimension_issues,
                    files_with_name_conflicts=files_with_name_conflicts,
                    focus_usages=focus_usage_counts,
                    extensions=extension_counts,
                    formats=format_counts,
                    sources=source_counts,
                    current_path="",
                    running=False,
                    finished=True,
                    stopped=False,
                    stop_requested=False,
                    error=str(exc),
                )
            )
        finally:
            self._file_analysis_thread = None

    def startFileAnalysisDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        current = self.getFileAnalysisProgress()
        if current.get("running"):
            return current

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        started_at = self._timestamp_now()
        self._setFileAnalysisProgress(
            running=True,
            finished=False,
            stopped=False,
            stop_requested=False,
            status="running",
            phase="discovery",
            message="Starting file analysis...",
            job_id=job_id,
            started_at=started_at,
            finished_at="",
            last_updated_at=started_at,
            shared_folder="",
            configured_extensions=[],
            directories_read=0,
            files_seen_total=0,
            files_matched_total=0,
            files_analyzed=0,
            files_with_sidecar=0,
            files_with_embedded_xmp=0,
            files_with_face_metadata=0,
            files_with_mwg_applied_to_dimensions=0,
            files_with_mwg_dimension_mismatch=0,
            files_with_mwg_orientation_transform_risk=0,
            analysis_progress={"current": 0, "total": 0},
            faces_total=0,
            faces_named=0,
            faces_unnamed=0,
            persons_distinct_by_name=0,
            focus_usages={},
            current_path="",
            extensions={},
            formats={},
            sources={},
        )
        worker = Thread(
            target=self._runFileAnalysis,
            kwargs={
                "user_key": user_key,
                "cookies": cookies,
                "base_url": base_url,
                "job_id": job_id,
            },
            daemon=True,
        )
        self._file_analysis_thread = worker
        worker.start()
        return self.getFileAnalysisProgress()

    @staticmethod
    def _buildPhotoImagePath(shared_folder: str, folder_name: str, filename: str) -> str:
        folder_relative = folder_name.strip()
        if folder_relative.startswith("/"):
            folder_relative = folder_relative.lstrip("/")

        shared_folder_name = Path(shared_folder).name
        if shared_folder_name and folder_relative.startswith(f"{shared_folder_name}/"):
            folder_relative = folder_relative[len(shared_folder_name) + 1:]

        if folder_relative:
            return str(Path(shared_folder) / folder_relative / filename)
        return str(Path(shared_folder) / filename)

    def startFaceMatchingDiscovery(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str = "search_photo_face_in_file",
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_from_progress: bool = False,
    ) -> Dict[str, Any]:
        current = self.getFaceMatchingProgress(user_key)
        worker = self._face_matching_threads.get(user_key)
        if current.get("running") and worker and worker.is_alive():
            return current

        resume_cursor = current.get("resume_cursor") if resume_from_progress and isinstance(current.get("resume_cursor"), dict) else {}
        cursor_skip_face_ids = resume_cursor.get("skip_face_ids") if isinstance(resume_cursor.get("skip_face_ids"), list) else []
        normalized_action = str(action or "search_photo_face_in_file").strip().lower()
        combined_skip_face_ids = list(skip_face_ids or [])
        combined_skip_targets = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        for face_id in cursor_skip_face_ids:
            try:
                normalized_face_id = int(face_id)
            except Exception:
                continue
            if normalized_face_id not in combined_skip_face_ids:
                combined_skip_face_ids.append(normalized_face_id)
        cursor_skip_targets = resume_cursor.get("skip_targets") if isinstance(resume_cursor.get("skip_targets"), list) else []
        for token in cursor_skip_targets:
            normalized_token = str(token or "").strip()
            if normalized_token and normalized_token not in combined_skip_targets:
                combined_skip_targets.append(normalized_token)
        if resume_cursor:
            auto = bool(resume_cursor.get("auto", auto))
            save_only = bool(resume_cursor.get("save_only", save_only))
            normalized_action = str(resume_cursor.get("action") or normalized_action).strip().lower() or normalized_action

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            finished=False,
            paused=False,
            auth_required=False,
            stop_requested=False,
            action=normalized_action,
            result=None,
            error="",
            auto=auto,
            save_only=save_only,
            persons_read=0,
            images_read=0,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=combined_skip_face_ids,
                skip_targets=combined_skip_targets,
                transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
                auto=auto,
                save_only=save_only,
                action=normalized_action,
            ),
        )
        worker = Thread(
            target=self._runFaceMatching,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "action": normalized_action,
                "limit": limit,
                "offset": offset,
                "skip_face_ids": combined_skip_face_ids,
                "skip_targets": combined_skip_targets,
                "auto": auto,
                "save_only": save_only,
                "resume_cursor": resume_cursor if resume_cursor else None,
            },
            daemon=True,
        )
        self._face_matching_threads[user_key] = worker
        worker.start()
        return self.getFaceMatchingProgress(user_key)
    
    def searchPhotoFaceInFile(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        known_persons_cache: Optional[List[Dict[str, Any]]] = None
        saved_entries: List[Dict[str, Any]] = []
        skip_face_ids_set = {
            int(face_id) for face_id in (skip_face_ids or [])
            if isinstance(face_id, int) or str(face_id).isdigit()
        }
        resume_skip_face_ids = resume_cursor.get("skip_face_ids") if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_face_ids"), list) else []
        skip_face_ids_set.update(
            int(face_id) for face_id in resume_skip_face_ids
            if isinstance(face_id, int) or str(face_id).isdigit()
        )
        persons_read = 0
        images_read = 0
        faces_read = 0
        metadata_faces_read = 0
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_photo_face_in_file",
            persons_read=0,
            images_read=0,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=transferred_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=list(skip_face_ids_set),
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
            ),
        )
        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                if save_only:
                    self._writeFaceMatchFindings(
                        status="failed",
                        shared_folder="",
                        action="search_photo_face_in_file",
                        auto=auto,
                        save_only=save_only,
                        transferred_count=transferred_count,
                        entries=[],
                    )
                return {
                    "searched": False,
                    "person": None,
                    "image": None,
                    "face": None,
                    "metadata_face": None,
                    "image_path": None,
                    "error": "shared_folder_not_found",
                }

            unknown_persons: List[Dict[str, Any]] = self.photos.sortPersonsForFaceMatch(
                self.photos.listFotoTeamPersonUnknown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    limit=limit,
                    offset=offset,
                    show_more=True,
                    show_hidden=False,
                )
            )
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_unknown_persons_loaded",
                message_params={"count": len(unknown_persons)},
                persons_total=len(unknown_persons),
            )

            for person in unknown_persons:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    return {
                        "searched": False,
                        "stopped": True,
                        "person": None,
                        "image": None,
                        "face": None,
                        "metadata_face": None,
                        "image_path": None,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=list(skip_face_ids_set),
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                        ),
                    }
                person_id = person.get("id")
                if person_id is None:
                    continue

                try:
                    person_id_int = int(person_id)
                except (TypeError, ValueError):
                    continue

                persons_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_person",
                    message_params={"current": persons_read, "total": len(unknown_persons)},
                    persons_read=persons_read,
                    current_person_id=person_id_int,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=list(skip_face_ids_set),
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                    ),
                )

                images = self.photos.listFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    person_id=person_id_int,
                    additional=['thumbnail'],
                )

                for image in images:
                    last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                        user_key=user_key,
                        base_url=base_url,
                        last_keepalive_at=last_keepalive_at,
                    )
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
                        return {
                            "searched": False,
                            "stopped": True,
                            "person": None,
                            "image": None,
                            "face": None,
                            "metadata_face": None,
                            "image_path": None,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=list(skip_face_ids_set),
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                        ),
                    }
                    image_id = image.get("id")
                    if image_id is None:
                        continue

                    try:
                        image_id_int = int(image_id)
                    except (TypeError, ValueError):
                        continue

                    images_read += 1
                    self._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_checking_image",
                        message_params={"count": images_read},
                        images_read=images_read,
                        current_image_id=image_id_int,
                        resume_cursor=self._buildFaceMatchResumeCursor(
                            skip_face_ids=list(skip_face_ids_set),
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                        ),
                    )

                    faces = self.photos.list_faceFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        id_item=image_id_int
                    )
                    for face in faces:
                        last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                            user_key=user_key,
                            base_url=base_url,
                            last_keepalive_at=last_keepalive_at,
                        )
                        if self._shouldStopFaceMatching(user_key):
                            final_message_key = "face_match:progress_stopped"
                            return {
                                "searched": False,
                                "stopped": True,
                                "person": None,
                                "image": None,
                                "face": None,
                                "metadata_face": None,
                                "image_path": None,
                                "transferred_count": transferred_count,
                                "auto": auto,
                                "resume_cursor": self._buildFaceMatchResumeCursor(
                                    skip_face_ids=list(skip_face_ids_set),
                                    transferred_count=transferred_count,
                                    auto=auto,
                                    save_only=save_only,
                                ),
                            }
                        faces_read += 1
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_face",
                            message_params={"count": faces_read},
                            faces_read=faces_read,
                            current_face_id=face.get("face_id"),
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )
                        face_person_id = face.get("person_id")
                        face_id = face.get("face_id")
                        try:
                            face_person_id_int = int(face_person_id)
                            face_id_int = int(face_id)
                        except (TypeError, ValueError):
                            continue
                        if face_id_int in skip_face_ids_set:
                            continue
                        if face.get("face_name", "") != "":
                            continue
                        if face_person_id_int != person_id_int:
                            continue
                        skip_face_ids_set.add(face_id_int)

                        folder_id = image.get("folder_id")
                        filename = image.get("filename")
                        try:
                            folder_id_int = int(folder_id)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(filename, str) or not filename:
                            continue

                        folder_payload = self.photos.getFotoTeamFolder(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            id_folder=folder_id_int,
                        )
                        folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                        folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                        if not isinstance(folder_name, str) or not folder_name:
                            continue

                        image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                        metadata_payload = self._readImageMetadata(image_path)
                        metadata_faces = metadata_payload.faces
                        metadata_faces_read += len(metadata_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_checking_metadata",
                            message_params={"count": images_read},
                            metadata_faces_read=metadata_faces_read,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )

                        photo_face = PhotosFace(
                            face_id=face_id_int,
                            person_id=person_id_int,
                            bbox=from_photos(face),
                        )
                        indexed_file_faces = [
                            (
                                metadata_index,
                                FileFace(
                                    name=metadata_face.name,
                                    bbox=from_xmp(metadata_face),
                                    source=metadata_face.source,
                                    source_format=metadata_face.source_format,
                                ),
                            )
                            for metadata_index, metadata_face in enumerate(metadata_faces)
                        ]
                        file_faces = [entry[1] for entry in indexed_file_faces]
                        if not file_faces:
                            continue

                        matches = self.face_matcher.match([photo_face], file_faces)
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            "face_match:progress_match_candidates",
                            message_params={"face": faces_read, "count": len(matches)},
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        )
                        if not matches:
                            continue

                        matched = None
                        for candidate in matches:
                            match_name = str(candidate.get("file_name") or "").strip()
                            if match_name:
                                matched = candidate
                                break
                        if not matched:
                            final_message_key = "face_match:progress_only_unnamed_matches"
                            continue

                        file_face_index = matched.get("file_face_index")
                        if not isinstance(file_face_index, int) or file_face_index < 0 or file_face_index >= len(indexed_file_faces):
                            continue
                        metadata_face_index = indexed_file_faces[file_face_index][0]
                        matched_person = None
                        mapped_assignment = None
                        lookup_debug: Dict[str, Any] = {}
                        matched_name = str(matched.get("file_name") or "").strip()
                        if matched_name:
                            if known_persons_cache is None:
                                known_persons_cache = self.photos.sortPersonsForFaceMatch(
                                    self.photos.listFotoTeamPersonKnown(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        additional=["thumbnail"],
                                    )
                                )
                            mapped_assignment = self.name_mappings.findNameMapping(matched_name)
                            if mapped_assignment:
                                mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
                                if mapped_target_name:
                                    matched_person = self.photos.findKnownPersonByName(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        name=mapped_target_name,
                                        known_persons=known_persons_cache,
                                    )
                            if matched_person is None:
                                matched_person = self.photos.findKnownPersonByName(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    name=matched_name,
                                    known_persons=known_persons_cache,
                                )
                            lookup_debug = self.photos.debugKnownPersonLookup(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                name=mapped_target_name if mapped_assignment and str(mapped_assignment.get("target_name") or "").strip() else matched_name,
                                known_persons=known_persons_cache,
                            )
                        final_message_key = "face_match:result_named_match"
                        final_message_params = {}
                        if matched_person:
                            final_message_key = "face_match:result_named_match_with_id"
                            final_message_params = {"id": matched_person.get("id")}

                        if auto and matched_person:
                            matched_person_id = matched_person.get("id") if isinstance(matched_person, dict) else None
                            matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                            if matched_person_id is not None and matched_person_name:
                                self.assignMatchedFaceToKnownPerson(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    face_id=face_id_int,
                                    person_id=int(matched_person_id),
                                    person_name=str(matched_person_name),
                                )
                                transferred_count += 1
                                final_message_key = "face_match:progress_auto_assigned"
                                final_message_params = {"count": transferred_count}
                                self._setFaceMatchingProgressMessage(
                                    user_key,
                                    final_message_key,
                                    message_params=final_message_params,
                                    transferred_count=transferred_count,
                                    resume_cursor=self._buildFaceMatchResumeCursor(
                                        skip_face_ids=list(skip_face_ids_set),
                                        transferred_count=transferred_count,
                                        auto=auto,
                                        save_only=save_only,
                                    ),
                                )
                                continue

                        result_entry = {
                            "searched": True,
                            "person": person,
                            "image": image,
                            "face": face,
                            "metadata_face": metadata_faces[metadata_face_index],
                            "image_path": image_path,
                            "match": matched,
                            "matched_person": matched_person,
                            "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                            "name_mapping": mapped_assignment,
                            "lookup_debug": lookup_debug,
                            "transferred_count": transferred_count,
                            "auto": auto,
                            "resume_cursor": self._buildFaceMatchResumeCursor(
                                skip_face_ids=list(skip_face_ids_set),
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                            ),
                        }
                        if save_only:
                            saved_entries.append(self._normalizeFaceMatchEntry(result_entry))
                            skip_face_ids_set.add(face_id_int)
                            continue
                        return result_entry

            final_message_key = "face_match:result_no_match"
            final_message_params = {}
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="search_photo_face_in_file",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": len(saved_entries),
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids_set),
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                running=False,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                transferred_count=transferred_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids_set),
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                ),
            )

    def searchFileFaceInSources(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        saved_entries: List[Dict[str, Any]] = []
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        skip_target_tokens = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_targets"), list):
            for token in resume_cursor.get("skip_targets") or []:
                normalized = str(token or "").strip()
                if normalized and normalized not in skip_target_tokens:
                    skip_target_tokens.append(normalized)

        source_scope = self._fileFaceMatchSourceScope()
        use_photos = source_scope in {"both", "photos"}
        use_metadata = source_scope in {"both", "metadata"}
        persons_read = 0
        images_read = 0
        faces_read = 0
        target_faces_read = 0
        metadata_faces_read = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="search_file_face_in_sources",
            persons_read=0,
            images_read=0,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=transferred_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=[],
                skip_targets=skip_target_tokens,
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                action="search_file_face_in_sources",
            ),
        )

        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                return {
                    "searched": False,
                    "error": "shared_folder_not_found",
                    "source_scope": source_scope,
                }

            photo_faces_by_path: Dict[str, List[Dict[str, Any]]] = {}
            if use_photos:
                known_persons = self.photos.sortPersonsForFaceMatch(
                    self.photos.listFotoTeamPersonKnown(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        show_more=True,
                        show_hidden=False,
                        additional=["thumbnail"],
                    )
                )
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_known_persons_loaded",
                    message_params={"count": len(known_persons)},
                    persons_read=persons_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                )
                seen_image_ids: Dict[int, str] = {}
                for person in known_persons:
                    last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                        user_key=user_key,
                        base_url=base_url,
                        last_keepalive_at=last_keepalive_at,
                    )
                    if self._shouldStopFaceMatching(user_key):
                        final_message_key = "face_match:progress_stopped"
                        return {
                            "searched": False,
                            "stopped": True,
                            "transferred_count": transferred_count,
                            "auto": auto,
                            "resume_cursor": self._buildFaceMatchResumeCursor(
                                skip_face_ids=[],
                                skip_targets=skip_target_tokens,
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                action="search_file_face_in_sources",
                            ),
                        }
                    person_id = person.get("id")
                    if person_id is None:
                        continue
                    try:
                        person_id_int = int(person_id)
                    except (TypeError, ValueError):
                        continue
                    persons_read += 1
                    self._setFaceMatchingProgress(
                        user_key,
                        persons_read=persons_read,
                        faces_read=faces_read,
                        target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    )
                    images = self.photos.listFotoTeamItems(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        person_id=person_id_int,
                        additional=["thumbnail"],
                    )
                    for image in images:
                        image_id = image.get("id")
                        folder_id = image.get("folder_id")
                        filename = image.get("filename")
                        try:
                            image_id_int = int(image_id)
                            folder_id_int = int(folder_id)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(filename, str) or not filename:
                            continue
                        if image_id_int in seen_image_ids:
                            image_path = seen_image_ids[image_id_int]
                        else:
                            folder_payload = self.photos.getFotoTeamFolder(
                                user_key=user_key,
                                cookies=cookies,
                                base_url=base_url,
                                id_folder=folder_id_int,
                            )
                            folder_data = folder_payload.get("folder") if isinstance(folder_payload, dict) else None
                            folder_name = folder_data.get("name") if isinstance(folder_data, dict) else None
                            if not isinstance(folder_name, str) or not folder_name:
                                continue
                            image_path = self._buildPhotoImagePath(shared_folder, folder_name, filename)
                            seen_image_ids[image_id_int] = image_path
                        if image_path not in photo_faces_by_path:
                            photo_faces_by_path[image_path] = []
                        faces = self.photos.list_faceFotoTeamItems(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            id_item=image_id_int,
                        )
                        for face in faces:
                            face_name = str(face.get("face_name") or "").strip()
                            face_id = face.get("face_id")
                            if not face_name or face_id is None:
                                continue
                            try:
                                face_id_int = int(face_id)
                            except (TypeError, ValueError):
                                continue
                            if any(int(existing.get("face_id")) == face_id_int for existing in photo_faces_by_path[image_path] if existing.get("face_id") is not None):
                                continue
                            face_record = dict(face)
                            face_record["image"] = image
                            face_record["person"] = person
                            photo_faces_by_path[image_path].append(face_record)
                            faces_read += 1
                        self._setFaceMatchingProgress(
                            user_key,
                            persons_read=persons_read,
                            faces_read=faces_read,
                            target_faces_read=target_faces_read,
                            metadata_faces_read=metadata_faces_read,
                        )

            reverse_candidates = self._getReverseFaceMatchCandidateEntries()
            candidate_entries_by_path: Dict[str, List[Dict[str, Any]]] = {}
            if reverse_candidates:
                for entry in reverse_candidates:
                    image_path = str(entry.get("image_path") or "").strip()
                    if not image_path:
                        continue
                    candidate_entries_by_path.setdefault(image_path, []).append(entry)
                candidate_paths = list(candidate_entries_by_path.keys())
            else:
                candidate_paths = self.files.listImageFiles(shared_folder)
            for image_path in candidate_paths:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    return {
                        "searched": False,
                        "stopped": True,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="search_file_face_in_sources",
                        ),
                    }

                images_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_file",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="search_file_face_in_sources",
                    ),
                )

                metadata_payload = self._readImageMetadata(image_path)
                metadata_faces = metadata_payload.faces
                metadata_faces_read += len(metadata_faces)
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_metadata",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="search_file_face_in_sources",
                    ),
                )
                candidate_entries = candidate_entries_by_path.get(image_path, [])
                if candidate_entries:
                    unnamed_targets = []
                    for candidate_entry in candidate_entries:
                        signature = candidate_entry.get("metadata_face")
                        if not isinstance(signature, dict):
                            continue
                        existing_face = self._findFaceBySignature(metadata_faces, signature)
                        if not existing_face or str(existing_face.name or "").strip():
                            continue
                        unnamed_targets.append(existing_face)
                else:
                    unnamed_targets = [face for face in metadata_faces if not str(face.name or "").strip()]
                if not unnamed_targets:
                    continue

                metadata_sources = [
                    face for face in metadata_faces
                    if str(face.name or "").strip()
                ] if use_metadata else []
                photo_sources = photo_faces_by_path.get(image_path, []) if use_photos else []

                for target_face in unnamed_targets:
                    target_faces_read += 1
                    target_token = self._faceMatchTargetToken(image_path=image_path, face=target_face)
                    if target_token in skip_target_tokens:
                        self._setFaceMatchingProgress(
                            user_key,
                            target_faces_read=target_faces_read,
                        )
                        continue

                    matched_entry = self._matchFileFaceInSources(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        image_path=image_path,
                        target_face=target_face,
                        photo_sources=photo_sources,
                        metadata_sources=metadata_sources,
                    )
                    self._setFaceMatchingProgressMessage(
                        user_key,
                        "face_match:progress_match_candidates",
                        message_params={"face": images_read, "count": 1 if matched_entry else 0},
                        images_read=images_read,
                        faces_read=faces_read,
                        target_faces_read=target_faces_read,
                        metadata_faces_read=metadata_faces_read,
                    )
                    if not matched_entry:
                        continue
                    source_name = str(matched_entry.get("source_name") or "").strip()
                    final_message_key = "face_match:result_named_source_match"
                    final_message_params = {}
                    matched_person = matched_entry.get("matched_person") if isinstance(matched_entry.get("matched_person"), dict) else None
                    if matched_person and matched_person.get("id") is not None:
                        final_message_key = "face_match:result_named_source_match_with_id"
                        final_message_params = {"id": matched_person.get("id")}

                    result_entry = dict(matched_entry)
                    result_entry.update({
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens + [target_token],
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="search_file_face_in_sources",
                        ),
                    })

                    if auto:
                        update_result = self.replaceMetadataFaceName(
                            image_path=image_path,
                            face_data=target_face.to_dict(),
                            new_name=source_name,
                        )
                        if update_result.get("updated"):
                            transferred_count += 1
                            skip_target_tokens.append(target_token)
                            final_message_key = "face_match:progress_auto_metadata_assigned"
                            final_message_params = {"count": transferred_count}
                            self._setFaceMatchingProgressMessage(
                                user_key,
                                final_message_key,
                                message_params=final_message_params,
                                transferred_count=transferred_count,
                                resume_cursor=self._buildFaceMatchResumeCursor(
                                    skip_face_ids=[],
                                    skip_targets=skip_target_tokens,
                                    transferred_count=transferred_count,
                                    auto=auto,
                                    save_only=save_only,
                                    action="search_file_face_in_sources",
                                ),
                            )
                            continue

                    if save_only:
                        saved_entries.append(self._normalizeFaceMatchEntry(result_entry))
                        skip_target_tokens.append(target_token)
                        continue
                    return result_entry

            final_message_key = "face_match:result_no_match"
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_metadata_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="search_file_face_in_sources",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": len(saved_entries),
                "source_scope": source_scope,
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                running=False,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="search_file_face_in_sources",
                ),
            )

    def searchMissingPhotosFaces(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        skip_targets: Optional[List[str]] = None,
        auto: bool = False,
        save_only: bool = False,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_keepalive_at = monotonic()
        saved_entries: List[Dict[str, Any]] = []
        transferred_count = int(resume_cursor.get("transferred_count") or 0) if isinstance(resume_cursor, dict) else 0
        skip_target_tokens = [str(value) for value in (skip_targets or []) if str(value or "").strip()]
        if isinstance(resume_cursor, dict) and isinstance(resume_cursor.get("skip_targets"), list):
            for token in resume_cursor.get("skip_targets") or []:
                normalized = str(token or "").strip()
                if normalized and normalized not in skip_target_tokens:
                    skip_target_tokens.append(normalized)

        persons_read = 0
        images_read = 0
        faces_read = 0
        target_faces_read = 0
        metadata_faces_read = 0
        final_message_key = "face_match:progress_finished"
        final_message_params: Dict[str, Any] = {}
        known_persons_cache: Optional[List[Dict[str, Any]]] = None

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            stop_requested=False,
            action="mark_missing_photos_faces",
            persons_read=0,
            images_read=0,
            faces_read=0,
            target_faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=transferred_count,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=[],
                skip_targets=skip_target_tokens,
                transferred_count=transferred_count,
                auto=auto,
                save_only=save_only,
                action="mark_missing_photos_faces",
            ),
        )

        try:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            if not shared_folder:
                final_message_key = "face_match:progress_shared_folder_missing"
                return {
                    "searched": False,
                    "error": "shared_folder_not_found",
                }

            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_listing_files",
                message_params={"path": shared_folder},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                ),
            )
            candidate_paths = self.files.listImageFiles(shared_folder)
            self._setFaceMatchingProgressMessage(
                user_key,
                "face_match:progress_files_listed",
                message_params={"count": len(candidate_paths)},
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                total_images=len(candidate_paths),
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                ),
            )
            for image_path in candidate_paths:
                last_keepalive_at = self._refreshFaceMatchingSessionIfNeeded(
                    user_key=user_key,
                    base_url=base_url,
                    last_keepalive_at=last_keepalive_at,
                )
                if self._shouldStopFaceMatching(user_key):
                    final_message_key = "face_match:progress_stopped"
                    return {
                        "searched": False,
                        "stopped": True,
                        "transferred_count": transferred_count,
                        "auto": auto,
                        "resume_cursor": self._buildFaceMatchResumeCursor(
                            skip_face_ids=[],
                            skip_targets=skip_target_tokens,
                            transferred_count=transferred_count,
                            auto=auto,
                            save_only=save_only,
                            action="mark_missing_photos_faces",
                        ),
                    }

                images_read += 1
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_file",
                    message_params={"count": images_read, "total": len(candidate_paths)},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                    ),
                )

                metadata_payload = self._readImageMetadata(image_path)
                metadata_faces = metadata_payload.faces
                metadata_faces_read += len(metadata_faces)
                self._setFaceMatchingProgressMessage(
                    user_key,
                    "face_match:progress_checking_metadata",
                    message_params={"count": images_read},
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    resume_cursor=self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens,
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                    ),
                )

                item = self.photos.findFotoTeamItemByPath(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    shared_folder=shared_folder,
                    image_path=image_path,
                    additional=["thumbnail"],
                )
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id is None:
                    continue
                try:
                    item_id_int = int(item_id)
                except (TypeError, ValueError):
                    continue

                photo_faces = self.photos.list_faceFotoTeamItems(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    id_item=item_id_int,
                )
                faces_read += len(photo_faces)
                self._setFaceMatchingProgress(
                    user_key,
                    images_read=images_read,
                    faces_read=faces_read,
                    target_faces_read=target_faces_read,
                    metadata_faces_read=metadata_faces_read,
                    current_image_id=item_id_int,
                )
                photo_file_faces = [
                    FileFace(
                        name=str(face.get("face_name") or ""),
                        bbox=from_photos(face),
                        source="photos",
                        source_format="PHOTOS",
                    )
                    for face in photo_faces
                    if isinstance(face, dict) and isinstance(face.get("bbox"), dict)
                ]
                target_face = None
                metadata_faces_by_format: Dict[str, int] = {}
                for metadata_face in metadata_faces:
                    source_format = str(metadata_face.source_format or "").strip().upper()
                    if source_format:
                        metadata_faces_by_format[source_format] = metadata_faces_by_format.get(source_format, 0) + 1
                    if target_face is not None:
                        continue
                    if not str(metadata_face.name or "").strip():
                        continue
                    if self._findExistingPhotosFaceMatch(
                        metadata_face=metadata_face,
                        existing_faces=photo_faces,
                    ) is not None:
                        continue
                    target_face = metadata_face
                if target_face is None:
                    continue

                target_faces_read += 1
                target_token = self._faceMatchTargetToken(image_path=image_path, face=target_face)
                if target_token in skip_target_tokens:
                    continue

                if known_persons_cache is None:
                    known_persons_cache = self.photos.sortPersonsForFaceMatch(
                        self.photos.listFotoTeamPersonKnown(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            additional=["thumbnail"],
                        )
                    )

                source_name = str(target_face.name or "").strip()
                matched_person, mapped_assignment, lookup_debug = self._lookupMatchedPersonBySourceName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    source_name=source_name,
                    known_persons_cache=known_persons_cache,
                )

                result_entry = {
                    "action": "mark_missing_photos_faces",
                    "searched": True,
                    "person": matched_person if isinstance(matched_person, dict) else None,
                    "image": item if isinstance(item, dict) else None,
                    "face": to_display_face(target_face),
                    "source_face": to_display_face(target_face),
                    "source_name": source_name,
                    "source_type": "metadata_face",
                    "metadata_face": to_display_face(target_face),
                    "image_path": image_path,
                    "match": {
                        "source_type": "metadata_face",
                        "source": target_face.source,
                        "source_format": target_face.source_format,
                        "file_name": source_name,
                        "iou": 1.0,
                        "photos_faces_count": len(photo_faces),
                        "metadata_faces_by_format": metadata_faces_by_format,
                    },
                    "matched_person": matched_person,
                    "matched_person_id": matched_person.get("id") if isinstance(matched_person, dict) else None,
                    "name_mapping": mapped_assignment,
                    "lookup_debug": lookup_debug,
                    "add_new_faces_to_photos": True,
                    "transferred_count": transferred_count,
                    "auto": auto,
                    "resume_cursor": self._buildFaceMatchResumeCursor(
                        skip_face_ids=[],
                        skip_targets=skip_target_tokens + [target_token],
                        transferred_count=transferred_count,
                        auto=auto,
                        save_only=save_only,
                        action="mark_missing_photos_faces",
                    ),
                }

                if auto and matched_person and matched_person.get("id") is not None:
                    add_result = self.addMatchedMetadataFaceToPhotos(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        image_path=image_path,
                        metadata_face=target_face.to_dict(),
                        person_id=int(matched_person.get("id")),
                    )
                    created_face_id = add_result.get("face_id")
                    matched_person_name = str(matched_person.get("name") or "").strip()
                    if created_face_id is not None and matched_person_name:
                        self.assignMatchedFaceToKnownPerson(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            face_id=int(created_face_id),
                            person_id=int(matched_person.get("id")),
                            person_name=matched_person_name,
                        )
                        transferred_count += 1
                        skip_target_tokens.append(target_token)
                        final_message_key = "face_match:progress_auto_assigned"
                        final_message_params = {"count": transferred_count}
                        self._setFaceMatchingProgressMessage(
                            user_key,
                            final_message_key,
                            message_params=final_message_params,
                            transferred_count=transferred_count,
                            resume_cursor=self._buildFaceMatchResumeCursor(
                                skip_face_ids=[],
                                skip_targets=skip_target_tokens,
                                transferred_count=transferred_count,
                                auto=auto,
                                save_only=save_only,
                                action="mark_missing_photos_faces",
                            ),
                        )
                        continue

                if save_only:
                    saved_entries.append(self._normalizeFaceMatchEntry(result_entry))
                    skip_target_tokens.append(target_token)
                    continue
                return result_entry

            final_message_key = "face_match:result_no_match"
            if auto and transferred_count:
                final_message_key = "face_match:progress_auto_assign_complete"
                final_message_params = {"count": transferred_count}
            if save_only:
                final_message_key = "face_match:progress_findings_saved" if saved_entries else "face_match:progress_findings_empty"
                final_message_params = {"count": len(saved_entries)}
                self._writeFaceMatchFindings(
                    status="finished",
                    shared_folder=shared_folder,
                    action="mark_missing_photos_faces",
                    auto=auto,
                    save_only=save_only,
                    transferred_count=transferred_count,
                    entries=saved_entries,
                )
            return {
                "searched": True,
                "person": None,
                "image": None,
                "face": None,
                "metadata_face": None,
                "image_path": None,
                "transferred_count": transferred_count,
                "auto": auto,
                "save_only": save_only,
                "findings_count": len(saved_entries),
                "resume_cursor": self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                ),
            }
        finally:
            self._setFaceMatchingProgressMessage(
                user_key,
                final_message_key,
                message_params=final_message_params,
                running=False,
                stop_requested=False,
                persons_read=persons_read,
                images_read=images_read,
                faces_read=faces_read,
                target_faces_read=target_faces_read,
                metadata_faces_read=metadata_faces_read,
                transferred_count=transferred_count,
                resume_cursor=self._buildFaceMatchResumeCursor(
                    skip_face_ids=[],
                    skip_targets=skip_target_tokens,
                    transferred_count=transferred_count,
                    auto=auto,
                    save_only=save_only,
                    action="mark_missing_photos_faces",
                ),
            )

    def list_files(self, *, base_path: str, pattern: str = "*") -> Dict[str, object]:
        if pattern == "__configured_images__":
            files = self.files.listImageFiles(base_path=base_path)
        else:
            files = self.files.list_files(base_path=base_path, pattern=pattern)
        return {"count": len(files), "files": files}

    def getFaceMatchFindingEntries(
        self,
        *,
        user_key: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
        auto: bool = False,
    ) -> Dict[str, Any]:
        findings = self.getFaceMatchFindings()
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        resolved_entries = entries
        transferred_count = int(findings.get("transferred_count") or 0)
        if user_key and isinstance(cookies, dict) and base_url:
            known_persons_cache = self.photos.sortPersonsForFaceMatch(
                self.photos.listFotoTeamPersonKnown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    additional=["thumbnail"],
                )
            )
            image_faces_cache: Dict[int, List[Dict[str, Any]]] = {}
            next_entries = []
            findings_changed = False
            for entry in entries:
                if not isinstance(entry, dict):
                    findings_changed = True
                    continue
                if not self._storedFaceMatchEntryExists(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    entry=entry,
                    image_faces_cache=image_faces_cache,
                ):
                    findings_changed = True
                    continue
                resolved_entry = self._resolveStoredFaceMatchEntry(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    entry=entry,
                    known_persons_cache=known_persons_cache,
                )
                action = str(resolved_entry.get("action") or "search_photo_face_in_file").strip().lower()
                if action in {"search_file_face_in_sources", "mark_missing_photos_faces"} and not str(resolved_entry.get("source_name") or "").strip():
                    findings_changed = True
                    continue
                if auto and action in {"search_file_face_in_sources", "mark_missing_photos_faces"}:
                    metadata_face = resolved_entry.get("metadata_face")
                    image_path = str(resolved_entry.get("image_path") or "").strip()
                    source_name = str(resolved_entry.get("source_name") or "").strip()
                    if image_path and isinstance(metadata_face, dict) and source_name:
                        if action == "mark_missing_photos_faces":
                            matched_person = resolved_entry.get("matched_person")
                            matched_person_id = matched_person.get("id") if isinstance(matched_person, dict) else None
                            matched_person_name = str(matched_person.get("name") or "").strip() if isinstance(matched_person, dict) else ""
                            if matched_person_id is not None and matched_person_name:
                                add_result = self.addMatchedMetadataFaceToPhotos(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    image_path=image_path,
                                    metadata_face=metadata_face,
                                    person_id=int(matched_person_id),
                                )
                                created_face_id = add_result.get("face_id")
                                if created_face_id is not None:
                                    self.assignMatchedFaceToKnownPerson(
                                        user_key=user_key,
                                        cookies=cookies,
                                        base_url=base_url,
                                        face_id=int(created_face_id),
                                        person_id=int(matched_person_id),
                                        person_name=matched_person_name,
                                    )
                                    transferred_count += 1
                                    findings_changed = True
                                    continue
                        else:
                            result = self.replaceMetadataFaceName(
                                image_path=image_path,
                                face_data=metadata_face,
                                new_name=source_name,
                            )
                            if result.get("updated"):
                                transferred_count += 1
                                findings_changed = True
                                continue
                if auto and action != "search_file_face_in_sources":
                    matched_person = resolved_entry.get("matched_person")
                    matched_person_id = matched_person.get("id") if isinstance(matched_person, dict) else None
                    matched_person_name = matched_person.get("name") if isinstance(matched_person, dict) else None
                    face = resolved_entry.get("face")
                    face_id = face.get("face_id") if isinstance(face, dict) else None
                    if matched_person_id is not None and matched_person_name and face_id is not None:
                        self.assignMatchedFaceToKnownPerson(
                            user_key=user_key,
                            cookies=cookies,
                            base_url=base_url,
                            face_id=int(face_id),
                            person_id=int(matched_person_id),
                            person_name=str(matched_person_name),
                        )
                        transferred_count += 1
                        findings_changed = True
                        continue
                next_entries.append(resolved_entry)
            resolved_entries = next_entries
            if findings_changed:
                self._persistFaceMatchFindingsEntries(
                    findings=findings,
                    entries=resolved_entries,
                    transferred_count=transferred_count,
                )
        return {
            "status": str(findings.get("status") or ""),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "count": len(resolved_entries),
            "entries": resolved_entries,
            "transferred_count": transferred_count,
            "save_only": bool(findings.get("save_only")),
            "auto": bool(auto or findings.get("auto")),
        }

    def removeFaceMatchFindingMetadataEntry(
        self,
        *,
        image_path: str,
        metadata_face: Dict[str, Any],
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        findings = self.getFaceMatchFindings()
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        remaining_entries = []
        removed_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_image_path = str(entry.get("image_path") or "").strip()
            entry_metadata_face = entry.get("metadata_face")
            if entry_image_path == str(image_path or "").strip() and isinstance(entry_metadata_face, dict):
                if self._faceMatchTargetToken(image_path=entry_image_path, face=entry_metadata_face) == self._faceMatchTargetToken(image_path=image_path, face=metadata_face):
                    removed_count += 1
                    continue
            remaining_entries.append(entry)

        if removed_count == 0:
            return {
                "removed": False,
                "removed_count": 0,
                "remaining_count": len(entries),
                "deleted": False,
            }

        transferred_count = int(findings.get("transferred_count") or 0)
        if increment_transferred_count:
            transferred_count += removed_count

        if not remaining_entries:
            deleted = self.file_analysis.deleteCheckFindings("face_match")
            return {
                "removed": deleted,
                "removed_count": removed_count,
                "remaining_count": 0,
                "deleted": bool(deleted),
                "transferred_count": transferred_count,
            }

        timestamp = self._timestamp_now()
        updated_payload = {
            "job_id": str(findings.get("job_id") or timestamp),
            "started_at": str(findings.get("started_at") or timestamp),
            "finished_at": str(findings.get("finished_at") or timestamp),
            "last_updated_at": timestamp,
            "status": str(findings.get("status") or "finished"),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "action": str(findings.get("action") or "search_photo_face_in_file"),
            "auto": bool(findings.get("auto")),
            "save_only": bool(findings.get("save_only")),
            "transferred_count": transferred_count,
            "count": len(remaining_entries),
            "entries": remaining_entries,
        }
        written = self.file_analysis.writeCheckFindings("face_match", updated_payload)
        return {
            "removed": bool(written),
            "removed_count": removed_count,
            "remaining_count": len(remaining_entries),
            "deleted": False,
            "transferred_count": transferred_count,
        }

    def removeFaceMatchFindingEntry(
        self,
        *,
        face_id: int,
        increment_transferred_count: bool = True,
    ) -> Dict[str, Any]:
        findings = self.getFaceMatchFindings()
        entries = findings.get("entries") if isinstance(findings.get("entries"), list) else []
        remaining_entries = []
        removed_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            face = entry.get("face")
            entry_face_id = None
            if isinstance(face, dict):
                try:
                    entry_face_id = int(face.get("face_id"))
                except (TypeError, ValueError):
                    entry_face_id = None
            if entry_face_id == int(face_id):
                removed_count += 1
                continue
            remaining_entries.append(entry)

        if removed_count == 0:
            return {
                "removed": False,
                "removed_count": 0,
                "remaining_count": len(entries),
                "deleted": False,
            }

        transferred_count = int(findings.get("transferred_count") or 0)
        if increment_transferred_count:
            transferred_count += removed_count

        if not remaining_entries:
            deleted = self.file_analysis.deleteCheckFindings("face_match")
            return {
                "removed": deleted,
                "removed_count": removed_count,
                "remaining_count": 0,
                "deleted": bool(deleted),
                "transferred_count": transferred_count,
            }

        timestamp = self._timestamp_now()
        updated_payload = {
            "job_id": str(findings.get("job_id") or timestamp),
            "started_at": str(findings.get("started_at") or timestamp),
            "finished_at": str(findings.get("finished_at") or timestamp),
            "last_updated_at": timestamp,
            "status": str(findings.get("status") or "finished"),
            "shared_folder": str(findings.get("shared_folder") or ""),
            "action": str(findings.get("action") or "search_photo_face_in_file"),
            "auto": bool(findings.get("auto")),
            "save_only": bool(findings.get("save_only")),
            "transferred_count": transferred_count,
            "count": len(remaining_entries),
            "entries": remaining_entries,
        }
        written = self.file_analysis.writeCheckFindings("face_match", updated_payload)
        return {
            "removed": bool(written),
            "removed_count": removed_count,
            "remaining_count": len(remaining_entries),
            "deleted": False,
            "transferred_count": transferred_count,
        }

    def read_file_text(self, *, path: str, max_bytes: int = 1024 * 1024) -> Dict[str, object]:
        return self.files.read_text(path=path, max_bytes=max_bytes)

    def getSharedFolder(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        folder_name: str = "photo",
    ) -> Optional[str]:
        return self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name=folder_name,
        )

    def assignMatchedFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_id: int,
        person_name: str,
        ) -> Dict[str, Any]:
        return self.photos.assignFaceToPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=person_id,
            person_name=person_name,
        )

    def assignChecksFaceToKnownPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_data: Dict[str, Any],
        person_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        source_format = str(face_data.get("source_format") or "").strip().upper()
        if source_format == "PHOTOS":
            face_id = face_data.get("face_id")
            if face_id is None:
                raise ValueError("photos_face_id_missing")
            return {
                "updated": True,
                "metadata_result": None,
                "add_result": None,
                "assign_result": self.assignMatchedFaceToKnownPerson(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    face_id=int(face_id),
                    person_id=person_id,
                    person_name=person_name,
                ),
            }

        metadata_result = self.replaceMetadataFaceName(
            image_path=image_path,
            face_data=face_data,
            new_name=person_name,
        )
        if not metadata_result.get("updated"):
            return {
                "updated": False,
                "warning": metadata_result.get("warning"),
                "metadata_result": metadata_result,
                "add_result": None,
                "assign_result": None,
            }

        add_result = self.addMatchedMetadataFaceToPhotos(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            image_path=image_path,
            metadata_face=face_data,
            person_id=person_id,
        )
        face_id = add_result.get("face_id")
        if face_id is None:
            raise ValueError("photos_face_create_failed")
        assign_result = self.assignMatchedFaceToKnownPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=int(face_id),
            person_id=person_id,
            person_name=person_name,
        )
        return {
            "updated": True,
            "warning": "",
            "metadata_result": metadata_result,
            "add_result": add_result,
            "assign_result": assign_result,
        }

    def replaceChecksFaceName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        face_data: Dict[str, Any],
        new_name: str,
    ) -> Dict[str, Any]:
        source_format = str(face_data.get("source_format") or "").strip().upper()
        replacement_name = str(new_name or "").strip()
        if source_format != "PHOTOS":
            result = self.replaceMetadataFaceName(
                image_path=image_path,
                face_data=face_data,
                new_name=replacement_name,
            )
            result["operation"] = "metadata_write"
            return result

        face_id = face_data.get("face_id")
        try:
            face_id = int(face_id)
        except (TypeError, ValueError):
            return {
                "updated": False,
                "warning": "checks:warning_photos_face_id_missing",
            }

        lookup_name = replacement_name
        mapped_assignment = self.name_mappings.findNameMapping(replacement_name)
        if isinstance(mapped_assignment, dict):
            mapped_target_name = str(mapped_assignment.get("target_name") or "").strip()
            if mapped_target_name:
                lookup_name = mapped_target_name

        target_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=lookup_name,
        )
        if not isinstance(target_person, dict):
            return {
                "updated": False,
                "warning": "checks:warning_target_person_not_found",
                "details": {
                    "requested_name": replacement_name,
                    "lookup_name": lookup_name,
                },
            }

        try:
            target_person_id = int(target_person.get("id"))
        except (TypeError, ValueError):
            return {
                "updated": False,
                "warning": "checks:warning_target_person_not_found",
                "details": {
                    "requested_name": replacement_name,
                    "lookup_name": lookup_name,
                },
            }

        assign_result = self.assignMatchedFaceToKnownPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_id=target_person_id,
            person_name=str(target_person.get("name") or lookup_name),
        )
        return {
            "updated": True,
            "warning": "",
            "operation": "photos_assign",
            "assign_result": assign_result,
            "target_person": {
                "id": target_person_id,
                "name": str(target_person.get("name") or ""),
            },
            "resolved_name": lookup_name,
        }

    @staticmethod
    def _metadataFaceToPhotosBoundingBox(face: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        normalized_face = to_display_face(face if isinstance(face, dict) else {})
        left = float(normalized_face.get("x") or 0) - (float(normalized_face.get("w") or 0) / 2)
        top = float(normalized_face.get("y") or 0) - (float(normalized_face.get("h") or 0) / 2)
        right = left + float(normalized_face.get("w") or 0)
        bottom = top + float(normalized_face.get("h") or 0)
        return {
            "top_left": {
                "x": max(0.0, min(1.0, left)),
                "y": max(0.0, min(1.0, top)),
            },
            "bottom_right": {
                "x": max(0.0, min(1.0, right)),
                "y": max(0.0, min(1.0, bottom)),
            },
        }

    def addMatchedMetadataFaceToPhotos(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        image_path: str,
        metadata_face: Dict[str, Any],
        person_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        if not shared_folder:
            raise ValueError("shared_folder_not_found")

        item = self.photos.findFotoTeamItemByPath(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            shared_folder=shared_folder,
            image_path=image_path,
            additional=["thumbnail"],
        )
        if not isinstance(item, dict) or item.get("id") is None:
            raise ValueError("photos_item_not_found_for_image")

        item_id = int(item.get("id"))
        candidate_face = PhotosFace(
            face_id=0,
            person_id=0,
            bbox=from_xmp(MetadataFace.from_dict(metadata_face)),
        )
        existing_faces = self.photos.list_faceFotoTeamItems(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            id_item=item_id,
        )
        matched_existing = self._findExistingPhotosFaceMatch(
            metadata_face=MetadataFace.from_dict(metadata_face),
            existing_faces=existing_faces,
        )
        if matched_existing is not None:
            return {
                "created": False,
                "face_id": int(matched_existing.get("face_id")),
                "item_id": item_id,
                "item": item,
                "duplicate": True,
                "existing_match": matched_existing,
            }

        face_id_temp = f"{item_id}-{int(monotonic() * 1000)}"
        add_result = self.photos.addFaceToItem(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            id_item=item_id,
            face_bbox=self._metadataFaceToPhotosBoundingBox(metadata_face),
            face_id_temp=face_id_temp,
            person_id=int(person_id) if person_id is not None else None,
        )
        created_face_id: Optional[int] = None
        for entry in add_result.get("list", []) if isinstance(add_result.get("list"), list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("face_id_temp") or "") != face_id_temp:
                continue
            try:
                created_face_id = int(entry.get("face_id"))
            except (TypeError, ValueError):
                created_face_id = None
            break
        if created_face_id is None:
            raise ValueError("photos_face_create_failed")
        return {
            "created": True,
            "face_id": created_face_id,
            "item_id": item_id,
            "item": item,
            "result": add_result,
        }

    def _findExistingPhotosFaceMatch(
        self,
        *,
        metadata_face: MetadataFace,
        existing_faces: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        candidate_face = PhotosFace(
            face_id=0,
            person_id=0,
            bbox=from_xmp(metadata_face),
        )
        existing_file_faces: List[FileFace] = []
        existing_lookup: List[Dict[str, Any]] = []
        for existing_face in existing_faces:
            if not isinstance(existing_face, dict) or not isinstance(existing_face.get("bbox"), dict):
                continue
            existing_file_faces.append(
                FileFace(
                    name=str(existing_face.get("face_name") or ""),
                    bbox=from_photos(existing_face),
                    source="photos",
                    source_format="PHOTOS",
                )
            )
            existing_lookup.append(existing_face)
        if not existing_file_faces:
            return None

        existing_matches = self.face_matcher.match([candidate_face], existing_file_faces)
        if not existing_matches:
            candidate_bbox = from_xmp(metadata_face)
            overlap_matches: List[Tuple[float, Dict[str, Any]]] = []
            for existing_face in existing_lookup:
                overlap_score = self._photosOverlapScore(
                    candidate_bbox,
                    from_photos(existing_face),
                )
                if overlap_score >= 0.5:
                    overlap_matches.append((overlap_score, existing_face))
            if not overlap_matches:
                return None
            overlap_matches.sort(key=lambda entry: entry[0], reverse=True)
            return overlap_matches[0][1]

        matched_existing = max(existing_matches, key=lambda match: float(match.get("iou") or 0))
        return existing_lookup[matched_existing["file_face_index"]]

    @staticmethod
    def _photosOverlapScore(left: Any, right: Any) -> float:
        try:
            overlap_width = min(float(left.x2), float(right.x2)) - max(float(left.x1), float(right.x1))
            overlap_height = min(float(left.y2), float(right.y2)) - max(float(left.y1), float(right.y1))
        except (AttributeError, TypeError, ValueError):
            return 0.0
        if overlap_width <= 0 or overlap_height <= 0:
            return 0.0

        overlap_area = overlap_width * overlap_height
        left_area = max(0.0, float(left.x2) - float(left.x1)) * max(0.0, float(left.y2) - float(left.y1))
        right_area = max(0.0, float(right.x2) - float(right.x1)) * max(0.0, float(right.y2) - float(right.y1))
        smaller_area = min(left_area, right_area)
        if smaller_area <= 0:
            return 0.0
        return overlap_area / smaller_area

    def createMatchedFaceAsPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        face_id: int,
        person_name: str,
    ) -> Dict[str, Any]:
        return self.photos.createPersonFromFace(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            face_id=face_id,
            person_name=person_name,
        )

    def _listAllPhotoItemsForPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: int,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        offset = 0
        page_size = 200
        while True:
            page = self.photos.listFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                person_id=person_id,
                offset=offset,
                limit=page_size,
            )
            if not page:
                break
            items.extend([item for item in page if isinstance(item, dict)])
            if len(page) < page_size:
                break
            offset += page_size
        return items

    def _collectPhotoFaceIdsForPerson(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person_id: int,
    ) -> List[int]:
        face_ids: List[int] = []
        seen: set[int] = set()
        for item in self._listAllPhotoItemsForPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            person_id=person_id,
        ):
            try:
                item_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            for face in self.photos.list_faceFotoTeamItems(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                id_item=item_id,
            ):
                try:
                    face_id = int(face.get("face_id"))
                    current_person_id = int(face.get("person_id"))
                except (TypeError, ValueError):
                    continue
                if current_person_id != int(person_id) or face_id in seen:
                    continue
                seen.add(face_id)
                face_ids.append(face_id)
        return face_ids

    @staticmethod
    def _extractPersonId(person_payload: Dict[str, Any]) -> Optional[int]:
        if not isinstance(person_payload, dict):
            return None
        candidates = [person_payload]
        if isinstance(person_payload.get("person"), dict):
            candidates.append(person_payload.get("person"))
        if isinstance(person_payload.get("list"), list):
            candidates.extend(item for item in person_payload.get("list") if isinstance(item, dict))
        for candidate in candidates:
            try:
                return int(candidate.get("id"))
            except (TypeError, ValueError):
                continue
        return None

    def _normalizePhotosPersonByMapping(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        person: Dict[str, Any],
        known_persons: List[Dict[str, Any]],
        mapping_lookup: Dict[str, str],
    ) -> Dict[str, Any]:
        source_name = str(person.get("name") or "").strip()
        source_key = NameMappingService._normalize_name_value(source_name)
        target_name = str(mapping_lookup.get(source_key) or "").strip()
        if not source_name or not target_name:
            return {"updated": False, "faces_reassigned": 0}
        if NameMappingService._normalize_name_value(target_name) == source_key:
            return {"updated": False, "faces_reassigned": 0}

        try:
            source_person_id = int(person.get("id"))
        except (TypeError, ValueError):
            return {"updated": False, "faces_reassigned": 0}

        face_ids = self._collectPhotoFaceIdsForPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            person_id=source_person_id,
        )
        if not face_ids:
            return {"updated": False, "faces_reassigned": 0}

        target_person = self.photos.findKnownPersonByName(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name=target_name,
            known_persons=known_persons,
        )
        if target_person is not None:
            try:
                target_person_id = int(target_person.get("id"))
            except (TypeError, ValueError):
                target_person_id = None
        else:
            target_person_id = None

        if target_person_id is None:
            created = self.createMatchedFaceAsPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=face_ids[0],
                person_name=target_name,
            )
            target_person_id = self._extractPersonId(created)
            if target_person_id is None:
                refreshed_target = self.photos.findKnownPersonByName(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    name=target_name,
                )
                if refreshed_target is not None:
                    try:
                        target_person_id = int(refreshed_target.get("id"))
                    except (TypeError, ValueError):
                        target_person_id = None
            if target_person_id is None:
                return {"updated": False, "faces_reassigned": 0, "error": "photos_person_create_failed"}

            known_persons.append({"id": target_person_id, "name": target_name})
            remaining_face_ids = face_ids[1:]
            reassigned = 1
        else:
            remaining_face_ids = face_ids
            reassigned = 0

        for face_id in remaining_face_ids:
            self.assignMatchedFaceToKnownPerson(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                face_id=int(face_id),
                person_id=int(target_person_id),
                person_name=target_name,
            )
            reassigned += 1

        return {
            "updated": reassigned > 0,
            "faces_reassigned": reassigned,
            "source_person_id": source_person_id,
            "target_person_id": int(target_person_id),
            "source_name": source_name,
            "target_name": target_name,
        }

    def startCleanupRun(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        targets: List[str],
    ) -> Dict[str, Any]:
        normalized_action = self._normalizeCleanupAction(action)
        normalized_targets = self._normalizeCleanupTargets(targets)
        current = self.getCleanupProgress(user_key, normalized_action)
        state_key = self._cleanupStateKey(user_key, normalized_action)
        worker = self._cleanup_threads.get(state_key)
        if current.get("running") and worker and worker.is_alive():
            return current

        self._setCleanupProgressMessage(
            user_key,
            normalized_action,
            "cleanup:status_preparing",
            running=True,
            finished=False,
            stop_requested=False,
            targets=normalized_targets,
            mappings_count=len(self.name_mappings.readNameMappings()),
            persons_total=0,
            persons_scanned=0,
            persons_updated=0,
            faces_reassigned=0,
            files_scanned=0,
            files_updated=0,
            metadata_faces_updated=0,
            current_path="",
            current_name="",
            warning="",
        )

        worker = Thread(
            target=self._runCleanupNameNormalization,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "action": normalized_action,
                "targets": normalized_targets,
            },
            daemon=True,
        )
        self._cleanup_threads[state_key] = worker
        worker.start()
        return self.getCleanupProgress(user_key, normalized_action)

    def _runCleanupNameNormalization(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        action: str,
        targets: List[str],
    ) -> None:
        normalized_action = self._normalizeCleanupAction(action)
        normalized_targets = self._normalizeCleanupTargets(targets)
        mappings = self.name_mappings.readNameMappings()
        mapping_lookup = self._normalizedNameMappingTable(mappings)
        if not mapping_lookup:
            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_no_mappings",
                running=False,
                finished=True,
                targets=normalized_targets,
                mappings_count=0,
            )
            return

        persons_scanned = 0
        persons_total = 0
        persons_updated = 0
        faces_reassigned = 0
        files_scanned = 0
        files_updated = 0
        metadata_faces_updated = 0
        warning = ""

        try:
            if "PHOTOS" in normalized_targets:
                known_persons = self.photos.listFotoTeamPersonKnown(
                    user_key=user_key,
                    cookies=cookies,
                    base_url=base_url,
                    show_more=True,
                    show_hidden=False,
                )
                persons_total = len(known_persons)
                for person in list(known_persons):
                    if self._shouldStopCleanup(user_key, normalized_action):
                        self._setCleanupProgressMessage(
                            user_key,
                            normalized_action,
                            "cleanup:progress_stopped",
                            running=False,
                            finished=True,
                            stop_requested=True,
                            targets=normalized_targets,
                            mappings_count=len(mapping_lookup),
                            persons_total=persons_total,
                            persons_scanned=persons_scanned,
                            persons_updated=persons_updated,
                            faces_reassigned=faces_reassigned,
                            files_scanned=files_scanned,
                            files_updated=files_updated,
                            metadata_faces_updated=metadata_faces_updated,
                        )
                        return
                    persons_scanned += 1
                    current_name = str(person.get("name") or "").strip()
                    self._setCleanupProgressMessage(
                        user_key,
                        normalized_action,
                        "cleanup:progress_checking_person",
                        message_params={"count": persons_scanned, "name": current_name},
                        running=True,
                        finished=False,
                        targets=normalized_targets,
                        mappings_count=len(mapping_lookup),
                        persons_total=persons_total,
                        persons_scanned=persons_scanned,
                        persons_updated=persons_updated,
                        faces_reassigned=faces_reassigned,
                        files_scanned=files_scanned,
                        files_updated=files_updated,
                        metadata_faces_updated=metadata_faces_updated,
                        current_name=current_name,
                    )
                    result = self._normalizePhotosPersonByMapping(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        person=person,
                        known_persons=known_persons,
                        mapping_lookup=mapping_lookup,
                    )
                    if result.get("updated"):
                        persons_updated += 1
                        faces_reassigned += int(result.get("faces_reassigned") or 0)

            metadata_targets = [target for target in normalized_targets if target in {"ACD", "MICROSOFT", "MWG_REGIONS"}]
            if metadata_targets:
                if not self.exiftool_handler.isAvailable():
                    warning = "cleanup:warning_exiftool_required"
                else:
                    shared_folder = self.core.getSharedFolder(
                        user_key=user_key,
                        cookies=cookies,
                        base_url=base_url,
                        folder_name="photo",
                    )
                    candidate_paths = self.files.listImageFiles(shared_folder) if shared_folder else []
                    total_files = len(candidate_paths)
                    for image_path in candidate_paths:
                        if self._shouldStopCleanup(user_key, normalized_action):
                            self._setCleanupProgressMessage(
                                user_key,
                                normalized_action,
                                "cleanup:progress_stopped",
                                running=False,
                                finished=True,
                                stop_requested=True,
                                targets=normalized_targets,
                                mappings_count=len(mapping_lookup),
                                persons_total=persons_total,
                                persons_scanned=persons_scanned,
                                persons_updated=persons_updated,
                                faces_reassigned=faces_reassigned,
                                files_scanned=files_scanned,
                                files_updated=files_updated,
                                metadata_faces_updated=metadata_faces_updated,
                                total_files=total_files,
                            )
                            return
                        files_scanned += 1
                        self._setCleanupProgressMessage(
                            user_key,
                            normalized_action,
                            "cleanup:progress_checking_file",
                            message_params={"count": files_scanned, "total": total_files},
                            running=True,
                            finished=False,
                            targets=normalized_targets,
                            mappings_count=len(mapping_lookup),
                            persons_total=persons_total,
                            persons_scanned=persons_scanned,
                            persons_updated=persons_updated,
                            faces_reassigned=faces_reassigned,
                            files_scanned=files_scanned,
                            files_updated=files_updated,
                            metadata_faces_updated=metadata_faces_updated,
                            total_files=total_files,
                            current_path=image_path,
                            warning=warning,
                        )
                        result = self.normalizeMetadataFaceNamesFromMappings(
                            image_path=image_path,
                            target_formats=metadata_targets,
                            mapping_lookup=mapping_lookup,
                            should_stop=lambda: self._shouldStopCleanup(user_key, normalized_action),
                        )
                        if result.get("stopped"):
                            self._setCleanupProgressMessage(
                                user_key,
                                normalized_action,
                                "cleanup:progress_stopped",
                                running=False,
                                finished=True,
                                stop_requested=True,
                                targets=normalized_targets,
                                mappings_count=len(mapping_lookup),
                                persons_total=persons_total,
                                persons_scanned=persons_scanned,
                                persons_updated=persons_updated,
                                faces_reassigned=faces_reassigned,
                                files_scanned=files_scanned,
                                files_updated=files_updated,
                                metadata_faces_updated=metadata_faces_updated,
                                total_files=total_files,
                                current_path=image_path,
                                warning=warning,
                            )
                            return
                        if result.get("updated"):
                            files_updated += 1
                            metadata_faces_updated += int(result.get("updated_faces") or 0)

            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_finished",
                running=False,
                finished=True,
                stop_requested=False,
                targets=normalized_targets,
                mappings_count=len(mapping_lookup),
                persons_total=persons_total,
                persons_scanned=persons_scanned,
                persons_updated=persons_updated,
                faces_reassigned=faces_reassigned,
                files_scanned=files_scanned,
                files_updated=files_updated,
                metadata_faces_updated=metadata_faces_updated,
                warning=warning,
            )
        except Exception as exc:
            self._setCleanupProgressMessage(
                user_key,
                normalized_action,
                "cleanup:status_failed",
                running=False,
                finished=True,
                stop_requested=False,
                targets=normalized_targets,
                mappings_count=len(mapping_lookup),
                persons_total=persons_total,
                persons_scanned=persons_scanned,
                persons_updated=persons_updated,
                faces_reassigned=faces_reassigned,
                files_scanned=files_scanned,
                files_updated=files_updated,
                metadata_faces_updated=metadata_faces_updated,
                error=str(exc),
            )
        finally:
            self._cleanup_threads.pop(self._cleanupStateKey(user_key, normalized_action), None)

    def suggestPersonsByName(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        name_prefix: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.photos.suggestFotoTeamPerson(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            name_prefix=name_prefix,
            additional=["thumbnail"],
            limit=limit,
        )

    def saveNameMapping(
        self,
        *,
        source_name: str,
        target_name: str,
    ) -> bool:
        return self.name_mappings.saveNameMapping(
            source_name=source_name,
            target_name=target_name,
        )

    def getRuntimeConfig(self) -> Dict[str, Any]:
        return self.config.readMergedConfig()

    def saveRuntimeConfig(self, config: Dict[str, Any]) -> bool:
        return self.config.writeConfig(config)
