#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from time import monotonic
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

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
from services.bbox_normalizer import from_photos, from_xmp, normalize_xmp_face
from services.config_service import ConfigService
from services.exiftool_service import ExifToolService
from services.face_matcher import FaceMatcher
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

    def install_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.installLatest()

    def remove_exiftool(self) -> Dict[str, Any]:
        return self.exiftool.removeInstalled()

    def _readImageMetadata(self, image_path: str) -> MetadataPayload:
        config = self.config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        use_exiftool_for_sidecars = bool(files_config.get("USE_EXIFTOOL_FOR_SIDECARS", False))
        prefer_exiftool_for_context = bool(files_config.get("PREFER_EXIFTOOL_FOR_CONTEXT", False))

        xmp_path = self.files.findXmpForImage(image_path)
        xmp_content = self.exiftool_handler.loadXmpFile(xmp_path) if xmp_path and use_exiftool_for_sidecars else self.files.loadXmpFromFile(xmp_path)
        xmp_source = "xmp_file" if xmp_content else ""

        if not xmp_content:
            xmp_content = self.exiftool_handler.loadEmbeddedXmp(image_path)
            xmp_source = "embedded_xmp_exiftool" if xmp_content else ""

        if not xmp_content:
            xmp_content = self.files.loadXmpFromImageParsed(image_path)
            xmp_source = "embedded_xmp_parsed" if xmp_content else ""

        if prefer_exiftool_for_context and self.exiftool_handler.isEnabled() and self.exiftool_handler.isAvailable():
            image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
            image_orientation = self.exiftool_handler.readImageOrientation(image_path)
            if not image_dimensions.get("width") or not image_dimensions.get("height"):
                image_dimensions = self.files.readImageDimensions(image_path)
            if image_orientation is None:
                image_orientation = self.files.readJpegExifOrientation(image_path)
        else:
            image_dimensions = self.files.readImageDimensions(image_path)
            image_orientation = self.files.readJpegExifOrientation(image_path)
            if (not image_dimensions.get("width") or not image_dimensions.get("height")) and self.exiftool_handler.isEnabled() and self.exiftool_handler.isAvailable():
                image_dimensions = self.exiftool_handler.readImageDimensions(image_path)
            if image_orientation is None and self.exiftool_handler.isEnabled() and self.exiftool_handler.isAvailable():
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
            face = MetadataFace.from_center_box(
                name=name,
                x=x,
                y=y,
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

        written = self.exiftool_handler.writeXmp(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "deleted": bool(written),
            "warning": "" if written else "checks:warning_face_delete_failed",
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
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

        written = self.exiftool_handler.writeXmp(xmp_path or image_path, ET.tostring(root, encoding="unicode"))
        return {
            "updated": bool(written),
            "warning": "" if written else "checks:warning_face_replace_failed",
            "target_path": xmp_path or image_path,
            "used_sidecar": bool(xmp_path),
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
        transferred_count: int,
        auto: bool,
        save_only: bool,
    ) -> Dict[str, Any]:
        return {
            "skip_face_ids": sorted({int(face_id) for face_id in skip_face_ids if isinstance(face_id, int)}),
            "transferred_count": int(transferred_count),
            "auto": bool(auto),
            "save_only": bool(save_only),
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

    def _buildCheckEntriesForType(
        self,
        *,
        image_path: str,
        review_type: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        normalized_type = str(review_type or "").strip().lower()
        if normalized_type == "dimension_issues":
            entry = self._buildDimensionMismatchReviewEntry(image_path, analysis)
            return [entry] if entry else []
        if normalized_type == "duplicate_faces":
            return self._buildDuplicateFaceReviewEntries(image_path, analysis)
        if normalized_type == "position_deviations":
            return self._buildPositionDeviationReviewEntries(image_path, analysis)
        if normalized_type == "name_conflicts":
            return self._buildNameConflictReviewEntries(image_path, analysis)
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

    def _runFaceMatching(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        limit: int,
        offset: int,
        skip_face_ids: Optional[List[int]],
        auto: bool,
        save_only: bool,
        resume_cursor: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            self.session_manager.keepalive(user_key, base_url=base_url)
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
                auto=auto,
                save_only=save_only,
                resume_cursor=resume_cursor or self._buildFaceMatchResumeCursor(
                    skip_face_ids=list(skip_face_ids or []),
                    transferred_count=0,
                    auto=auto,
                    save_only=save_only,
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
        findings_by_type: Dict[str, List[str]],
    ) -> None:
        for finding_type, paths in findings_by_type.items():
            self._writeFileAnalysisCheckFindings(
                finding_type=finding_type,
                job_id=job_id,
                started_at=started_at,
                shared_folder=shared_folder,
                status=status,
                finished=finished,
                findings=paths,
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
    def _normalizedReviewFace(face: Any) -> Dict[str, Any]:
        if isinstance(face, MetadataFace):
            face_data = face.to_dict()
        elif isinstance(face, dict):
            face_data = dict(face)
        else:
            return {}

        if str(face_data.get("source_format") or "") == "MWG_REGIONS":
            return normalize_xmp_face(face_data)
        return face_data

    @staticmethod
    def _isSameFace(left: Any, right: Any) -> bool:
        if isinstance(left, MetadataFace):
            left = left.to_dict()
        if isinstance(right, MetadataFace):
            right = right.to_dict()
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        keys = ("source_format", "source", "name", "x", "y", "w", "h", "orientation")
        return all(left.get(key) == right.get(key) for key in keys)

    @staticmethod
    def _faceSignature(face: Any) -> Dict[str, Any]:
        if isinstance(face, MetadataFace):
            face = face.to_dict()
        if not isinstance(face, dict):
            return {}
        return {
            "source_format": face.get("source_format"),
            "source": face.get("source"),
            "name": face.get("name"),
            "x": face.get("x"),
            "y": face.get("y"),
            "w": face.get("w"),
            "h": face.get("h"),
            "orientation": face.get("orientation"),
        }

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
        applied_face = normalize_xmp_face(review_face)
        reference_face = self._findBestReferenceFace(review_face, reference_faces) or review_face

        return {
            "review_type": "dimension_issues",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "left_face": applied_face,
            "right_face": self._normalizedReviewFace(reference_face),
            "left_alert_faces": [
                normalize_xmp_face(face) for face in mwg_faces
                if not self._isSameFace(face, review_face)
            ],
            "left_reference_faces": [self._normalizedReviewFace(face) for face in reference_faces],
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
        if review_name:
            same_name = [face for face in candidates if str(face.name or "").strip().casefold() == review_name]
            if same_name:
                return same_name[0]
        return candidates[0] if candidates else None

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
            left_matches = self._countDuplicateSuggestionMatches(left, faces)
            right_matches = self._countDuplicateSuggestionMatches(right, faces)
            if left_matches > right_matches:
                left_state = "suggested"
            elif right_matches > left_matches:
                right_state = "suggested"

        return {
            "review_type": "duplicate_faces",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": self._normalizedReviewFace(left),
            "right_face": self._normalizedReviewFace(right),
            "left_state": left_state,
            "right_state": right_state,
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _countDuplicateSuggestionMatches(self, candidate: MetadataFace, faces: List[MetadataFace]) -> int:
        candidate_name = str(candidate.name or "").strip().casefold()
        candidate_format = str(candidate.source_format or "").strip().upper()
        if not candidate_name or not candidate_format:
            return 0

        normalized_candidate = self._normalizedReviewFace(candidate)
        matches = 0
        for face in faces:
            face_name = str(face.name or "").strip().casefold()
            face_format = str(face.source_format or "").strip().upper()
            if face_name != candidate_name or face_format == candidate_format:
                continue
            normalized_face = self._normalizedReviewFace(face)
            if self.files._boxesOverlapStrongly(normalized_candidate, normalized_face):
                matches += 1
        return matches

    def _buildPositionDeviationReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = payload.faces
        entries: List[Dict[str, Any]] = []
        for index, left in enumerate(faces):
            left_name = str(left.name or "").strip().casefold()
            left_format = str(left.source_format or "").strip().upper()
            if not left_name or not left_format:
                continue
            normalized_left = self._normalizedReviewFace(left)
            for right in faces[index + 1:]:
                right_name = str(right.name or "").strip().casefold()
                right_format = str(right.source_format or "").strip().upper()
                if left_name != right_name or left_format == right_format:
                    continue
                normalized_right = self._normalizedReviewFace(right)
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
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = payload.faces
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        return {
            "review_type": "position_deviations",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": self._normalizedReviewFace(left),
            "right_face": self._normalizedReviewFace(right),
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _buildNameConflictReviewEntries(
        self,
        image_path: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = payload.faces
        entries: List[Dict[str, Any]] = []
        for index, left in enumerate(faces):
            left_name = str(left.name or "").strip()
            if not left_name:
                continue
            normalized_left = self._normalizedReviewFace(left)
            for right in faces[index + 1:]:
                right_name = str(right.name or "").strip()
                if not right_name or left_name.casefold() == right_name.casefold():
                    continue
                normalized_right = self._normalizedReviewFace(right)
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
    ) -> Optional[Dict[str, Any]]:
        payload = self._readImageMetadata(image_path)
        faces = payload.faces
        left = self._findFaceBySignature(faces, (entry or {}).get("left_face_signature") or {})
        right = self._findFaceBySignature(faces, (entry or {}).get("right_face_signature") or {})
        if not left or not right:
            return None
        return {
            "review_type": "name_conflicts",
            "image_path": image_path,
            "image_name": Path(image_path).name,
            "face_name": str(left.name or ""),
            "left_name": str(left.name or ""),
            "right_name": str(right.name or ""),
            "left_format": str(left.source_format or ""),
            "right_format": str(right.source_format or ""),
            "left_face": self._normalizedReviewFace(left),
            "right_face": self._normalizedReviewFace(right),
            "left_alert_faces": [],
            "left_reference_faces": [],
            "right_alert_faces": [],
            "right_reference_faces": [],
        }

    def _getCheckFindingPaths(self, finding_type: str) -> List[str]:
        findings_payload = self.file_analysis.readCheckFindings(finding_type)
        paths = findings_payload.get("paths") if isinstance(findings_payload.get("paths"), list) else []
        normalized_paths = [str(path) for path in paths if isinstance(path, str) and path]
        if normalized_paths:
            return normalized_paths

        entries = findings_payload.get("entries") if isinstance(findings_payload.get("entries"), list) else []
        resolved_paths: List[str] = []
        seen_paths = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            image_path = str(entry.get("image_path") or "").strip()
            if not image_path or image_path in seen_paths:
                continue
            seen_paths.add(image_path)
            resolved_paths.append(image_path)
        return resolved_paths

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
            )

        if source_mode_normalized == "findings":
            findings_payload = self.file_analysis.readCheckFindings(check_type_normalized)
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
            candidate_paths = self._getCheckFindingPaths(check_type_normalized)
        else:
            shared_folder = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name="photo",
            )
            candidate_paths = self.files.listImageFiles(shared_folder) if shared_folder else []

        entries: List[Dict[str, Any]] = []
        seen_paths = set()
        for image_path in candidate_paths:
            if image_path in seen_paths:
                continue
            seen_paths.add(image_path)
            entries.append(
                self._buildCheckEntry(
                    review_type=check_type_normalized,
                    image_path=image_path,
                )
            )

        return {
            "check_type": check_type_normalized,
            "source_mode": source_mode_normalized,
            "save_only": False,
            "count": len(entries),
            "entries": entries,
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
    ) -> None:
        try:
            result = self.searchNextChecksItem(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                check_type=check_type,
                save_only=save_only,
                resume_cursor=resume_cursor,
            )
            self._setChecksProgress(
                user_key,
                **result,
            )
        except (SessionBootstrapRequired, SessionManagerError) as exc:
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
                resume_cursor=resume_cursor or self._buildChecksResumeCursor(
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
    ) -> Dict[str, Any]:
        shared_folder = self.core.getSharedFolder(
            user_key=user_key,
            cookies=cookies,
            base_url=base_url,
            folder_name="photo",
        )
        if not shared_folder:
            return {
                "running": False,
                "finished": True,
                "source_mode": "scan",
                "check_type": check_type,
                "save_only": save_only,
                "message_key": "checks:progress_shared_folder_missing",
                "message": "Shared folder could not be resolved.",
                "message_params": {},
                "result": None,
                "files_scanned": 0,
                "total_files": 0,
                "findings_count": 0,
                "resume_cursor": self._buildChecksResumeCursor(
                    path_index=0,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=0,
                ),
            }

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
            item = self.getChecksReviewItem(entry=entry)
            return {
                "running": False,
                "finished": True,
                "stop_requested": False,
                "source_mode": "scan",
                "check_type": check_type,
                "save_only": save_only,
                "files_scanned": min(path_index, total_files),
                "total_files": total_files,
                "findings_count": max(findings_count, 1),
                "current_path": str(entry.get("image_path") or ""),
                "result": {
                    "entry": entry,
                    "item": item,
                },
                "resume_cursor": self._buildChecksResumeCursor(
                    path_index=path_index,
                    pending_entries=remaining_entries,
                    source_mode="scan",
                    check_type=check_type,
                    save_only=save_only,
                    findings_count=max(findings_count, 1),
                ),
                "message_key": "checks:progress_result_found",
                "message": "Check finding found.",
                "message_params": {"count": max(findings_count, 1)},
            }

        for index in range(max(0, path_index), total_files):
            if self._shouldStopChecks(user_key, check_type):
                return {
                    "running": False,
                    "finished": True,
                    "stop_requested": False,
                    "source_mode": "scan",
                    "check_type": check_type,
                    "save_only": save_only,
                    "files_scanned": index,
                    "total_files": total_files,
                    "findings_count": findings_count,
                    "current_path": "",
                    "result": None,
                    "resume_cursor": self._buildChecksResumeCursor(
                        path_index=index,
                        pending_entries=[],
                        source_mode="scan",
                        check_type=check_type,
                        save_only=save_only,
                        findings_count=findings_count,
                    ),
                    "message_key": "checks:progress_stopped",
                    "message": "Checks scan stopped.",
                    "message_params": {"count": findings_count},
                }
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
            )
            if not entries:
                continue

            findings_count += len(entries)
            if save_only:
                saved_entries.extend(entries)
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
            item = self.getChecksReviewItem(entry=entry)
            return {
                "running": False,
                "finished": True,
                "stop_requested": False,
                "source_mode": "scan",
                "check_type": check_type,
                "save_only": False,
                "files_scanned": scanned_count,
                "total_files": total_files,
                "findings_count": findings_count,
                "current_path": image_path,
                "result": {
                    "entry": entry,
                    "item": item,
                },
                "resume_cursor": self._buildChecksResumeCursor(
                    path_index=index + 1,
                    pending_entries=entries[1:],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=False,
                    findings_count=findings_count,
                ),
                "message_key": "checks:progress_result_found",
                "message": "Check finding found.",
                "message_params": {"count": findings_count},
            }

        if save_only:
            self._writeChecksFindings(
                check_type=check_type,
                status="finished",
                shared_folder=shared_folder,
                source_mode="scan",
                save_only=True,
                entries=saved_entries,
            )
            return {
                "running": False,
                "finished": True,
                "stop_requested": False,
                "source_mode": "scan",
                "check_type": check_type,
                "save_only": True,
                "files_scanned": total_files,
                "total_files": total_files,
                "findings_count": len(saved_entries),
                "current_path": "",
                "result": None,
                "resume_cursor": self._buildChecksResumeCursor(
                    path_index=total_files,
                    pending_entries=[],
                    source_mode="scan",
                    check_type=check_type,
                    save_only=True,
                    findings_count=len(saved_entries),
                ),
                "message_key": "checks:progress_findings_saved" if saved_entries else "checks:progress_findings_empty",
                "message": "Checks findings saved." if saved_entries else "No checks findings were saved.",
                "message_params": {"count": len(saved_entries)},
            }

        return {
            "running": False,
            "finished": True,
            "stop_requested": False,
            "source_mode": "scan",
            "check_type": check_type,
            "save_only": False,
            "files_scanned": total_files,
            "total_files": total_files,
            "findings_count": findings_count,
            "current_path": "",
            "result": None,
            "resume_cursor": self._buildChecksResumeCursor(
                path_index=total_files,
                pending_entries=[],
                source_mode="scan",
                check_type=check_type,
                save_only=False,
                findings_count=findings_count,
            ),
            "message_key": "checks:progress_finished_no_match",
            "message": "No further checks findings found.",
            "message_params": {"count": findings_count},
        }

    def getChecksReviewItem(self, *, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        image_path = str(entry.get("image_path") or "").strip()
        review_type = str(entry.get("review_type") or "").strip().lower()
        if not image_path or not review_type:
            return None
        analysis = self.analyzeImageFaceMetadata(image_path)
        if review_type == "dimension_issues":
            return self._buildDimensionMismatchReviewItem(image_path, analysis, entry)
        if review_type == "duplicate_faces":
            if not self._hasFaceSignature(entry.get("left_face_signature")) or not self._hasFaceSignature(entry.get("right_face_signature")):
                first_entry = next(iter(self._buildDuplicateFaceReviewEntries(image_path, analysis)), None)
                if not first_entry:
                    return None
                entry = first_entry
            return self._buildDuplicateFaceReviewItem(image_path, analysis, entry)
        if review_type == "position_deviations":
            if not self._hasFaceSignature(entry.get("left_face_signature")) or not self._hasFaceSignature(entry.get("right_face_signature")):
                first_entry = next(iter(self._buildPositionDeviationReviewEntries(image_path, analysis)), None)
                if not first_entry:
                    return None
                entry = first_entry
            return self._buildPositionDeviationReviewItem(image_path, analysis, entry)
        if review_type == "name_conflicts":
            if not self._hasFaceSignature(entry.get("left_face_signature")) or not self._hasFaceSignature(entry.get("right_face_signature")):
                first_entry = next(iter(self._buildNameConflictReviewEntries(image_path, analysis)), None)
                if not first_entry:
                    return None
                entry = first_entry
            return self._buildNameConflictReviewItem(image_path, analysis, entry)
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

    def _configuredAnalysisChecks(self) -> Dict[str, bool]:
        config = self.config.readMergedConfig()
        analysis = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks = analysis.get("CHECKS") if isinstance(analysis.get("CHECKS"), dict) else {}
        return {
            "DUPLICATE_FACES": bool(checks.get("DUPLICATE_FACES", True)),
            "POSITION_DEVIATIONS": bool(checks.get("POSITION_DEVIATIONS", True)),
            "DIMENSION_ISSUES": bool(checks.get("DIMENSION_ISSUES", True)),
            "NAME_CONFLICTS": bool(checks.get("NAME_CONFLICTS", True)),
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
        configured_extensions = self.files.configuredImageExtensions()
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

        try:
            for dirpath, _, filenames in os.walk(shared_folder):
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
                            "dimension_issues": dimension_mismatch_paths,
                            "duplicate_faces": duplicate_faces_paths,
                            "position_deviations": position_deviation_paths,
                            "name_conflicts": name_conflict_paths,
                        },
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
                                "dimension_issues": dimension_mismatch_paths,
                                "duplicate_faces": duplicate_faces_paths,
                                "position_deviations": position_deviation_paths,
                                "name_conflicts": name_conflict_paths,
                            },
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
                            "dimension_issues": dimension_mismatch_paths,
                            "duplicate_faces": duplicate_faces_paths,
                            "position_deviations": position_deviation_paths,
                            "name_conflicts": name_conflict_paths,
                        },
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

                metadata_payload = self._readImageMetadata(image_path)
                analysis = self.files.analyzeMetadata(metadata_payload)
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
                        position_deviation_entries.extend(self._buildPositionDeviationReviewEntries(image_path, analysis))
                if analysis_checks["NAME_CONFLICTS"]:
                    files_with_name_conflicts = (files_with_name_conflicts or 0) + int(analysis.get("files_with_name_conflicts") or 0)
                    if analysis.get("files_with_name_conflicts"):
                        name_conflict_paths.append(image_path)
                        name_conflict_entries.extend(self._buildNameConflictReviewEntries(image_path, analysis))
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
                    "dimension_issues": dimension_mismatch_paths,
                    "duplicate_faces": duplicate_faces_paths,
                    "position_deviations": position_deviation_paths,
                    "name_conflicts": name_conflict_paths,
                },
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
        limit: int = 1,
        offset: int = 0,
        skip_face_ids: Optional[List[int]] = None,
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
        combined_skip_face_ids = list(skip_face_ids or [])
        for face_id in cursor_skip_face_ids:
            try:
                normalized_face_id = int(face_id)
            except Exception:
                continue
            if normalized_face_id not in combined_skip_face_ids:
                combined_skip_face_ids.append(normalized_face_id)
        if resume_cursor:
            auto = bool(resume_cursor.get("auto", auto))
            save_only = bool(resume_cursor.get("save_only", save_only))

        self._setFaceMatchingProgressMessage(
            user_key,
            "face_match:status_starting",
            running=True,
            finished=False,
            paused=False,
            auth_required=False,
            stop_requested=False,
            action="search_photo_face_in_file",
            result=None,
            error="",
            auto=auto,
            save_only=save_only,
            persons_read=0,
            images_read=0,
            faces_read=0,
            current_person_id=None,
            current_image_id=None,
            current_face_id=None,
            metadata_faces_read=0,
            transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
            resume_cursor=self._buildFaceMatchResumeCursor(
                skip_face_ids=combined_skip_face_ids,
                transferred_count=int(resume_cursor.get("transferred_count") or 0) if resume_cursor else 0,
                auto=auto,
                save_only=save_only,
            ),
        )
        worker = Thread(
            target=self._runFaceMatching,
            kwargs={
                "user_key": user_key,
                "cookies": dict(cookies),
                "base_url": base_url,
                "limit": limit,
                "offset": offset,
                "skip_face_ids": combined_skip_face_ids,
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

            unknown_persons: List[Dict[str, Any]] = self.photos.listFotoTeamPersonUnknown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                limit=limit,
                offset=offset,
                show_more=True,
                show_hidden=False,
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
                                known_persons_cache = self.photos.listFotoTeamPersonKnown(
                                    user_key=user_key,
                                    cookies=cookies,
                                    base_url=base_url,
                                    additional=["thumbnail"],
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
            known_persons_cache = self.photos.listFotoTeamPersonKnown(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                additional=["thumbnail"],
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
                if auto:
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
