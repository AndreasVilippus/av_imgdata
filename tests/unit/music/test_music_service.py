from pathlib import Path

from music.service import MusicRatingsService
from services.config_service import ConfigService


class DummySessionManager:
    def call_api(self, **kwargs):
        if kwargs["api"] == "SYNO.Core.User":
            return {"data": {"users": [{"uid": 1027, "name": "andreas", "description": "Andreas"}]}}
        if kwargs["api"] == "SYNO.Core.Share":
            return {"data": {"shares": [{"name": "music", "vol_path": "/volume1"}]}}
        raise AssertionError(kwargs)


def test_music_capabilities_lists_users_and_shared_music_folders(tmp_path, monkeypatch):
    config = ConfigService(str(tmp_path / "config.json"))
    service = MusicRatingsService(DummySessionManager(), config)
    monkeypatch.setattr(service, "AUDIO_STATION_PACKAGE_PATH", Path(tmp_path / "AudioStation"))

    result = service.capabilities(user_key="user", cookies={}, base_url="https://dsm.test")

    assert result["users"]["users"][0]["name"] == "andreas"
    assert result["users"]["users"][0]["id"] == 1027
    assert result["shared_folders"] == [{"name": "music", "path": "/volume1/music"}]
    assert result["audio_station"]["required_write_scope"] == "multi_user_system_service"
    assert result["audio_station"]["api_setrating_other_users_verified"] is False
    assert result["audio_station"]["api_multi_user_write_status"] == "unsupported_login_uid_bound"
    assert result["audio_station"]["database_schema_evidence"] is True
    assert result["audio_station"]["recommended_write_strategy"] == "database_pending_verification"
    assert result["audio_station"]["write_supported"] is False
    assert result["audio_station"]["write_block_reason"] == "database_runtime_requirements_not_verified"
    assert result["scan"]["live_watch_available"] is False


def test_music_preview_filters_by_change_days_and_normalizes_popm(tmp_path, monkeypatch):
    music_root = tmp_path / "music"
    music_root.mkdir()
    recent = music_root / "recent.mp3"
    old = music_root / "old.mp3"
    recent.write_bytes(b"recent")
    old.write_bytes(b"old")

    service = MusicRatingsService(DummySessionManager(), ConfigService(str(tmp_path / "config.json")))
    service._shared_music_folders = lambda **kwargs: [{"name": "music", "path": str(music_root)}]
    service.exiftool.readAudioRating = lambda path: {
        "success": True,
        "tags": {"Popularimeter": "Rating=196 Count=0"} if path.endswith("recent.mp3") else {},
        "error": "",
    }

    result = service.preview(
        user_key="user",
        cookies={},
        base_url="https://dsm.test",
        changed_since_days=0,
    )

    assert result["files_scanned"] == 2
    assert result["ratings_found"] == 1
    assert result["entries"][0]["rating_stars"] == 4
