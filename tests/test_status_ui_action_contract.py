from pathlib import Path


def _computed_method(source: str, method_name: str) -> str:
    start = source.find(f"\t\t{method_name}()")
    assert start >= 0, f"Missing computed method: {method_name}"
    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not determine method end: {method_name}"
    return source[start:end]


def _watch_method(source: str, method_name: str) -> str:
    start = source.find(f"\t\t{method_name}(")
    assert start >= 0, f"Missing watch method: {method_name}"
    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not determine watch method end: {method_name}"
    return source[start:end]


def test_face_match_restart_button_is_limited_to_saved_file_search():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    guard = _computed_method(source, "faceMatchCanRestartSavedFileSearch")
    assert "selectedFaceMatchingAction === 'search_photo_face_in_file'" in guard
    assert "!this.faceMatchUseStoredFindings" in guard
    assert "faceMatchSaveOnly" in guard
    assert "hasFaceMatchStoredFindings" in guard
    assert "faceMatchIsPaused" in guard
    assert "!this.faceMatchLoading" in guard
    assert "!this.faceMatchAuthRequired" in guard

    label = _computed_method(source, "faceMatchPrimaryButtonLabel")
    assert "faceMatchLoading" in label
    assert "faceMatchAuthRequired" in label
    assert "faceMatchCanRestartSavedFileSearch" in label
    assert "faceMatchIsPaused" not in label
    assert "face_match:button_restart" in label
    assert "face_match:button_start" in label


def test_face_match_save_only_and_use_stored_findings_are_mutually_exclusive():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    use_stored = _watch_method(source, "faceMatchUseStoredFindings")
    assert "this.faceMatchSaveOnly = false" in use_stored
    assert "resetFaceMatchFindingsReview" in use_stored

    save_only = _watch_method(source, "faceMatchSaveOnly")
    assert "this.faceMatchUseStoredFindings = false" in save_only


def test_face_match_number_from_is_method_not_computed():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    computed_start = source.find("\tcomputed: {")
    watch_start = source.find("\twatch: {")
    methods_start = source.find("\tmethods: {")
    assert computed_start >= 0 and watch_start > computed_start and methods_start > watch_start

    computed = source[computed_start:watch_start]
    methods = source[methods_start:]

    assert "faceMatchNumberFrom(...values)" not in computed
    assert "faceMatchNumberFrom(...values)" in methods
    assert "this.faceMatchNumberFrom(" in computed


def test_checks_restart_button_is_limited_to_saved_scan():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    guard = _computed_method(source, "checksCanRestartSavedScan")
    assert "selectedChecksAction === 'scan'" in guard
    assert "checksSaveOnly" in guard
    assert "hasChecksStoredFindings" in guard
    assert "!this.isChecksReviewActive" in guard
    assert "!this.isChecksReviewStopping" in guard
    assert "!this.checksLoading" in guard

    label = _computed_method(source, "checksPrimaryButtonLabel")
    assert "isChecksReviewActive || this.isChecksReviewStopping" in label
    assert "checksLoading" in label
    assert "checksCanRestartSavedScan" in label
    assert "checks:button_restart" in label
    assert "checks:button_start" in label


def test_checks_restart_button_does_not_depend_on_generic_progress_presence():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    guard = _computed_method(source, "checksCanRestartSavedScan")

    assert "Object.keys(this.checksProgress)" not in guard
    assert "checksCurrentItem" not in guard
    assert "checksEntries.length" not in guard
    assert "selectedChecksAction === 'findings'" not in guard
