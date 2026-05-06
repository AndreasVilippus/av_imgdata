#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.config_service import ConfigService
from services.exiftool_service import ExifToolService


class ExifToolHandler:
    def __init__(self, config_service: ConfigService):
        self._config = config_service

    def isEnabled(self) -> bool:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return bool(files_config.get("USE_EXIFTOOL", False))

    def configuredPath(self) -> str:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        return ExifToolService._configuredPathFromFilesConfig(files_config)

    def resolveExecutable(self) -> Tuple[str, str]:
        return ExifToolService._resolveExecutable(self.configuredPath())

    def isAvailable(self) -> bool:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return False
        return bool(ExifToolService._readExifToolVersion(executable_path))

    def loadEmbeddedXmp(self, image_path: str) -> Optional[str]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-b", "-XMP", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None

        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def loadXmpFile(self, xmp_path: str) -> Optional[str]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-b", "-XMP", xmp_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None

        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def readImageDimensions(self, image_path: str) -> Dict[str, Any]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return {"width": None, "height": None, "unit": "pixel"}

        try:
            result = subprocess.run(
                [executable_path, "-s3", "-ImageWidth", "-ImageHeight", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return {"width": None, "height": None, "unit": "pixel"}
        if result.returncode != 0:
            return {"width": None, "height": None, "unit": "pixel"}

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return {"width": None, "height": None, "unit": "pixel"}

        try:
            width = int(float(lines[0]))
            height = int(float(lines[1]))
        except (TypeError, ValueError):
            return {"width": None, "height": None, "unit": "pixel"}

        return {"width": width, "height": height, "unit": "pixel"}

    def readImageOrientation(self, image_path: str) -> Optional[int]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return None

        try:
            result = subprocess.run(
                [executable_path, "-s3", "-n", "-Orientation", image_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None

        value = result.stdout.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def readMetadataContext(self, image_path: str, *, include_xmp: bool = True) -> Dict[str, Any]:
        """
        Liest Metadaten-Kontext mit einem einzigen ExifTool-Aufruf.
        Gibt Dimensionen, Orientation und optional XMP zurück.
        """
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": "exiftool_not_available",
            }

        # Baue ExifTool-Argumente
        args = [executable_path, "-j", "-n"]
        if include_xmp:
            args.extend(["-XMP"])
        args.extend(["-ImageWidth", "-ImageHeight", "-Orientation", image_path])

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": f"exiftool_execution_failed: {exc}",
            }

        if result.returncode != 0:
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": f"exiftool_returncode_{result.returncode}",
            }

        # Parse JSON-Ausgabe
        try:
            import json
            data = json.loads(result.stdout.strip())
            if not isinstance(data, list) or len(data) < 1:
                return {
                    "success": False,
                    "xmp_content": None,
                    "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                    "image_orientation": None,
                    "error": "invalid_json_output",
                }
            entry = data[0]
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": f"json_parse_error: {exc}",
            }

        # Extrahiere Werte
        xmp_content = None
        if include_xmp and "XMP" in entry:
            xmp_value = entry["XMP"]
            if isinstance(xmp_value, str) and xmp_value.strip():
                xmp_content = xmp_value.strip()

        width = None
        height = None
        if "ImageWidth" in entry:
            try:
                width = int(float(entry["ImageWidth"]))
            except (TypeError, ValueError):
                pass
        if "ImageHeight" in entry:
            try:
                height = int(float(entry["ImageHeight"]))
            except (TypeError, ValueError):
                pass

        orientation = None
        if "Orientation" in entry:
            try:
                orientation = int(float(entry["Orientation"]))
            except (TypeError, ValueError):
                pass

        return {
            "success": True,
            "xmp_content": xmp_content,
            "image_dimensions": {"width": width, "height": height, "unit": "pixel"},
            "image_orientation": orientation,
            "error": None,
        }

    def readMetadataContextBatch(self, image_paths: list[str], *, include_xmp: bool = True, batch_size: int = 100) -> Dict[str, Dict[str, Any]]:
        """
        Liest Metadaten-Kontext für mehrere Dateien in Batches.
        Gibt ein Dictionary zurück, das Dateipfade auf ihre Kontexte mappt.
        """
        if not image_paths:
            return {}

        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            # Bei nicht verfügbarem ExifTool alle Dateien mit Fehler markieren
            error_context = {
                "success": False,
                "xmp_content": None,
                "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                "image_orientation": None,
                "error": "exiftool_not_available",
            }
            return {path: error_context for path in image_paths}

        result = {}
        
        # Verarbeite in Batches
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            
            # Baue ExifTool-Argumente für Batch
            args = [executable_path, "-j", "-n"]
            if include_xmp:
                args.extend(["-XMP"])
            args.extend(["-ImageWidth", "-ImageHeight", "-Orientation"] + batch_paths)

            try:
                batch_result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except (FileNotFoundError, OSError) as exc:
                # Bei Batch-Fehler alle Dateien im Batch mit Fehler markieren
                error_context = {
                    "success": False,
                    "xmp_content": None,
                    "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                    "image_orientation": None,
                    "error": f"exiftool_execution_failed: {exc}",
                }
                for path in batch_paths:
                    result[path] = error_context
                continue

            if batch_result.returncode != 0:
                # Bei Batch-Fehler alle Dateien im Batch mit Fehler markieren
                error_context = {
                    "success": False,
                    "xmp_content": None,
                    "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                    "image_orientation": None,
                    "error": f"exiftool_returncode_{batch_result.returncode}",
                }
                for path in batch_paths:
                    result[path] = error_context
                continue

            # Parse JSON-Ausgabe für Batch
            try:
                import json
                data = json.loads(batch_result.stdout.strip())
                if not isinstance(data, list):
                    # Bei ungültiger Ausgabe alle Dateien im Batch mit Fehler markieren
                    error_context = {
                        "success": False,
                        "xmp_content": None,
                        "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                        "image_orientation": None,
                        "error": "invalid_json_output",
                    }
                    for path in batch_paths:
                        result[path] = error_context
                    continue

                # Baue Mapping von SourceFile zu Eintrag
                batch_entries = {}
                for entry in data:
                    if isinstance(entry, dict) and "SourceFile" in entry:
                        source_file = entry["SourceFile"]
                        batch_entries[source_file] = entry

                # Verarbeite jede Datei im Batch
                for path in batch_paths:
                    if path in batch_entries:
                        entry = batch_entries[path]
                        
                        # Extrahiere Werte wie in Einzelmethode
                        xmp_content = None
                        if include_xmp and "XMP" in entry:
                            xmp_value = entry["XMP"]
                            if isinstance(xmp_value, str) and xmp_value.strip():
                                xmp_content = xmp_value.strip()

                        width = None
                        height = None
                        if "ImageWidth" in entry:
                            try:
                                width = int(float(entry["ImageWidth"]))
                            except (TypeError, ValueError):
                                pass
                        if "ImageHeight" in entry:
                            try:
                                height = int(float(entry["ImageHeight"]))
                            except (TypeError, ValueError):
                                pass

                        orientation = None
                        if "Orientation" in entry:
                            try:
                                orientation = int(float(entry["Orientation"]))
                            except (TypeError, ValueError):
                                pass

                        result[path] = {
                            "success": True,
                            "xmp_content": xmp_content,
                            "image_dimensions": {"width": width, "height": height, "unit": "pixel"},
                            "image_orientation": orientation,
                            "error": None,
                        }
                    else:
                        # Datei wurde nicht in Ausgabe gefunden
                        result[path] = {
                            "success": False,
                            "xmp_content": None,
                            "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                            "image_orientation": None,
                            "error": "file_not_in_batch_output",
                        }
                        
            except (json.JSONDecodeError, TypeError) as exc:
                # Bei JSON-Fehler alle Dateien im Batch mit Fehler markieren
                error_context = {
                    "success": False,
                    "xmp_content": None,
                    "image_dimensions": {"width": None, "height": None, "unit": "pixel"},
                    "image_orientation": None,
                    "error": f"json_parse_error: {exc}",
                }
                for path in batch_paths:
                    result[path] = error_context

        return result

    def writeXmp(self, target_path: str, xmp_content: str) -> bool:
        return bool(self.writeXmpDetailed(target_path, xmp_content).get("updated"))

    def writeXmpDetailed(self, target_path: str, xmp_content: str) -> Dict[str, Any]:
        executable_path, _ = self.resolveExecutable()
        if not executable_path or not target_path or not xmp_content:
            return {
                "updated": False,
                "error": "invalid_write_request",
                "target_path": target_path,
                "executable_path": executable_path,
            }

        packet_content = str(xmp_content or "").strip()
        if not packet_content:
            return {
                "updated": False,
                "error": "empty_xmp_content",
                "target_path": target_path,
                "executable_path": executable_path,
            }
        if "<?xpacket" not in packet_content:
            packet_content = (
                "<?xpacket begin='\ufeff' id='W5M0MpCehiHzreSzNTczkc9d'?>\n"
                f"{packet_content}\n"
                "<?xpacket end='w'?>\n"
            )

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".xmp", encoding="utf-8", delete=False) as handle:
                handle.write(packet_content)
                temp_path = handle.name
            result = subprocess.run(
                [executable_path, "-m", "-overwrite_original", f"-XMP<={temp_path}", target_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, OSError):
            return {
                "updated": False,
                "error": "exiftool_execution_failed",
                "target_path": target_path,
                "executable_path": executable_path,
            }
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        combined_output = f"{stdout}\n{stderr}".lower()
        details = {
            "target_path": target_path,
            "executable_path": executable_path,
            "returncode": int(result.returncode),
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }

        if result.returncode != 0:
            return {
                "updated": False,
                "error": "exiftool_write_failed",
                **details,
            }
        if "0 image files updated" in combined_output or "0 image files created" in combined_output:
            return {
                "updated": False,
                "error": "no_image_files_updated",
                **details,
            }
        if "1 image files updated" in combined_output or "1 image files created" in combined_output:
            return {
                "updated": True,
                **details,
            }
        if "1 image files unchanged" in combined_output:
            return {
                "updated": True,
                "unchanged": True,
                **details,
            }
        return {
            "updated": True,
            **details,
        }
