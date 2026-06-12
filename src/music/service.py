from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from api.session_manager import SessionManager
from handler.core_handler import CoreHandler
from handler.exiftool_handler import ExifToolHandler
from music.ratings_mapping import normalize_rating
from services.config_service import ConfigService


class MusicRatingsService:
    AUDIO_STATION_PACKAGE_PATH = Path("/var/packages/AudioStation")

    def __init__(self, session_manager: SessionManager, config_service: ConfigService):
        self.session_manager = session_manager
        self.config = config_service
        self.core = CoreHandler(session_manager)
        self.exiftool = ExifToolHandler(config_service)

    def _list_users(self, *, user_key: str, cookies: Dict[str, str], base_url: str) -> Dict[str, Any]:
        try:
            payload = self.session_manager.call_api(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                api="SYNO.Core.User",
                params={
                    "method": "list",
                    "version": "1",
                    "offset": "0",
                    "limit": "-1",
                    "type": "local",
                },
            )
        except Exception as exc:
            return {"available": False, "users": [], "error": str(exc)}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        users = data.get("users") if isinstance(data.get("users"), list) else []
        return {
            "available": True,
            "users": [
                {
                    "id": user.get("uid", user.get("id")),
                    "name": str(user.get("name") or ""),
                    "description": str(user.get("description") or ""),
                    "email": str(user.get("email") or ""),
                }
                for user in users
                if isinstance(user, dict) and str(user.get("name") or "").strip()
            ],
            "error": "",
        }

    def _shared_music_folders(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        configured_names: List[str],
    ) -> List[Dict[str, str]]:
        folders: List[Dict[str, str]] = []
        for name in configured_names:
            path = self.core.getSharedFolder(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                folder_name=name,
            )
            if path:
                folders.append({"name": name, "path": path})
        return folders

    def capabilities(self, *, user_key: str, cookies: Dict[str, str], base_url: str) -> Dict[str, Any]:
        config = self.config.readMergedConfig()
        music = config.get("music") if isinstance(config.get("music"), dict) else {}
        files = music.get("FILES") if isinstance(music.get("FILES"), dict) else {}
        scan = music.get("SCAN") if isinstance(music.get("SCAN"), dict) else {}
        audio_station = music.get("AUDIO_STATION") if isinstance(music.get("AUDIO_STATION"), dict) else {}
        folder_names = files.get("SHARED_FOLDER_NAMES") if isinstance(files.get("SHARED_FOLDER_NAMES"), list) else ["music"]
        package_exists = self.AUDIO_STATION_PACKAGE_PATH.exists()
        return {
            "enabled": bool(music.get("ENABLED", True)),
            "audio_station": {
                "installed": package_exists,
                "package_path": str(self.AUDIO_STATION_PACKAGE_PATH),
                "required_write_scope": "multi_user_system_service",
                "api_setrating_documented": True,
                "api_setrating_other_users_verified": False,
                "api_multi_user_write_status": "unsupported_login_uid_bound",
                "database_schema_evidence": True,
                "database_fallback_allowed": bool(audio_station.get("ALLOW_DATABASE_FALLBACK", False)),
                "recommended_write_strategy": "database_pending_verification",
                "write_supported": False,
                "write_block_reason": "database_runtime_requirements_not_verified",
            },
            "users": self._list_users(user_key=user_key, cookies=cookies, base_url=base_url),
            "shared_folders": self._shared_music_folders(
                user_key=user_key,
                cookies=cookies,
                base_url=base_url,
                configured_names=[str(name) for name in folder_names if str(name).strip()],
            ),
            "scan": {
                "changed_since_days_default": int(scan.get("CHANGED_SINCE_DAYS_DEFAULT") or 0),
                "live_watch_enabled": bool(scan.get("LIVE_WATCH_ENABLED", False)),
                "live_watch_available": False,
                "live_watch_reason": "service_not_implemented",
                "audio_extensions": list(files.get("AUDIO_EXTENSIONS") or []),
            },
        }

    @staticmethod
    def _rating_from_tags(tags: Dict[str, Any]) -> Dict[str, Any]:
        for key, schema in (
            ("Popularimeter", "popm"),
            ("RatingPercent", "rating_percent"),
            ("FMPSRating", "fmps_rating"),
            ("Rating", "rating"),
        ):
            if key in tags:
                rating = normalize_rating(tags.get(key), schema)
                if rating.get("rating_stars") is not None:
                    return rating
        return normalize_rating(None, "unknown")

    def preview(
        self,
        *,
        user_key: str,
        cookies: Dict[str, str],
        base_url: str,
        changed_since_days: int = 0,
        limit: int = 500,
    ) -> Dict[str, Any]:
        capabilities = self.capabilities(user_key=user_key, cookies=cookies, base_url=base_url)
        extensions = {str(value).lower().lstrip(".") for value in capabilities["scan"]["audio_extensions"]}
        normalized_days = max(0, int(changed_since_days or 0))
        normalized_limit = max(1, min(5000, int(limit or 500)))
        cutoff = (
            datetime.now(timezone.utc).timestamp() - (normalized_days * 86400)
            if normalized_days > 0
            else 0
        )
        entries: List[Dict[str, Any]] = []
        files_scanned = 0
        for folder in capabilities["shared_folders"]:
            root = Path(folder["path"])
            if not root.exists() or not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if len(entries) >= normalized_limit:
                    break
                if not path.is_file() or path.suffix.lower().lstrip(".") not in extensions or "@eaDir" in path.parts:
                    continue
                try:
                    if cutoff and path.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                files_scanned += 1
                metadata = self.exiftool.readAudioRating(str(path))
                rating = self._rating_from_tags(metadata.get("tags") if isinstance(metadata.get("tags"), dict) else {})
                if rating.get("rating_stars") is None:
                    continue
                entries.append({"path": str(path), **rating})
        return {
            "dry_run": True,
            "changed_since_days": normalized_days,
            "limit": normalized_limit,
            "files_scanned": files_scanned,
            "ratings_found": len(entries),
            "entries": entries,
        }
