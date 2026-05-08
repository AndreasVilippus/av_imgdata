from pathlib import Path


def test_face_match_progress_cards_still_exist():
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    assert "ProgressOverviewCard" in view
    assert "faceMatchShowPersonsProgress" in view
    assert "faceMatchShowFileProgress" in view
    assert "faceMatchStatusHeadline" in view


def test_face_match_progress_visibility_includes_preparing_or_running_state():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "faceMatchHasActiveProgressState()" in mixin
    assert "progress.running" in mixin
    assert "this.faceMatchLoading" in mixin
    assert "Object.keys(progress).length" in mixin


def test_face_match_persons_progress_no_longer_requires_known_total():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    start = mixin.find("faceMatchShowPersonsProgress()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.faceMatchHasActiveProgressState" in method
    assert "this.faceMatchPersonsTotal > 0 && !this.faceMatchIsFileSourceAction" not in method


def test_face_match_file_progress_uses_displayed_file_counters():
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    assert "vm.faceMatchFileProgressTotal" in view
    assert "vm.faceMatchFileProgressCurrent" in view

    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    assert "faceMatchFileProgressTotal()" in mixin
    assert "faceMatchFileProgressCurrent()" in mixin
    assert "total_images" in mixin
    assert "images_read" in mixin
    assert "files_total" in mixin
    assert "files_scanned" in mixin
