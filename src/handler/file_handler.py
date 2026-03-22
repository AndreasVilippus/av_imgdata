#!/usr/bin/env python3
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from services.config_service import ConfigService


NS_ACD = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "acdsee-rs": "http://ns.acdsee.com/regions/",
    "acdsee-stArea": "http://ns.acdsee.com/sType/Area#",
}

NS_PICASA = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "mwg-rs": "http://www.metadataworkinggroup.com/schemas/regions/",
    "stArea": "http://ns.adobe.com/xmp/sType/Area#",
}


class FileHandler:
    """File-specific reads/processing independent from DSM Photos APIs."""

    def __init__(self, config_service: Optional[ConfigService] = None):
        self._config = config_service or ConfigService()

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
    def _parsePicasaFaces(xmp_content: str, *, source: str) -> List[Dict[str, Any]]:
        persons: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(xmp_content)
        except Exception:
            return persons

        for description in root.findall(".//rdf:Description", NS_PICASA):
            if description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Type") != "Face":
                continue

            area = description.find("mwg-rs:Area", NS_PICASA)
            if area is None:
                continue

            try:
                x = float(area.get("{http://ns.adobe.com/xmp/sType/Area#}x"))
                y = float(area.get("{http://ns.adobe.com/xmp/sType/Area#}y"))
                width = float(area.get("{http://ns.adobe.com/xmp/sType/Area#}w"))
                height = float(area.get("{http://ns.adobe.com/xmp/sType/Area#}h"))
            except (TypeError, ValueError):
                continue

            persons.append(
                {
                    "name": description.get("{http://www.metadataworkinggroup.com/schemas/regions/}Name"),
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                    "source": source,
                    "source_format": "PICASA",
                }
            )
        return persons

    def readAllPersonsFromImage(self, image_path: str) -> List[Dict[str, Any]]:
        config = self._config.readConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
        schema_config = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}

        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))
        exiftool_path = str(files_config.get("PATHEXIFTOOL", "exiftool") or "exiftool")
        use_acd = bool(schema_config.get("ACD", True))
        use_picasa = bool(schema_config.get("PICASA", True))

        xmp_path = self._findXmpForImage(image_path)
        xmp_content = self._loadXmpFromFile(xmp_path)
        xmp_source = "xmp_file" if xmp_content else ""
        if not xmp_content and use_exiftool:
            xmp_content = self._loadXmpFromImageExiftool(image_path, exiftool_path)
            xmp_source = "embedded_xmp_exiftool" if xmp_content else ""
        if not xmp_content:
            xmp_content = self._loadXmpFromImageParsed(image_path)
            xmp_source = "embedded_xmp_parsed" if xmp_content else ""
        if not xmp_content:
            return []

        persons: List[Dict[str, Any]] = []
        if use_acd:
            persons.extend(self._parseAcdFaces(xmp_content, source=xmp_source or "metadata"))
        if use_picasa:
            persons.extend(self._parsePicasaFaces(xmp_content, source=xmp_source or "metadata"))
        return persons
