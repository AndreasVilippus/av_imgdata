from pathlib import Path


def test_music_ratings_ui_exposes_users_shared_folders_and_scan_options():
    sidebar = Path("ui/src/components/AppSidebarNav.vue").read_text(encoding="utf-8")
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")
    view = Path("ui/src/views/MusicRatingsView.vue").read_text(encoding="utf-8")

    assert "$emit('select', 'music_ratings')" in sidebar
    assert "selectedOption === 'music_ratings'" in app
    assert "musicRatingsUsers" in view
    assert "musicRatingsSharedFolders" in view
    assert "musicRatingsChangedSinceDays" in view
    assert "musicRatingsLiveWatchEnabled" in view
    assert "loadMusicRatingsPreview" in view
    assert "write_blocked" in view
    assert "required_write_scope" in view
    assert "recommended_write_strategy" in view
