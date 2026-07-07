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
    assert "hasFaceMatchStoredFindings" in guard
    assert "faceMatchIsPaused" in guard
    assert "!this.faceMatchLoading" in guard
    assert "!this.faceMatchAuthRequired" in guard

    label = _computed_method(source, "faceMatchPrimaryButtonLabel")
    assert "faceMatchHasActiveProgressState" in label
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
    assert ':disabled="vm.faceMatchLoading || (!vm.faceMatchRecognitionActionSelected && !vm.hasFaceMatchStoredFindings)"' in use_findings_switch


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


def test_face_match_stored_findings_can_skip_false_detection_persistently():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    can_skip = _computed_method(source, "faceMatchCanSkipStoredFinding")
    assert "faceMatchReviewingStoredFindings" in can_skip
    assert "faceMatchResultSummary.found" in can_skip

    skip_method = _watch_method(source, "skipCurrentStoredFaceMatchFinding")
    assert "/api/face_skip_match" in skip_method
    assert "metadata_face: metadataFace" in skip_method
    assert "await this.advanceFaceMatchFindingsAfterTransfer(data)" in skip_method

    assert 'v-if="vm.faceMatchCanSkipStoredFinding"' in view
    assert '@click="vm.skipCurrentStoredFaceMatchFinding"' in view
    assert "face_match:button_skip_false_detection" in view


def test_face_match_left_preview_delete_icon_can_ignore_insightface_missing_face():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    can_ignore = _computed_method(source, "faceMatchCanIgnoreInsightFaceDetection")
    assert "search_missing_faces_insightface" in can_ignore
    assert "metadata_face" in can_ignore
    assert "image_path" in can_ignore
    assert "faceMatchResultSummary.found" in can_ignore

    ignore_method = _watch_method(source, "ignoreCurrentInsightFaceDetection")
    assert "skipCurrentStoredFaceMatchFinding" in ignore_method
    assert "this.faceMatchSkippedTargets = this.buildNextSkippedTargets()" in ignore_method
    assert "await this.startFaceMatchingAction({ resetSkippedFaceIds: false })" in ignore_method

    assert 'v-if="vm.faceMatchLeftPreviewDeleteButtonVisible"' in view
    assert ':title="vm.faceMatchLeftPreviewDeleteTooltip"' in view
    assert '@click.prevent="vm.handleFaceMatchLeftPreviewDelete"' in view
    assert "face_match:button_ignore_insightface_detection" in source


def test_face_match_live_next_preserves_displayed_progress_as_partial_scan_base():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    start = _watch_method(source, "startFaceMatchingAction")
    assert "const displayedProgress = this.faceMatchDisplayedProgress || {}" in start
    assert "persons_read: Math.max(0, Number(displayedProgress.persons_read) || 0)" in start
    assert "images_read: Math.max(0, Number(displayedProgress.images_read) || 0)" in start
    assert "faces_read: Math.max(0, Number(displayedProgress.faces_read) || 0)" in start
    assert "target_faces_read: Math.max(0, Number(displayedProgress.target_faces_read) || 0)" in start
    assert "metadata_faces_read: Math.max(0, Number(displayedProgress.metadata_faces_read) || 0)" in start


def test_face_match_file_list_actions_show_preparing_status_immediately():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    start = _watch_method(source, "startFaceMatchingAction")
    assert "const buildsFileList = [" in start
    assert "'search_file_face_in_sources'" in start
    assert "'mark_missing_photos_faces'" in start
    assert "'search_missing_faces_insightface'" in start
    assert "message_key: buildsFileList" in start
    assert "face_match:status_preparing_scan" in start
    assert "Face matching starts. Building file list..." in start
    assert "running: true" in start


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


def test_face_match_result_actions_use_action_lock_and_disable_result_controls():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    interaction = _computed_method(source, "faceMatchInteractionDisabled")
    assert "this.faceMatchHasActiveProgressState || this.faceMatchActionLocked" in interaction

    action = _watch_method(source, "handleFaceMatchAction")
    assert "this.faceMatchInteractionDisabled" in action
    assert "this.faceMatchActionLocked = true" in action
    assert "finally" in action
    assert "this.faceMatchActionLocked = false" in action

    assert ':disabled="vm.faceMatchActionLocked"' in view
    assert ':disabled="vm.faceMatchInteractionDisabled || !vm.hasNextFaceMatch"' in view
    assert ':disabled="vm.faceMatchInteractionDisabled"' in view


def test_face_match_found_result_message_does_not_show_generic_finished_progress():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    message = _computed_method(source, "faceMatchStatusMessage")

    result_guard = message.find("this.faceMatchResultSummary && this.faceMatchResultSummary.found")
    generic_message = message.find("progress && progress.message_key")

    assert result_guard >= 0
    assert generic_message > result_guard
    assert "face_match:status_result_ready" in message
    assert "face_match:result_" in message
    assert "progress_finished" not in message[:generic_message]


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



def test_checks_restart_translation_exists_for_german_ui():
    source = Path("ui/texts/ger/strings").read_text(encoding="utf-8")
    checks_start = source.find("\n[checks]\n")
    assert checks_start >= 0
    next_section = source.find("\n[", checks_start + len("\n[checks]\n"))
    checks = source[checks_start: next_section if next_section >= 0 else len(source)]

    assert 'button_restart="Neustart"' in checks
