#!/usr/bin/env python3
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional
from services.config_service import ConfigService
from services.exiftool_service import ExifToolService
from models.metadata_payload import MetadataPayload
from services.bbox_normalizer import normalize_xmp_face


class FileHandler:
    SIDECAR_LOOKUP_VARIANTS = [
        "same_dir_stem",
        "same_dir_filename",
        "xmp_dir_stem",
        "xmp_dir_filename",
    ]
    
    def __init__(self, config_service: Optional[ConfigService] = None):
        self._config = config_service or ConfigService()
        self._exiftool = ExifToolService(self._config)

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

    def configuredExifToolImageExtensions(self) -> List[str]:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return self._normalize_image_extensions(files_config.get("EXIFTOOL_IMAGE_EXTENSIONS"), [])

    def configuredSidecarLookupVariants(self) -> List[str]:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        configured = files_config.get("SIDECAR_LOOKUP_VARIANTS")
        if not isinstance(configured, list):
            return list(self.SIDECAR_LOOKUP_VARIANTS)

        normalized: List[str] = []
        for entry in configured:
            candidate = str(entry or "").strip().lower()
            if candidate not in self.SIDECAR_LOOKUP_VARIANTS or candidate in normalized:
                continue
            normalized.append(candidate)
        return normalized or list(self.SIDECAR_LOOKUP_VARIANTS)

    def imageExtensionsNativeOnly(self) -> bool:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return bool(files_config.get("IMAGE_EXTENSIONS_NATIVE_ONLY", False))

    def useExifToolExtensionsForDiscovery(self) -> bool:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))
        return use_exiftool and not self.imageExtensionsNativeOnly()

    def effectiveImageExtensions(self) -> List[str]:
        native_extensions = self.configuredImageExtensions()
        if not self.useExifToolExtensionsForDiscovery():
            return native_extensions

        configured_extensions = self.configuredExifToolImageExtensions()
        if configured_extensions:
            return configured_extensions

        supported = self._exiftool.getSupportedReadableExtensions()
        supported_extensions = supported.get("extensions") if isinstance(supported.get("extensions"), list) else []
        normalized_supported = self._normalize_image_extensions(supported_extensions, [])
        return normalized_supported or native_extensions

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

    def configuredMetadataSchemas(self) -> Dict[str, bool]:
        config = self._config.readMergedConfig()
        metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        schema_config = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}
        return {
            "ACD": bool(schema_config.get("ACD", True)),
            "MICROSOFT": bool(schema_config.get("MICROSOFT", True)),
            "MWG_REGIONS": bool(schema_config.get("MWG_REGIONS", True)),
        }

    def analyzeMetadata(self, metadata_payload: MetadataPayload) -> Dict[str, Any]:
        metadata = metadata_payload.to_dict()
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
        normalized = normalize_xmp_face(face) if str(face.get("source_format") or "") in {"MWG_REGIONS", "MICROSOFT"} else dict(face)
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

        extensions = set(self.effectiveImageExtensions())
        return sorted([
            str(p) for p in root.rglob("*")
            if p.is_file() and p.suffix.lower().lstrip(".") in extensions
            and "@eaDir" not in p.parts
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
    def _findCaseInsensitivePath(base_path: str, path_parts: List[str]) -> Optional[str]:
        current = Path(base_path)
        if not current.exists() or not current.is_dir():
            return None

        for part in path_parts:
            if not part:
                return None
            try:
                entries = {entry.name.lower(): entry for entry in current.iterdir()}
            except Exception:
                return None
            matched = entries.get(part.lower())
            if matched is None:
                return None
            current = matched

        return str(current) if current.exists() else None

    def findXmpForImage(self, image_path: str) -> Optional[str]:
        directory = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        name_no_ext, _ = os.path.splitext(filename)
        if not os.path.isdir(directory):
            return None

        variants = self.configuredSidecarLookupVariants()
        candidate_parts: List[List[str]] = []
        if "same_dir_stem" in variants:
            candidate_parts.append([f"{name_no_ext}.xmp"])
        if "same_dir_filename" in variants:
            candidate_parts.append([f"{filename}.xmp"])
        if "xmp_dir_stem" in variants:
            candidate_parts.append(["xmp", f"{name_no_ext}.xmp"])
        if "xmp_dir_filename" in variants:
            candidate_parts.append(["xmp", f"{filename}.xmp"])

        for parts in candidate_parts:
            matched = self._findCaseInsensitivePath(directory, parts)
            if matched and os.path.isfile(matched):
                return matched
        return None

    @staticmethod
    def loadXmpFromFile(xmp_path: Optional[str]) -> Optional[str]:
        if not xmp_path:
            return None

        try:
            with open(xmp_path, "r", encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except Exception:
            return None

    @staticmethod
    def loadXmpFromImageParsed(image_path: str) -> Optional[str]:
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
    def readImageDimensions(image_path: str) -> Dict[str, Any]:
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
    def readJpegExifOrientation(image_path: str) -> Optional[int]:
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

    def readAllPersonsFromMetadata(self, metadata_payload: MetadataPayload) -> List[Dict[str, Any]]:
        return [face.to_dict() for face in metadata_payload.faces]
