#!/usr/bin/env python3
import os
import re
import struct
import mmap
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple
from services.config_service import ConfigService
from services.exiftool_service import ExifToolService
from models.metadata_payload import MetadataPayload
from services.bbox_normalizer import normalize_xmp_face


class SidecarLookupCache:
    """
    Cache für Sidecar-Lookups pro Scanlauf.
    Indexiert Verzeichnisse und ermöglicht Case-insensitive Lookups ohne wiederholte Verzeichnis-Scans.
    """
    
    def __init__(self):
        self._dir_cache: Dict[str, Dict[str, str]] = {}  # dir_path -> {filename_lower: full_path}
        self._lock = Lock()
    
    def find_xmp_for_image(
        self, 
        image_path: str, 
        variants: List[str],
        find_case_insensitive_func
    ) -> Optional[str]:
        """
        Suche XMP-Sidecar für Image mit Cache.
        
        Args:
            image_path: Pfad zum Bild
            variants: Configurierte Lookup-Varianten
            find_case_insensitive_func: Callback für Case-insensitive Path-Suche
        
        Returns:
            Pfad zur XMP-Datei oder None
        """
        directory = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        name_no_ext, _ = os.path.splitext(filename)
        
        if not os.path.isdir(directory):
            return None
        
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
            matched = self._find_with_cache(directory, parts, find_case_insensitive_func)
            if matched and os.path.isfile(matched):
                return matched
        return None
    
    def _find_with_cache(self, directory: str, parts: List[str], find_func) -> Optional[str]:
        """
        Suche Pfad mit Cache für das erste Verzeichnis.
        """
        if not parts:
            return None
        
        # Für mehrstufige Pfade (z.B. xmp/file.xmp) nur das top-level Dir cachen
        top_dir = directory
        remaining_parts = parts
        
        # Wenn mehrere parts (z.B. xmp-Verzeichnis), suche zuerst das xmp-Dir
        if len(parts) > 1:
            xmp_subdir = parts[0]
            with self._lock:
                if top_dir not in self._dir_cache:
                    self._dir_cache[top_dir] = self._index_directory(top_dir)
                dir_cache = self._dir_cache[top_dir]
            
            xmp_dir_lower = xmp_subdir.lower()
            xmp_dir_full = None
            for cached_name, cached_path in dir_cache.items():
                if cached_name == xmp_dir_lower:
                    xmp_dir_full = cached_path
                    break
            
            if not xmp_dir_full or not os.path.isdir(xmp_dir_full):
                return None
            
            # Jetzt suche Datei im xmp-Verzeichnis
            top_dir = xmp_dir_full
            remaining_parts = parts[1:]
        
        # Indexiere das aktuelle Verzeichnis falls noch nicht geschehen
        with self._lock:
            if top_dir not in self._dir_cache:
                self._dir_cache[top_dir] = self._index_directory(top_dir)
            dir_cache = self._dir_cache[top_dir]
        
        # Suche Datei im Cache (case-insensitive)
        if len(remaining_parts) == 1:
            filename_lower = remaining_parts[0].lower()
            return dir_cache.get(filename_lower)
        
        return None
    
    def _index_directory(self, directory: str) -> Dict[str, str]:
        """
        Indexiere ein Verzeichnis: {filename_lower: full_path}.
        """
        index: Dict[str, str] = {}
        try:
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)
                entry_lower = entry.lower()
                index[entry_lower] = full_path
        except (FileNotFoundError, PermissionError, OSError):
            pass
        return index


class FileHandler:
    SIDECAR_LOOKUP_VARIANTS = [
        "same_dir_stem",
        "same_dir_filename",
        "xmp_dir_stem",
        "xmp_dir_filename",
    ]
    RAW_PREVIEW_EXTENSIONS = {
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
        ".nef",
        ".nrw",
        ".orf",
        ".pef",
        ".raf",
        ".rw2",
    }
    MAX_RAW_PREVIEW_FALLBACK_SCAN_BYTES = 64 * 1024 * 1024
    
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
        return bool(files_config.get("IMAGE_EXTENSIONS_NATIVE_ONLY", True))

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

    def configuredAnalysisChecks(self) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
        analysis_config = config.get("analysis") if isinstance(config.get("analysis"), dict) else {}
        checks_config = analysis_config.get("CHECKS") if isinstance(analysis_config.get("CHECKS"), dict) else {}
        defaults = ConfigService.defaultConfig()["analysis"]["CHECKS"]
        single_source = str(checks_config.get("SINGLE_SOURCE_OF_TRUTH", defaults["SINGLE_SOURCE_OF_TRUTH"]) or "").strip().lower()
        metadata_formats = {"acd", "microsoft", "mwg_regions"}
        metadata_locations = {"any", "embedded", "sidecar"}
        if single_source != "photos":
            parts = single_source.split(":")
            if not (len(parts) == 3 and parts[0] == "metadata" and parts[1] in metadata_formats and parts[2] in metadata_locations):
                single_source = ""
        return {
            "DUPLICATE_FACES": bool(checks_config.get("DUPLICATE_FACES", defaults["DUPLICATE_FACES"])),
            "POSITION_DEVIATIONS": bool(checks_config.get("POSITION_DEVIATIONS", defaults["POSITION_DEVIATIONS"])),
            "POSITION_DEVIATIONS_INCLUDE_PHOTOS": bool(checks_config.get("POSITION_DEVIATIONS_INCLUDE_PHOTOS", defaults["POSITION_DEVIATIONS_INCLUDE_PHOTOS"])),
            "DIMENSION_ISSUES": bool(checks_config.get("DIMENSION_ISSUES", defaults["DIMENSION_ISSUES"])),
            "NAME_CONFLICTS": bool(checks_config.get("NAME_CONFLICTS", defaults["NAME_CONFLICTS"])),
            "NAME_CONFLICTS_INCLUDE_PHOTOS": bool(checks_config.get("NAME_CONFLICTS_INCLUDE_PHOTOS", defaults["NAME_CONFLICTS_INCLUDE_PHOTOS"])),
            "NAME_CONFLICT_OVERLAP_THRESHOLD": self._clampFloat(checks_config.get("NAME_CONFLICT_OVERLAP_THRESHOLD", defaults.get("NAME_CONFLICT_OVERLAP_THRESHOLD", 0.75)), 0.0, 1.0, 0.75),
            "NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH": bool(checks_config.get("NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH", defaults.get("NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH", True))),
            "NAME_CONFLICT_MIN_BEST_MATCH_MARGIN": self._clampFloat(checks_config.get("NAME_CONFLICT_MIN_BEST_MATCH_MARGIN", defaults.get("NAME_CONFLICT_MIN_BEST_MATCH_MARGIN", 0.05)), 0.0, 1.0, 0.05),
            "SINGLE_SOURCE_OF_TRUTH": single_source,
        }

    @staticmethod
    def _clampFloat(value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return float(default)
        if numeric < minimum:
            return float(minimum)
        if numeric > maximum:
            return float(maximum)
        return numeric

    def configuredMetadataSchemas(self) -> Dict[str, bool]:
        config = self._config.readMergedConfig()
        metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        schema_config = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}
        return {
            "ACD": bool(schema_config.get("ACD", True)),
            "MICROSOFT": bool(schema_config.get("MICROSOFT", True)),
            "MWG_REGIONS": bool(schema_config.get("MWG_REGIONS", True)),
            "IPTC_EXT_REGIONS": bool(schema_config.get("IPTC_EXT_REGIONS", True)),
        }

    def analyzeMetadata(
        self,
        metadata_payload: MetadataPayload,
        comparison_faces: Optional[List[Dict[str, Any]]] = None,
        include_position_deviation_comparison_faces: bool = False,
        include_name_conflict_comparison_faces: bool = False,
    ) -> Dict[str, Any]:
        metadata = metadata_payload.to_dict()
        analysis_checks = self.configuredAnalysisChecks()
        faces = metadata.get("faces") if isinstance(metadata.get("faces"), list) else []
        normalized_comparison_faces = [
            face for face in list(comparison_faces or [])
            if isinstance(face, dict)
        ]
        image_dimensions = metadata.get("image_dimensions") if isinstance(metadata.get("image_dimensions"), dict) else {}
        image_orientation = metadata.get("image_orientation")
        applied_dimensions = metadata.get("mwg_applied_to_dimensions") if isinstance(metadata.get("mwg_applied_to_dimensions"), dict) else {}
        displayed_image_dimensions = self._orientedImageDimensions(image_dimensions, image_orientation)
        mwg_matches = self._appliedDimensionsMatch(displayed_image_dimensions, applied_dimensions) if analysis_checks["DIMENSION_ISSUES"] else None
        duplicate_faces_count = self._countDuplicateNamedFacesPerFormat(faces) if analysis_checks["DUPLICATE_FACES"] else None
        position_deviation_faces = list(faces)
        if include_position_deviation_comparison_faces:
            position_deviation_faces.extend(normalized_comparison_faces)
        face_position_deviations_count = self._countCrossFormatPositionDeviations(position_deviation_faces) if analysis_checks["POSITION_DEVIATIONS"] else None
        name_conflict_faces = list(faces)
        if include_name_conflict_comparison_faces:
            name_conflict_faces.extend(normalized_comparison_faces)
        name_conflicts_count = self._countOverlappingNameConflicts(
            name_conflict_faces,
            overlap_threshold=analysis_checks["NAME_CONFLICT_OVERLAP_THRESHOLD"],
            require_mutual_best_match=analysis_checks["NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"],
            min_best_match_margin=analysis_checks["NAME_CONFLICT_MIN_BEST_MATCH_MARGIN"],
        ) if analysis_checks["NAME_CONFLICTS"] else None

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
    def _faceOverlapScore(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        left_box = FileHandler._faceBox(left)
        right_box = FileHandler._faceBox(right)
        overlap_width = min(left_box["x2"], right_box["x2"]) - max(left_box["x1"], right_box["x1"])
        overlap_height = min(left_box["y2"], right_box["y2"]) - max(left_box["y1"], right_box["y1"])
        if overlap_width <= 0 or overlap_height <= 0:
            return 0.0

        overlap_area = overlap_width * overlap_height
        left_area = max(0.0, left_box["x2"] - left_box["x1"]) * max(0.0, left_box["y2"] - left_box["y1"])
        right_area = max(0.0, right_box["x2"] - right_box["x1"]) * max(0.0, right_box["y2"] - right_box["y1"])
        smaller_area = min(left_area, right_area)
        if smaller_area <= 0:
            return 0.0
        return overlap_area / smaller_area

    @staticmethod
    def _boxesOverlapStrongly(left: Dict[str, Any], right: Dict[str, Any], *, threshold: float = 0.5) -> bool:
        return FileHandler._faceOverlapScore(left, right) >= threshold

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

    def _countOverlappingNameConflicts(
        self,
        faces: List[Dict[str, Any]],
        *,
        overlap_threshold: float = 0.75,
        require_mutual_best_match: bool = True,
        min_best_match_margin: float = 0.05,
    ) -> int:
        normalized_faces = [
            self._normalizedFaceForComparison(face)
            for face in faces
            if isinstance(face, dict) and self._normalizeFaceName(face.get("name"))
        ]

        best_matches: Dict[int, Tuple[int, float, float]] = {}
        if require_mutual_best_match:
            for index, left in enumerate(normalized_faces):
                scored: List[Tuple[int, float]] = []
                for other_index, right in enumerate(normalized_faces):
                    if index == other_index:
                        continue
                    if left.get("source_format") == right.get("source_format"):
                        continue
                    score = self._faceOverlapScore(left, right)
                    if score > 0:
                        scored.append((other_index, score))
                scored.sort(key=lambda item: item[1], reverse=True)
                if scored:
                    best_score = scored[0][1]
                    second_score = scored[1][1] if len(scored) > 1 else 0.0
                    best_matches[index] = (scored[0][0], best_score, best_score - second_score)

        conflicts = set()
        for index, left in enumerate(normalized_faces):
            for other_index, right in enumerate(normalized_faces[index + 1:], start=index + 1):
                left_name = self._normalizeFaceName(left.get("name"))
                right_name = self._normalizeFaceName(right.get("name"))
                if not left_name or not right_name or left_name == right_name:
                    continue
                score = self._faceOverlapScore(left, right)
                if score < overlap_threshold:
                    continue
                if require_mutual_best_match:
                    left_best = best_matches.get(index)
                    right_best = best_matches.get(other_index)
                    if not left_best or not right_best:
                        continue
                    if left_best[0] != other_index or right_best[0] != index:
                        continue
                    if left_best[2] < min_best_match_margin or right_best[2] < min_best_match_margin:
                        continue
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

    def findXmpForImage(self, image_path: str, lookup_cache: Optional[SidecarLookupCache] = None) -> Optional[str]:
        directory = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        name_no_ext, _ = os.path.splitext(filename)
        if not os.path.isdir(directory):
            return None

        variants = self.configuredSidecarLookupVariants()
        
        # Nutze Cache wenn verfügbar
        if lookup_cache is not None:
            return lookup_cache.find_xmp_for_image(
                image_path,
                variants,
                self._findCaseInsensitivePath
            )
        
        # Fallback auf direkte Suche ohne Cache
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
    def loadXmpFromImageParsed(image_path: str, max_bytes: Optional[int] = None) -> Optional[str]:
        if not os.path.isfile(image_path):
            return None

        try:
            with open(image_path, "rb") as handle:
                if max_bytes is not None:
                    data = handle.read(max_bytes)
                else:
                    data = handle.read()
        except Exception:
            return None

        start_match = re.search(br"<[A-Za-z0-9_:-]*xmpmeta\b", data, re.IGNORECASE)
        end_match = re.search(br"</[A-Za-z0-9_:-]*xmpmeta>", data, re.IGNORECASE)
        if not start_match or not end_match:
            return None

        start = start_match.start()
        end = end_match.end()
        if end <= start:
            return None

        xmp_bytes = data[start:end]
        return xmp_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def extractEmbeddedJpegPreview(cls, image_path: str) -> Optional[bytes]:
        if Path(image_path).suffix.lower() not in cls.RAW_PREVIEW_EXTENSIONS:
            return None
        if not os.path.isfile(image_path):
            return None

        try:
            with open(image_path, "rb") as handle:
                if os.fstat(handle.fileno()).st_size == 0:
                    return None
                with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    return cls._extractTiffEmbeddedJpeg(data)
        except Exception:
            return None

    @classmethod
    def _extractTiffEmbeddedJpeg(cls, data: bytes) -> Optional[bytes]:
        if len(data) < 8:
            return None

        byte_order = data[:2]
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            return cls._findLargestJpegSegment(data, cls.MAX_RAW_PREVIEW_FALLBACK_SCAN_BYTES)

        try:
            magic = struct.unpack(f"{endian}H", data[2:4])[0]
            if magic != 42:
                return cls._findLargestJpegSegment(data, cls.MAX_RAW_PREVIEW_FALLBACK_SCAN_BYTES)
            first_ifd_offset = struct.unpack(f"{endian}I", data[4:8])[0]
        except Exception:
            return None

        queue = [first_ifd_offset]
        visited = set()
        best_preview: Optional[bytes] = None

        while queue:
            ifd_offset = queue.pop(0)
            if ifd_offset in visited:
                continue
            visited.add(ifd_offset)

            parsed = cls._parseTiffIfd(data, endian, ifd_offset)
            if not parsed:
                continue

            tags, next_ifd_offset = parsed
            jpeg_offsets = tags.get(0x0201, [])
            jpeg_lengths = tags.get(0x0202, [])
            for jpeg_offset in jpeg_offsets:
                for jpeg_length in jpeg_lengths:
                    preview = cls._sliceJpegPreview(data, jpeg_offset, jpeg_length)
                    if preview and (best_preview is None or len(preview) > len(best_preview)):
                        best_preview = preview

            for sub_ifd_offset in tags.get(0x014A, []):
                if 0 < sub_ifd_offset < len(data):
                    queue.append(sub_ifd_offset)
            if next_ifd_offset and 0 < next_ifd_offset < len(data):
                queue.append(next_ifd_offset)

        return best_preview or cls._findLargestJpegSegment(data, cls.MAX_RAW_PREVIEW_FALLBACK_SCAN_BYTES)

    @classmethod
    def _parseTiffIfd(cls, data: bytes, endian: str, ifd_offset: int) -> Optional[Tuple[Dict[int, List[int]], int]]:
        if ifd_offset <= 0 or ifd_offset + 2 > len(data):
            return None

        try:
            entry_count = struct.unpack(f"{endian}H", data[ifd_offset:ifd_offset + 2])[0]
        except Exception:
            return None

        entries_start = ifd_offset + 2
        entries_end = entries_start + (entry_count * 12)
        next_offset_pos = entries_end
        if entries_end > len(data) or next_offset_pos + 4 > len(data):
            return None

        tags: Dict[int, List[int]] = {}
        for index in range(entry_count):
            entry_offset = entries_start + (index * 12)
            entry = data[entry_offset:entry_offset + 12]
            try:
                tag, value_type, count = struct.unpack(f"{endian}HHI", entry[:8])
            except Exception:
                continue
            values = cls._readTiffUnsignedValues(data, endian, value_type, count, entry[8:12])
            if values:
                tags[tag] = values

        try:
            next_ifd_offset = struct.unpack(f"{endian}I", data[next_offset_pos:next_offset_pos + 4])[0]
        except Exception:
            next_ifd_offset = 0

        return tags, next_ifd_offset

    @staticmethod
    def _readTiffUnsignedValues(data: bytes, endian: str, value_type: int, count: int, value_field: bytes) -> List[int]:
        type_formats = {
            3: ("H", 2),
            4: ("I", 4),
        }
        if count <= 0 or value_type not in type_formats:
            return []

        fmt, unit_size = type_formats[value_type]
        total_size = unit_size * count
        if total_size <= 4:
            raw = value_field[:total_size]
        else:
            try:
                value_offset = struct.unpack(f"{endian}I", value_field)[0]
            except Exception:
                return []
            if value_offset <= 0 or value_offset + total_size > len(data):
                return []
            raw = data[value_offset:value_offset + total_size]

        values: List[int] = []
        for offset in range(0, len(raw), unit_size):
            chunk = raw[offset:offset + unit_size]
            if len(chunk) != unit_size:
                continue
            try:
                values.append(struct.unpack(f"{endian}{fmt}", chunk)[0])
            except Exception:
                continue
        return values

    @staticmethod
    def _sliceJpegPreview(data: bytes, offset: int, length: int) -> Optional[bytes]:
        if offset <= 0 or length <= 2 or offset + length > len(data):
            return None
        preview = data[offset:offset + length]
        if not preview.startswith(b"\xff\xd8"):
            return None
        return preview

    @staticmethod
    def _findLargestJpegSegment(data: bytes, max_scan_bytes: Optional[int] = None) -> Optional[bytes]:
        best: Optional[bytes] = None
        position = 0
        scan_limit = len(data)
        if max_scan_bytes is not None:
            scan_limit = min(scan_limit, max(0, max_scan_bytes))
        while True:
            start = data.find(b"\xff\xd8", position, scan_limit)
            if start < 0:
                break
            end = data.find(b"\xff\xd9", start + 2, scan_limit)
            if end < 0:
                break
            candidate = data[start:end + 2]
            if best is None or len(candidate) > len(best):
                best = candidate
            position = end + 2
        return best

    @staticmethod
    def readImageDimensions(image_path: str) -> Dict[str, Any]:
        suffix = Path(image_path).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return FileHandler._readJpegDimensions(image_path)
        if suffix == ".png":
            return FileHandler._readPngDimensions(image_path)
        return {"width": None, "height": None, "unit": "pixel"}

    @staticmethod
    def readJpegContext(image_path: str, *, include_xmp: bool = True, max_scan_bytes: int = 64 * 1024 * 1024) -> Dict[str, Any]:
        context = {
            "width": None,
            "height": None,
            "unit": "pixel",
            "orientation": None,
            "xmp_content": None,
            "xmp_source": "",
            "scanned_bytes": 0,
            "complete": False,
        }

        suffix = Path(image_path).suffix.lower()
        if suffix not in {".jpg", ".jpeg"}:
            return context

        try:
            with open(image_path, "rb") as handle:
                header = handle.read(2)
                context["scanned_bytes"] = len(header)
                if len(header) < 2 or header != b"\xff\xd8":
                    return context

                sof_markers = {
                    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
                }

                while True:
                    if max_scan_bytes is not None and context["scanned_bytes"] >= max_scan_bytes:
                        context["complete"] = False
                        return context

                    prefix = handle.read(1)
                    if not prefix:
                        context["complete"] = True
                        return context
                    context["scanned_bytes"] += 1
                    if prefix != b"\xff":
                        context["complete"] = False
                        return context

                    marker = handle.read(1)
                    if not marker:
                        context["complete"] = True
                        return context
                    context["scanned_bytes"] += 1
                    while marker == b"\xff":
                        marker = handle.read(1)
                        if not marker:
                            context["complete"] = True
                            return context
                        context["scanned_bytes"] += 1

                    if marker == b"\x00":
                        continue

                    code = marker[0]
                    if code in {0xD8, 0xD9}:
                        continue
                    if code == 0xDA:
                        context["complete"] = True
                        return context

                    length_bytes = handle.read(2)
                    if len(length_bytes) < 2:
                        context["complete"] = True
                        return context
                    context["scanned_bytes"] += 2

                    segment_length = struct.unpack(">H", length_bytes)[0]
                    if segment_length < 2:
                        context["complete"] = True
                        return context

                    segment_size = segment_length - 2
                    segment_data = handle.read(segment_size)
                    context["scanned_bytes"] += len(segment_data)
                    if len(segment_data) != segment_size:
                        context["complete"] = True
                        return context

                    if code in sof_markers and segment_size >= 7:
                        try:
                            context["height"] = struct.unpack(">H", segment_data[1:3])[0]
                            context["width"] = struct.unpack(">H", segment_data[3:5])[0]
                        except Exception:
                            pass

                    if code == 0xE1 and segment_data.startswith(b"Exif\x00\x00"):
                        tiff_start = 6
                        orientation = FileHandler._readExifOrientationFromTiff(segment_data, tiff_start, len(segment_data))
                        if orientation is not None:
                            context["orientation"] = orientation

                    if include_xmp and code == 0xE1:
                        if segment_data.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
                            try:
                                xmp_payload = segment_data[len(b"http://ns.adobe.com/xap/1.0/\x00"):]
                                context["xmp_content"] = xmp_payload.decode("utf-8", errors="replace")
                                context["xmp_source"] = "embedded_xmp_parsed"
                            except Exception:
                                pass

                    if context["width"] is not None and context["height"] is not None and context["orientation"] is not None and (not include_xmp or context["xmp_content"] is not None):
                        context["complete"] = True
                        return context

        except Exception:
            return context

        return context

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
