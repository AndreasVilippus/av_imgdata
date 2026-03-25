#!/usr/bin/env python3
import os
import platform
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from services.config_service import ConfigService


class ExifToolService:
    """Detect local ExifTool and compare it with the latest official upstream version."""

    HISTORY_URL = "https://exiftool.org/history.html"
    INSTALL_URL = "https://exiftool.org/install.html"
    INDEX_URL = "https://exiftool.org/index.html"

    def __init__(self, config_service: Optional[ConfigService] = None):
        self._config = config_service or ConfigService()

    def getStatus(self) -> Dict[str, Any]:
        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        configured_path = str(files_config.get("PATHEXIFTOOL", "exiftool") or "exiftool").strip() or "exiftool"
        use_exiftool = bool(files_config.get("USE_EXIFTOOL", False))

        local_info = self._detectLocalExifTool(configured_path)
        online_info = self._fetchLatestOfficialInfo()
        perl_info = self._detectPerl()
        update_available = self._isUpdateAvailable(local_info.get("version"), online_info.get("latest_version"))

        return {
            "configured_path": configured_path,
            "use_exiftool": use_exiftool,
            "local": local_info,
            "online": online_info,
            "perl": perl_info,
            "architecture": self._architectureInfo(local_info),
            "update_available": update_available,
        }

    def installLatest(self) -> Dict[str, Any]:
        perl_info = self._detectPerl()
        if not perl_info.get("available"):
            return {
                "success": False,
                "message": "perl_not_available",
                "perl": perl_info,
                "hint": "Please install the Synology Perl package before installing ExifTool.",
            }

        online = self._fetchLatestOfficialInfo()
        download_url = str(online.get("unix_download_url") or "").strip()
        package_name = str(online.get("unix_package_name") or "").strip()
        latest_version = str(online.get("latest_version") or "").strip()
        if not download_url or not package_name or not latest_version:
            return {
                "success": False,
                "message": "latest_exiftool_package_not_found",
                "online": online,
            }

        package_var = Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
        install_root = package_var / "exiftool"
        archive_path = install_root / package_name
        extracted_root = install_root / f"Image-ExifTool-{latest_version}"

        install_root.mkdir(parents=True, exist_ok=True)
        self._downloadFile(download_url, archive_path)

        if extracted_root.exists():
            shutil.rmtree(extracted_root)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=install_root)

        executable_path = extracted_root / "exiftool"
        if not executable_path.exists():
            return {
                "success": False,
                "message": "installed_exiftool_executable_not_found",
                "download_url": download_url,
                "install_root": str(install_root),
            }

        executable_path.chmod(0o755)

        installed_version = self._readExifToolVersion(str(executable_path))
        if not installed_version:
            return {
                "success": False,
                "message": "installed_exiftool_smoke_test_failed",
                "download_url": download_url,
                "installed_path": str(executable_path),
                "perl": perl_info,
            }

        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        files_config["PATHEXIFTOOL"] = str(executable_path)
        files_config["USE_EXIFTOOL"] = True
        config["files"] = files_config
        self._config.writeConfig(config)

        return {
            "success": True,
            "message": "exiftool_installed",
            "download_url": download_url,
            "version": installed_version,
            "archive_path": str(archive_path),
            "installed_path": str(executable_path),
            "perl": perl_info,
            "online": online,
        }

    def removeInstalled(self) -> Dict[str, Any]:
        package_var = Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
        install_root = package_var / "exiftool"
        if install_root.exists():
            shutil.rmtree(install_root)

        config = self._config.readMergedConfig()
        files_config = config.get("files") if isinstance(config.get("files"), dict) else {}
        files_config["PATHEXIFTOOL"] = "exiftool"
        files_config["USE_EXIFTOOL"] = False
        config["files"] = files_config
        self._config.writeConfig(config)

        return {
            "success": True,
            "message": "exiftool_removed",
            "removed_root": str(install_root),
        }

    def _detectLocalExifTool(self, configured_path: str) -> Dict[str, Any]:
        resolved_path, found_via = self._resolveExecutable(configured_path)
        if not resolved_path:
            return {
                "found": False,
                "configured_path": configured_path,
                "resolved_path": "",
                "found_via": "",
                "version": "",
                "kind": "missing",
            }

        version = self._readExifToolVersion(resolved_path)
        kind = self._detectInstallationKind(resolved_path)
        return {
            "found": bool(version),
            "configured_path": configured_path,
            "resolved_path": resolved_path,
            "found_via": found_via,
            "version": version,
            "kind": kind,
        }

    @staticmethod
    def _resolveExecutable(configured_path: str) -> Tuple[str, str]:
        candidate = str(configured_path or "").strip()
        if not candidate:
            candidate = "exiftool"

        explicit = Path(candidate)
        if explicit.is_absolute():
            return (str(explicit), "configured_path") if explicit.exists() else ("", "")

        found = shutil.which(candidate)
        if found:
            return found, "path_lookup"

        common_paths = [
            "/usr/bin/exiftool",
            "/usr/local/bin/exiftool",
            "/opt/bin/exiftool",
            "/var/packages/ExifTool/target/bin/exiftool",
        ]
        for path in common_paths:
            if Path(path).exists():
                return path, "common_path"
        return "", ""

    @staticmethod
    def _readExifToolVersion(executable_path: str) -> str:
        try:
            result = subprocess.run(
                [executable_path, "-ver"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return str(result.stdout or "").strip()

    @staticmethod
    def _detectInstallationKind(executable_path: str) -> str:
        try:
            with open(executable_path, "rb") as handle:
                header = handle.read(256)
        except Exception:
            return "unknown"

        if header.startswith(b"\x7fELF"):
            return "native_binary"
        if header.startswith(b"#!") and b"perl" in header.lower():
            return "perl_script"
        if header.startswith(b"#!"):
            return "script"
        return "unknown"

    def _fetchLatestOfficialInfo(self) -> Dict[str, Any]:
        history_html = self._fetchText(self.HISTORY_URL)
        install_html = self._fetchText(self.INSTALL_URL)

        latest_date = ""
        latest_version = ""
        if history_html:
            match = re.search(r"([A-Z][a-z]{2}\.?\s+\d{1,2},\s+\d{4})\s*-\s*Version\s+([0-9.]+)", history_html)
            if match:
                latest_date = match.group(1).strip()
                latest_version = match.group(2).strip()

        unix_package_name = ""
        if latest_version:
            unix_package_name = f"Image-ExifTool-{latest_version}.tar.gz"
        elif install_html:
            package_match = re.search(r"(Image-ExifTool-[0-9.]+\.tar\.gz)", install_html)
            if package_match:
                unix_package_name = package_match.group(1)
                latest_version = unix_package_name.replace("Image-ExifTool-", "").replace(".tar.gz", "")

        unix_download_url = f"https://exiftool.org/{unix_package_name}" if unix_package_name else ""
        return {
            "checked": bool(history_html or install_html),
            "latest_version": latest_version,
            "latest_release_date": latest_date,
            "history_url": self.HISTORY_URL,
            "install_url": self.INSTALL_URL,
            "index_url": self.INDEX_URL,
            "unix_package_name": unix_package_name,
            "unix_download_url": unix_download_url,
        }

    @staticmethod
    def _detectPerl() -> Dict[str, Any]:
        common_candidates = [
            shutil.which("perl") or "",
            "/usr/bin/perl",
            "/usr/local/bin/perl",
            "/var/packages/Perl/target/usr/bin/perl",
        ]
        seen = set()
        candidates = []
        for candidate in common_candidates:
            normalized = str(candidate or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

        for candidate in candidates:
            if not Path(candidate).exists():
                continue
            version = ExifToolService._readPerlVersion(candidate)
            if version:
                return {
                    "available": True,
                    "path": candidate,
                    "version": version,
                }
        return {
            "available": False,
            "path": "",
            "version": "",
        }

    @staticmethod
    def _readPerlVersion(perl_path: str) -> str:
        try:
            result = subprocess.run(
                [perl_path, "-e", "print $];"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return str(result.stdout or "").strip()

    @staticmethod
    def _fetchText(url: str) -> str:
        request = Request(url, headers={"User-Agent": "AV_ImgData/0.6.0"})
        try:
            with urlopen(request, timeout=8) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _downloadFile(url: str, target_path: Path) -> None:
        request = Request(url, headers={"User-Agent": "AV_ImgData/0.6.0"})
        with urlopen(request, timeout=30) as response:
            target_path.write_bytes(response.read())

    @staticmethod
    def _versionTuple(value: Any) -> Tuple[int, ...]:
        parts = re.findall(r"\d+", str(value or ""))
        return tuple(int(part) for part in parts)

    def _isUpdateAvailable(self, local_version: Any, latest_version: Any) -> bool:
        local_tuple = self._versionTuple(local_version)
        latest_tuple = self._versionTuple(latest_version)
        if not local_tuple or not latest_tuple:
            return False
        return local_tuple < latest_tuple

    @staticmethod
    def _architectureInfo(local_info: Dict[str, Any]) -> Dict[str, Any]:
        machine = platform.machine() or os.uname().machine
        local_kind = str(local_info.get("kind") or "")
        local_architecture_dependent = local_kind == "native_binary"
        return {
            "machine": machine,
            "local_installation_kind": local_kind,
            "local_installation_architecture_dependent": local_architecture_dependent,
            "official_unix_distribution_architecture_dependent": False,
            "notes": [
                "The official Unix/Linux ExifTool distribution is the Perl package and is generally not CPU-architecture specific.",
                "DSM architecture matters mainly when using a native packaged binary or when Perl/runtime dependencies are missing on the target system.",
                "For DSM, the configured executable path and executable type should be checked in addition to the CPU architecture.",
            ],
        }
