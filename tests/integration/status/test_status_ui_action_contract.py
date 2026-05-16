from pathlib import Path


def _computed_method(source: str, method_name: str) -> str:
    start = source.find(f"\t\t{method_name}()")
    assert start >= 0, f"Missing computed method: {method_name}"
    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not determine method end: {method_name}"
    return source[start:end]


def _watch_method(source: str, method_name: str) -> str:
    start = source.find(f"\t\t{method_name}(")
    if start < 0:
        start = source.find(f"\t\tasync {method_name}(")
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
    assert "hasFaceMatchStoredFindings" not in guard
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


def test_face_match_stored_findings_availability_uses_findings_status_not_runtime_progress():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    has_findings = _computed_method(source, "hasFaceMatchStoredFindings")
    assert "faceMatchFindingsStatus" in has_findings
    assert "faceMatchProgress" not in has_findings
    assert "faceMatchDisplayedFindingsCount" not in has_findings

    use_findings_switch = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")
    assert ':disabled="vm.faceMatchLoading || !vm.hasFaceMatchStoredFindings"' in use_findings_switch


def test_face_match_stored_findings_position_accounts_for_removed_entries():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    checked = _computed_method(source, "faceMatchStoredFindingsChecked")
    assert "faceMatchStoredFindingsCompletedCount" in checked
    assert "currentOffset" in checked
    assert "faceMatchFindingIndex" in checked
    assert "Math.min(total" in checked

    completed = _computed_method(source, "faceMatchStoredFindingsCompletedCount")
    assert "faceMatchStoredFindingsTotal" in completed
    assert "faceMatchFindingEntries.length" in completed
    assert "total - remaining" in completed


def test_face_match_stored_findings_message_uses_monotonic_checked_position():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    load_entry = _watch_method(source, "loadFaceMatchFindingAtIndex")
    assert "current: this.faceMatchStoredFindingsChecked" in load_entry
    assert "current: index + 1" not in load_entry


def test_face_match_findings_transfer_keeps_zero_remaining_count():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    advance = _watch_method(source, "advanceFaceMatchFindingsAfterTransfer")
    assert "Number.isFinite(Number(findingsUpdate.remaining_count))" in advance
    assert "Math.max(0, Number(findingsUpdate.remaining_count))" in advance
    assert "Number(findingsUpdate.remaining_count) || remainingEntries.length" not in advance


def test_face_match_live_next_preserves_displayed_progress_as_partial_scan_base():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    start = _watch_method(source, "startFaceMatchingAction")
    assert "const displayedProgress = this.faceMatchDisplayedProgress || {}" in start
    assert "persons_read: Math.max(0, Number(displayedProgress.persons_read) || 0)" in start
    assert "images_read: Math.max(0, Number(displayedProgress.images_read) || 0)" in start
    assert "faces_read: Math.max(0, Number(displayedProgress.faces_read) || 0)" in start
    assert "target_faces_read: Math.max(0, Number(displayedProgress.target_faces_read) || 0)" in start
    assert "metadata_faces_read: Math.max(0, Number(displayedProgress.metadata_faces_read) || 0)" in start


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
    assert "hasChecksStoredFindings" not in guard
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



def test_checks_restart_translation_exists_for_german_ui():
    source = Path("ui/texts/ger/strings").read_text(encoding="utf-8")
    checks_start = source.find("\n[checks]\n")
    assert checks_start >= 0
    next_section = source.find("\n[", checks_start + len("\n[checks]\n"))
    checks = source[checks_start: next_section if next_section >= 0 else len(source)]

    assert 'button_restart="Neustart"' in checks
