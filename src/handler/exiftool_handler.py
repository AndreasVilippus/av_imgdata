#!/usr/bin/env python3
import json
import select
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.config_service import ConfigService
from services.exiftool_service import ExifToolService


class _ExifToolResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = int(returncode)
        self.stdout = str(stdout or "")
        self.stderr = str(stderr or "")


class PersistentExifToolProcess:
    """Serialized ExifTool -stay_open reader for metadata read calls."""

    def __init__(self, executable_path: str, *, timeout_seconds: float = 30.0):
        self.executable_path = str(executable_path or "")
        self.timeout_seconds = float(timeout_seconds or 30.0)
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen] = None

    def close(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            if process is None:
                return
            try:
                if process.stdin:
                    process.stdin.write("-stay_open\nFalse\n")
                    process.stdin.flush()
            except Exception:
                pass
            try:
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def _start_locked(self) -> subprocess.Popen:
        if not self.executable_path:
            raise FileNotFoundError("exiftool executable not configured")
        if self._process is not None and self._process.poll() is None:
            return self._process

        self.close()
        self._process = subprocess.Popen(
            [self.executable_path, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        return self._process

    def run(self, args: List[str]) -> _ExifToolResult:
        with self._lock:
            process = self._start_locked()
            if process.stdin is None or process.stdout is None:
                self.close()
                raise OSError("exiftool stay_open pipes are not available")

            command = "\n".join(str(arg) for arg in args)
            if command:
                command += "\n"
            command += "-execute\n"

            try:
                process.stdin.write(command)
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()
                raise

            output_lines: List[str] = []
            deadline = time.monotonic() + max(1.0, self.timeout_seconds)
            stdout_fd = process.stdout.fileno()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.close()
                    raise TimeoutError("exiftool stay_open request timed out")

                ready, _, _ = select.select([stdout_fd], [], [], remaining)
                if not ready:
                    self.close()
                    raise TimeoutError("exiftool stay_open request timed out")

                line = process.stdout.readline()
                if line == "":
                    self.close()
                    raise OSError("exiftool stay_open process ended")
                if line.strip() == "{ready}":
                    break
                output_lines.append(line)

            return _ExifToolResult(0, "".join(output_lines), "")


class ExifToolHandler:
    def __init__(self, config_service: ConfigService):
        self._config = config_service
        self._persistent_lock = threading.RLock()
        self._persistent_reader: Optional[PersistentExifToolProcess] = None
        self._persistent_executable_path = ""

    def close(self) -> None:
        with self._persistent_lock:
            reader = self._persistent_reader
            self._persistent_reader = None
            self._persistent_executable_path = ""
        if reader is not None:
            reader.close()

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

    def _filesConfig(self) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
        return config.get("files") if isinstance(config.get("files"), dict) else {}

    def _persistentEnabled(self) -> bool:
        files_config = self._filesConfig()
        return bool(files_config.get("EXIFTOOL_PERSISTENT_ENABLED", True))

    def _persistentTimeoutSeconds(self) -> float:
        files_config = self._filesConfig()
        try:
            return float(files_config.get("EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS", 30))
        except (TypeError, ValueError):
            return 30.0

    def _persistentReader(self, executable_path: str) -> PersistentExifToolProcess:
        with self._persistent_lock:
            if (
                self._persistent_reader is None
                or self._persistent_executable_path != executable_path
            ):
                if self._persistent_reader is not None:
                    self._persistent_reader.close()
                self._persistent_reader = PersistentExifToolProcess(
                    executable_path,
                    timeout_seconds=self._persistentTimeoutSeconds(),
                )
                self._persistent_executable_path = executable_path
            return self._persistent_reader

    def _runSubprocessExifTool(self, args: List[str]) -> _ExifToolResult:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return _ExifToolResult(127, "", "exiftool_not_available")
        try:
            result = subprocess.run(
                [executable_path, *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=max(1.0, self._persistentTimeoutSeconds()),
            )
        except subprocess.TimeoutExpired:
            return _ExifToolResult(124, "", "exiftool_execution_timeout")
        except FileNotFoundError:
            return _ExifToolResult(127, "", "exiftool_not_found")
        except OSError as exc:
            return _ExifToolResult(126, "", f"exiftool_execution_failed: {exc}")
        return _ExifToolResult(result.returncode, result.stdout, result.stderr)

    def _runPersistentExifTool(self, args: List[str]) -> _ExifToolResult:
        executable_path, _ = self.resolveExecutable()
        if not executable_path:
            return _ExifToolResult(127, "", "exiftool_not_available")
        reader = self._persistentReader(executable_path)
        return reader.run(args)

    def _runExifTool(self, args: List[str], *, allow_persistent: bool = True) -> _ExifToolResult:
        if allow_persistent and self._persistentEnabled():
            try:
                return self._runPersistentExifTool(args)
            except TimeoutError:
                self.close()
                return _ExifToolResult(124, "", "exiftool_execution_timeout")
            except Exception:
                self.close()
                return self._runSubprocessExifTool(args)
        return self._runSubprocessExifTool(args)

    @staticmethod
    def _emptyDimensions() -> Dict[str, Any]:
        return {"width": None, "height": None, "unit": "pixel"}

    def loadEmbeddedXmp(self, image_path: str) -> Optional[str]:
        result = self._runExifTool(["-b", "-XMP", image_path])
        if result.returncode != 0:
            return None
        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def loadXmpFile(self, xmp_path: str) -> Optional[str]:
        result = self._runExifTool(["-b", "-XMP", xmp_path])
        if result.returncode != 0:
            return None
        xmp_content = result.stdout.strip()
        return xmp_content if xmp_content else None

    def readImageDimensions(self, image_path: str) -> Dict[str, Any]:
        result = self._runExifTool(["-s3", "-ImageWidth", "-ImageHeight", image_path])
        if result.returncode != 0:
            return self._emptyDimensions()

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return self._emptyDimensions()

        try:
            width = int(float(lines[0]))
            height = int(float(lines[1]))
        except (TypeError, ValueError):
            return self._emptyDimensions()

        return {"width": width, "height": height, "unit": "pixel"}

    def readImageOrientation(self, image_path: str) -> Optional[int]:
        result = self._runExifTool(["-s3", "-n", "-Orientation", image_path])
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
        args = ["-j", "-n"]
        if include_xmp:
            args.append("-XMP")
        args.extend(["-ImageWidth", "-ImageHeight", "-Orientation", image_path])

        result = self._runExifTool(args)
        if result.returncode != 0:
            error = result.stderr.strip() or f"exiftool_returncode_{result.returncode}"
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": self._emptyDimensions(),
                "image_orientation": None,
                "error": error,
            }

        try:
            data = json.loads(result.stdout.strip())
            if not isinstance(data, list) or len(data) < 1 or not isinstance(data[0], dict):
                return {
                    "success": False,
                    "xmp_content": None,
                    "image_dimensions": self._emptyDimensions(),
                    "image_orientation": None,
                    "error": "invalid_json_output",
                }
            entry = data[0]
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            return {
                "success": False,
                "xmp_content": None,
                "image_dimensions": self._emptyDimensions(),
                "image_orientation": None,
                "error": f"json_parse_error: {exc}",
            }

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
                timeout=max(1.0, self._persistentTimeoutSeconds()),
            )
        except subprocess.TimeoutExpired:
            return {
                "updated": False,
                "error": "exiftool_execution_timeout",
                "target_path": target_path,
                "executable_path": executable_path,
            }
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
