from pathlib import Path


def test_face_match_progress_cards_still_exist():
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    assert "ProgressOverviewCard" in view
    assert "faceMatchShowPersonsProgress" in view
    assert "faceMatchShowFileProgress" in view
    assert "faceMatchStatusHeadline" in view


def test_face_match_progress_visibility_includes_preparing_or_running_state():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    start = mixin.find("faceMatchHasActiveProgressState()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "faceMatchHasActiveProgressState()" in mixin
    assert "progress.running === true" in method
    assert "progress.stop_requested === true" in method
    assert "this.faceMatchLoading" in method
    assert "faceMatchStatusPhase()" in mixin
    assert "phase === 'preparing'" in method
    assert "phase === 'running'" in method
    assert "phase === 'stopping'" in method
    assert "Object.keys(progress).length" not in method


def test_face_match_persons_progress_no_longer_requires_known_total():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    start = mixin.find("faceMatchShowPersonsProgress()")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.faceMatchHasActiveProgressState" in method
    assert "this.faceMatchPersonsTotal > 0 && !this.faceMatchIsFileSourceAction" not in method


def test_face_match_finished_progress_does_not_keep_scan_progress_visible():
    mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    active_start = mixin.find("faceMatchHasActiveProgressState()")
    assert active_start >= 0
    active_end = mixin.find("\n\t\t},", active_start)
    assert active_end > active_start
    active = mixin[active_start:active_end]
    assert "progress.message_key" not in active
    assert "progress.message" not in active
    assert "Object.keys(progress).length" not in active
    assert "phase === 'finished'" not in active

    persons_start = mixin.find("faceMatchShowPersonsProgress()")
    assert persons_start >= 0
    persons_end = mixin.find("\n\t\t},", persons_start)
    assert persons_end > persons_start
    persons = mixin[persons_start:persons_end]
    assert "this.faceMatchHasActiveProgressState" in persons
    assert "this.faceMatchPersonsTotal > 0" not in persons

    files_start = mixin.find("faceMatchShowFileProgress()")
    assert files_start >= 0
    files_end = mixin.find("\n\t\t},", files_start)
    assert files_end > files_start
    files = mixin[files_start:files_end]
    assert "this.faceMatchHasActiveProgressState" in files
    assert "this.faceMatchFileProgressTotal > 0" not in files


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
