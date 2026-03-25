#!/usr/bin/env python3
import os
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from services.config_service import ConfigService
from services.bbox_normalizer import normalize_xmp_face


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


class FileHandler:
    
    def __init__(self, config_service: Optional[ConfigService] = None):
        self._config = config_service or ConfigService()

    @staticmethod
    def _normalize_image_extensions(value: Any, default_extensions: List[str]) -> List[str]:
        if not isinstance(value, list):
            return list(default_extensions)

        normalized: List[str] = []
        for entry in value:
            candidate = str(entry or "").strip().lower().lstrip(".")
            if not candidate or candidate in normalized:
                continue
            normalized.append(candidate)

        return normalized or list(default_extensions)

    def configuredImageExtensions(self) -> List[str]:
        config = self._config.readMergedConfig()
        default_extensions = ConfigService.defaultConfig()["files"]["IMAGE_EXTENSIONS"]
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return self._normalize_image_extensions(files_config.get("IMAGE_EXTENSIONS"), default_extensions)

    def configuredAnalysisChecks(self) -> Dict[str, bool]:
        config = self._config.readMergedConfig()
        analysis_config = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks_config = analysis_config.get("CHECKS") if isinstance(analysis_config.get("CHECKS"), dict) else {}
        defaults = ConfigService.defaultConfig()["analysis"]["CHECKS"]
        return {
            "DUPLICATE_FACES": bool(checks_config.get("DUPLICATE_FACES", defaults["DUPLICATE_FACES"])),
            "POSITION_DEVIATIONS": bool(checks_config.get("POSITION_DEVIATIONS", defaults["POSITION_DEVIATIONS"])),
            "DIMENSION_ISSUES": bool(checks_config.get("DIMENSION_ISSUES", defaults["DIMENSION_ISSUES"])),
            "NAME_CONFLICTS": bool(checks_config.get("NAME_CONFLICTS", defaults["NAME_CONFLICTS"])),
        }

    def _readFaceMetadata(self, image_path: str) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        schema_config = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}

        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))
        exiftool_path = str(files_config.get("PATHEXIFTOOL", "exiftool") or "exiftool")
        use_acd = bool(schema_config.get("ACD", True))
        use_microsoft = bool(schema_config.get("MICROSOFT", True))
        use_mwg_regions = bool(schema_config.get("MWG_REGIONS", True))

        xmp_path = self._findXmpForImage(image_path)
        xmp_content = self._loadXmpFromFile(xmp_path)
        xmp_source = "xmp_file" if xmp_content else ""
        if not xmp_content and use_exiftool:
            xmp_content = self._loadXmpFromImageExiftool(image_path, exiftool_path)
            xmp_source = "embedded_xmp_exiftool" if xmp_content else ""
        if not xmp_content:
            xmp_content = self._loadXmpFromImageParsed(image_path)
            xmp_source = "embedded_xmp_parsed" if xmp_content else ""

        faces: List[Dict[str, Any]] = []
        mwg_context: Dict[str, Any] = {
            "mwg_applied_to_dimensions_present": False,
            "mwg_applied_to_dimensions": {},
        }
        if xmp_content:
            if use_acd:
                faces.extend(self._parseAcdFaces(xmp_content, source=xmp_source or "metadata"))
            if use_microsoft:
                faces.extend(self._parseMicrosoftFaces(xmp_content, source=xmp_source or "metadata"))
            if use_mwg_regions:
                mwg_context = self._extractMwgRegionsContext(xmp_content)
                faces.extend(self._parseMwgRegionsFaces(xmp_content, source=xmp_source or "metadata"))

        image_dimensions = self._readImageDimensions(image_path)
        image_orientation = self._readJpegExifOrientation(image_path)
        xmp_orientation = self._extractXmpTiffOrientation(xmp_content) if xmp_content else None
        if image_orientation is None:
            image_orientation = xmp_orientation
        applied_dimensions = mwg_context.get("mwg_applied_to_dimensions") if isinstance(mwg_context.get("mwg_applied_to_dimensions"), dict) else {}
        applied_width = applied_dimensions.get("width")
        applied_height = applied_dimensions.get("height")
        applied_unit = str(applied_dimensions.get("unit") or "").strip().lower()
        current_width = image_dimensions.get("width")
        current_height = image_dimensions.get("height")
        mwg_matches_current: Optional[bool] = None
        if mwg_context.get("mwg_applied_to_dimensions_present") and applied_unit == "pixel" and applied_width and applied_height and current_width and current_height:
            mwg_matches_current = applied_width == current_width and applied_height == current_height

        mwg_orientation_transform_required = bool(
            mwg_context.get("mwg_applied_to_dimensions_present")
            and image_orientation not in (None, 1)
        )

        if image_orientation not in (None, 1):
            for face in faces:
                if str(face.get("source_format") or "") == "MWG_REGIONS":
                    face["orientation"] = image_orientation

        return {
            "image_path": image_path,
            "xmp_path": xmp_path or "",
            "has_sidecar": bool(xmp_path),
            "xmp_source": xmp_source,
            "has_xmp": bool(xmp_content),
            "faces": faces,
            "image_dimensions": image_dimensions,
            "image_orientation": image_orientation,
            "mwg_applied_to_dimensions_present": bool(mwg_context.get("mwg_applied_to_dimensions_present")),
            "mwg_applied_to_dimensions": applied_dimensions,
            "mwg_applied_to_dimensions_matches_current": mwg_matches_current,
            "mwg_orientation_transform_required": mwg_orientation_transform_required,
        }

    def analyzeImageFaceMetadata(self, image_path: str) -> Dict[str, Any]:
        metadata = self._readFaceMetadata(image_path)
        analysis_checks = self.configuredAnalysisChecks()
        faces = metadata.get("faces") if isinstance(metadata.get("faces"), list) else []
        image_dimensions = metadata.get("image_dimensions") if isinstance(metadata.get("image_dimensions"), dict) else {}
        image_orientation = metadata.get("image_orientation")
        applied_dimensions = metadata.get("mwg_applied_to_dimensions") if isinstance(metadata.get("mwg_applied_to_dimensions"), dict) else {}
        displayed_image_dimensions = self._orientedImageDimensions(image_dimensions, image_orientation)
        mwg_matches = self._appliedDimensionsMatch(displayed_image_dimensions, applied_dimensions) if analysis_checks["DIMENSION_ISSUES"] else None
        duplicate_faces_count = self._countDuplicateNamedFacesPerFormat(faces) if analysis_checks["DUPLICATE_FACES"] else None
        face_position_deviations_count = self._countCrossFormatPositionDeviations(faces) if analysis_checks["POSITION_DEVIATIONS"] else None
        name_conflicts_count = self._countOverlappingNameConflicts(faces) if analysis_checks["NAME_CONFLICTS"] else None

        named_faces = 0
        unnamed_faces = 0
        distinct_person_names = set()
        format_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        focus_usage_counts: Dict[str, int] = {}

        for face in faces:
            name = str(face.get("name") or "").strip()
            if name:
                named_faces += 1
                distinct_person_names.add(name.casefold())
            else:
                unnamed_faces += 1

            source = str(face.get("source") or metadata.get("xmp_source") or "metadata")
            source_counts[source] = source_counts.get(source, 0) + 1

            source_format = str(face.get("source_format") or face.get("format") or "")
            if source_format:
                format_counts[source_format] = format_counts.get(source_format, 0) + 1

            focus_usage = str(face.get("focus_usage") or "").strip()
            if focus_usage:
                focus_usage_counts[focus_usage] = focus_usage_counts.get(focus_usage, 0) + 1

        metadata.update(
            {
                "files_with_face_metadata": 1 if faces else 0,
                "faces_total": len(faces),
                "faces_named": named_faces,
                "faces_unnamed": unnamed_faces,
                "persons_distinct_by_name": len(distinct_person_names),
                "sources": source_counts,
                "formats": format_counts,
                "focus_usages": focus_usage_counts,
                "image_dimensions": image_dimensions,
                "displayed_image_dimensions": displayed_image_dimensions,
                "image_orientation": image_orientation,
                "mwg_applied_to_dimensions": applied_dimensions,
                "mwg_applied_to_dimensions_matches_current": mwg_matches,
                "files_with_duplicate_faces": 1 if analysis_checks["DUPLICATE_FACES"] and duplicate_faces_count > 0 else (0 if analysis_checks["DUPLICATE_FACES"] else None),
                "files_with_face_position_deviations": 1 if analysis_checks["POSITION_DEVIATIONS"] and face_position_deviations_count > 0 else (0 if analysis_checks["POSITION_DEVIATIONS"] else None),
                "files_with_name_conflicts": 1 if analysis_checks["NAME_CONFLICTS"] and name_conflicts_count > 0 else (0 if analysis_checks["NAME_CONFLICTS"] else None),
                "files_with_mwg_applied_to_dimensions": 1 if analysis_checks["DIMENSION_ISSUES"] and metadata.get("mwg_applied_to_dimensions_present") else (0 if analysis_checks["DIMENSION_ISSUES"] else None),
                "files_with_mwg_dimension_mismatch": 1 if analysis_checks["DIMENSION_ISSUES"] and mwg_matches is False else (0 if analysis_checks["DIMENSION_ISSUES"] else None),
                "files_with_dimension_issues": 1 if analysis_checks["DIMENSION_ISSUES"] and mwg_matches is False else (0 if analysis_checks["DIMENSION_ISSUES"] else None),
                "files_with_mwg_orientation_transform_risk": 1 if analysis_checks["DIMENSION_ISSUES"] and metadata.get("mwg_orientation_transform_required") else (0 if analysis_checks["DIMENSION_ISSUES"] else None),
            }
        )
        return metadata

    @staticmethod
    def _normalizeFaceName(value: Any) -> str:
        return str(value or "").strip().casefold()

    @staticmethod
    def _normalizedFaceForComparison(face: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_xmp_face(face) if str(face.get("source_format") or "") == "MWG_REGIONS" else dict(face)
        return {
            "name": str(normalized.get("name") or "").strip(),
            "source_format": str(normalized.get("source_format") or ""),
            "x": float(normalized.get("x") or 0),
            "y": float(normalized.get("y") or 0),
            "w": float(normalized.get("w") or 0),
            "h": float(normalized.get("h") or 0),
        }

    @staticmethod
    def _faceBox(face: Dict[str, Any]) -> Dict[str, float]:
        center_x = float(face.get("x") or 0)
        center_y = float(face.get("y") or 0)
        width = float(face.get("w") or 0)
        height = float(face.get("h") or 0)
        return {
            "x1": center_x - (width / 2),
            "y1": center_y - (height / 2),
            "x2": center_x + (width / 2),
            "y2": center_y + (height / 2),
        }

    @staticmethod
    def _boxesOverlapStrongly(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        left_box = FileHandler._faceBox(left)
        right_box = FileHandler._faceBox(right)
        overlap_width = min(left_box["x2"], right_box["x2"]) - max(left_box["x1"], right_box["x1"])
        overlap_height = min(left_box["y2"], right_box["y2"]) - max(left_box["y1"], right_box["y1"])
        if overlap_width <= 0 or overlap_height <= 0:
            return False

        overlap_area = overlap_width * overlap_height
        left_area = max(0.0, left_box["x2"] - left_box["x1"]) * max(0.0, left_box["y2"] - left_box["y1"])
        right_area = max(0.0, right_box["x2"] - right_box["x1"]) * max(0.0, right_box["y2"] - right_box["y1"])
        smaller_area = min(left_area, right_area)
        if smaller_area <= 0:
            return False
        return (overlap_area / smaller_area) >= 0.5

    def _countDuplicateNamedFacesPerFormat(self, faces: List[Dict[str, Any]]) -> int:
        seen: Dict[tuple, int] = {}
        duplicates = 0
        for face in faces:
            if not isinstance(face, dict):
                continue
            name = self._normalizeFaceName(face.get("name"))
            source_format = str(face.get("source_format") or "").strip().upper()
            if not name or not source_format:
                continue
            key = (source_format, name)
            seen[key] = seen.get(key, 0) + 1
        for count in seen.values():
            if count > 1:
                duplicates += 1
        return duplicates

    def _countCrossFormatPositionDeviations(self, faces: List[Dict[str, Any]]) -> int:
        normalized_faces = [
            self._normalizedFaceForComparison(face)
            for face in faces
            if isinstance(face, dict) and self._normalizeFaceName(face.get("name"))
        ]
        deviations = set()
        for index, left in enumerate(normalized_faces):
            for right in normalized_faces[index + 1:]:
                if self._normalizeFaceName(left.get("name")) != self._normalizeFaceName(right.get("name")):
                    continue
                if left.get("source_format") == right.get("source_format"):
                    continue
                if not self._boxesOverlapStrongly(left, right):
                    deviations.add(self._normalizeFaceName(left.get("name")))
        return len(deviations)

    def _countOverlappingNameConflicts(self, faces: List[Dict[str, Any]]) -> int:
        normalized_faces = [
            self._normalizedFaceForComparison(face)
            for face in faces
            if isinstance(face, dict) and self._normalizeFaceName(face.get("name"))
        ]
        conflicts = set()
        for index, left in enumerate(normalized_faces):
            for right in normalized_faces[index + 1:]:
                left_name = self._normalizeFaceName(left.get("name"))
                right_name = self._normalizeFaceName(right.get("name"))
                if not left_name or not right_name or left_name == right_name:
                    continue
                if self._boxesOverlapStrongly(left, right):
                    conflicts.add(tuple(sorted((left_name, right_name))))
        return len(conflicts)

    def listImageFiles(self, base_path: str) -> List[str]:
        root = Path(base_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []

        extensions = set(self.configuredImageExtensions())
        return sorted([
            str(p) for p in root.rglob("*")
            if p.is_file() and p.suffix.lower().lstrip(".") in extensions
        ])

    @staticmethod
    def list_files(base_path: str, pattern: str = "*") -> List[str]:
        root = Path(base_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []
        return sorted([str(p) for p in root.glob(pattern) if p.is_file()])

    @staticmethod
    def read_text(path: str, max_bytes: int = 1024 * 1024) -> Dict[str, Any]:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "error": "file_not_found", "content": ""}

        with file_path.open("rb") as handle:
            raw = handle.read(max_bytes)
        text = raw.decode("utf-8", errors="replace")
        return {"success": True, "error": "", "content": text}

    @staticmethod
    def _findXmpForImage(image_path: str) -> Optional[str]:
        directory = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        name_no_ext, _ = os.path.splitext(filename)
        candidates = [f"{name_no_ext}.xmp", f"{filename}.xmp"]
        if not os.path.isdir(directory):
            return None

        files_lower = {entry.lower(): entry for entry in os.listdir(directory)}
        for candidate in candidates:
            matched = files_lower.get(candidate.lower())
            if matched:
                return os.path.join(directory, matched)
        return None

    @staticmethod
    def _loadXmpFromFile(xmp_path: Optional[str]) -> Optional[str]:
        if not xmp_path:
            return None

        try:
            with open(xmp_path, "r", encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except Exception:
            return None

    @staticmethod
    def _loadXmpFromImageExiftool(image_path: str, exiftool_path: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [exiftool_path, "-b", "-XMP", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None

        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    @staticmethod
    def _loadXmpFromImageParsed(image_path: str) -> Optional[str]:
        if not os.path.isfile(image_path):
            return None

        try:
            with open(image_path, "rb") as handle:
                data = handle.read()
        except Exception:
            return None

        start = data.find(b"<x:xmpmeta")
        end = data.find(b"</x:xmpmeta>")
        if start == -1 or end == -1:
            return None

        xmp_bytes = data[start:end + len(b"</x:xmpmeta>")]
        return xmp_bytes.decode("utf-8", errors="ignore")

    @staticmethod
    def _readImageDimensions(image_path: str) -> Dict[str, Any]:
        suffix = Path(image_path).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return FileHandler._readJpegDimensions(image_path)
        if suffix == ".png":
            return FileHandler._readPngDimensions(image_path)
        return {"width": None, "height": None, "unit": "pixel"}

    @staticmethod
    def _readPngDimensions(image_path: str) -> Dict[str, Any]:
        try:
            with open(image_path, "rb") as handle:
                header = handle.read(24)
        except Exception:
            return {"width": None, "height": None, "unit": "pixel"}

        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            return {"width": None, "height": None, "unit": "pixel"}

        width = struct.unpack(">I", header[16:20])[0]
        height = struct.unpack(">I", header[20:24])[0]
        return {"width": width, "height": height, "unit": "pixel"}

    @staticmethod
    def _readJpegDimensions(image_path: str) -> Dict[str, Any]:
        try:
            with open(image_path, "rb") as handle:
                data = handle.read()
        except Exception:
            return {"width": None, "height": None, "unit": "pixel"}

        if len(data) < 4 or data[:2] != b"\xff\xd8":
            return {"width": None, "height": None, "unit": "pixel"}

        position = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }

        while position + 9 < len(data):
            if data[position] != 0xFF:
                position += 1
                continue

            marker = data[position + 1]
            if marker in {0xD8, 0xD9}:
                position += 2
                continue

            if position + 4 > len(data):
                break

            segment_length = struct.unpack(">H", data[position + 2:position + 4])[0]
            if segment_length < 2 or position + 2 + segment_length > len(data):
                break

            if marker in sof_markers and segment_length >= 7:
                height = struct.unpack(">H", data[position + 5:position + 7])[0]
                width = struct.unpack(">H", data[position + 7:position + 9])[0]
                return {"width": width, "height": height, "unit": "pixel"}

            position += 2 + segment_length

        return {"width": None, "height": None, "unit": "pixel"}

    @staticmethod
    def _readJpegExifOrientation(image_path: str) -> Optional[int]:
        try:
            with open(image_path, "rb") as handle:
                data = handle.read()
        except Exception:
            return None

        if len(data) < 4 or data[:2] != b"\xff\xd8":
            return None

        position = 2
        while position + 4 <= len(data):
            if data[position] != 0xFF:
                position += 1
                continue

            marker = data[position + 1]
            if marker in {0xD8, 0xD9}:
                position += 2
                continue

            if position + 4 > len(data):
                break

            segment_length = struct.unpack(">H", data[position + 2:position + 4])[0]
            segment_start = position + 4
            segment_end = position + 2 + segment_length
            if segment_length < 2 or segment_end > len(data):
                break

            if marker == 0xE1 and data[segment_start:segment_start + 6] == b"Exif\x00\x00":
                tiff_start = segment_start + 6
                return FileHandler._readExifOrientationFromTiff(data, tiff_start, segment_end)

            position = segment_end

        return None

    @staticmethod
    def _readExifOrientationFromTiff(data: bytes, tiff_start: int, segment_end: int) -> Optional[int]:
        if tiff_start + 8 > segment_end:
            return None

        byte_order = data[tiff_start:tiff_start + 2]
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            return None

        ifd0_offset = struct.unpack(endian + "I", data[tiff_start + 4:tiff_start + 8])[0]
        ifd0_start = tiff_start + ifd0_offset
        if ifd0_start + 2 > segment_end:
            return None

        entry_count = struct.unpack(endian + "H", data[ifd0_start:ifd0_start + 2])[0]
        entry_start = ifd0_start + 2

        for index in range(entry_count):
            offset = entry_start + index * 12
            if offset + 12 > segment_end:
                return None

            tag, value_type = struct.unpack(endian + "HH", data[offset:offset + 4])
            count = struct.unpack(endian + "I", data[offset + 4:offset + 8])[0]
            if tag != 0x0112 or value_type != 3 or count < 1:
                continue

            return struct.unpack(endian + "H", data[offset + 8:offset + 10])[0]

        return None

    @staticmethod
    def _parseAcdFaces(
        xmp_content: str,
        *,
        source: str,
        filter_unknown: bool = True,
        filter_denied: bool = True,
    ) -> List[Dict[str, Any]]:
        persons: List[Dict[str, Any]] = []
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
                {
                    "name": name,
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                    "source": source,
                    "source_format": "ACD",
                }
            )
        return persons

    @staticmethod
    def _parseMwgRegionsFaces(xmp_content: str, *, source: str) -> List[Dict[str, Any]]:
        persons: List[Dict[str, Any]] = []
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
                x = FileHandler._readFloatAttributeOrChild(area, "x", NS_MWG_REGIONS["stArea"])
                y = FileHandler._readFloatAttributeOrChild(area, "y", NS_MWG_REGIONS["stArea"])
                width = FileHandler._readFloatAttributeOrChild(area, "w", NS_MWG_REGIONS["stArea"])
                height = FileHandler._readFloatAttributeOrChild(area, "h", NS_MWG_REGIONS["stArea"])
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
                {
                    "name": name,
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                    "source": source,
                    "source_format": "MWG_REGIONS",
                    "focus_usage": focus_usage,
                }
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

        width = FileHandler._readIntAttributeOrChild(applied, "w", NS_MWG_REGIONS["stDim"])
        height = FileHandler._readIntAttributeOrChild(applied, "h", NS_MWG_REGIONS["stDim"])
        unit = FileHandler._readTextAttributeOrChild(applied, "unit", NS_MWG_REGIONS["stDim"])
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
        value = FileHandler._readTextAttributeOrChild(node, local_name, namespace)
        return float(value)

    @staticmethod
    def _readIntAttributeOrChild(node: ET.Element, local_name: str, namespace: str) -> Optional[int]:
        value = FileHandler._readTextAttributeOrChild(node, local_name, namespace)
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parseMicrosoftFaces(xmp_content: str, *, source: str) -> List[Dict[str, Any]]:
        persons: List[Dict[str, Any]] = []
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
                {
                    "name": name,
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                    "source": source,
                    "source_format": "MICROSOFT",
                }
            )
        return persons

    @staticmethod
    def _orientedImageDimensions(image_dimensions: Dict[str, Any], orientation: Optional[int]) -> Dict[str, Any]:
        if not image_dimensions:
            return {}
        width = image_dimensions.get("width")
        height = image_dimensions.get("height")
        unit = image_dimensions.get("unit") or "pixel"
        if not width or not height:
            return {"width": width, "height": height, "unit": unit}
        if orientation in {5, 6, 7, 8}:
            return {"width": height, "height": width, "unit": unit}
        return {"width": width, "height": height, "unit": unit}

    @staticmethod
    def _appliedDimensionsMatch(image_dimensions: Dict[str, Any], applied_dimensions: Dict[str, Any]) -> Optional[bool]:
        if not image_dimensions or not applied_dimensions:
            return None
        try:
            return (
                int(image_dimensions.get("width") or 0) == int(applied_dimensions.get("width") or 0)
                and int(image_dimensions.get("height") or 0) == int(applied_dimensions.get("height") or 0)
            )
        except (TypeError, ValueError):
            return None

    def readAllPersonsFromImage(self, image_path: str) -> List[Dict[str, Any]]:
        metadata = self._readFaceMetadata(image_path)
        faces = metadata.get("faces")
        return faces if isinstance(faces, list) else []
