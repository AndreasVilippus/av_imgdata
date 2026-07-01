from pathlib import Path


def test_face_frame_options_use_individual_sources_and_labeled_standard_fields():
    source = Path("ui/src/components/cleanup/FaceFrameStandardizationOptions.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    for source_key in ("photos", "acd", "microsoft", "mwg_regions"):
        assert f"key: '{source_key}'" in source
    assert "selection_mode" in source
    assert "operation_mode" in source
    for threshold_key in ("safe_iou", "review_iou", "safe_center_delta", "safe_size_delta"):
        assert threshold_key in source
        assert threshold_key in mixin
    for mode in ("immediate", "save_only", "findings"):
        assert f'value="{mode}"' in source
    assert "sm-form-label" in source
    assert "sm-form-number-input" in source
    assert 'placeholder="det_' not in source


def test_face_frame_options_open_in_start_dialog_and_are_saved_on_start():
    cleanup_view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    styles = Path("ui/src/styles/app.css").read_text(encoding="utf-8")

    assert 'v-if="vm.faceFrameOptionsDialogVisible"' in cleanup_view
    assert 'sm-settings-modal' in cleanup_view
    assert '<FaceFrameStandardizationOptions v-if=' not in cleanup_view
    assert '<FaceFrameStandardizationOptions :vm="vm" :modal="true"' in cleanup_view
    assert "openFaceFrameOptionsDialog()" in mixin
    assert "persistFaceFrameStartOptions()" in mixin
    assert "window.localStorage.setItem" in mixin
    assert "loadStoredFaceFrameStartOptions()" in mixin
    assert "av_imgdata.cleanup.standardize_face_frames.options" in mixin
    assert "resume_existing: !!options.resumeExisting" in mixin
    assert "resumeExisting: true" in mixin
    assert "operation_mode: this.faceFrameOptions.operation_mode" in mixin
    assert "operation_mode: this.recognitionOptions.operation_mode" in mixin
    assert ".sm-settings-modal" in styles


def test_general_labeled_form_field_standard_is_defined():
    styles = Path("ui/src/styles/app.css").read_text(encoding="utf-8")

    for class_name in (".sm-form-grid", ".sm-form-field", ".sm-form-label", ".sm-form-input", ".sm-form-select"):
        assert class_name in styles


def test_face_frame_manual_review_shows_current_and_insightface_previews_without_result_table():
    source = Path("ui/src/components/cleanup/FaceFrameFindingsTable.vue").read_text(encoding="utf-8")
    cleanup_view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")

    assert "faceFrameManualReviewEnabled" in source
    assert 'class="panel face-match-split-panel"' in source
    assert '<div class="cleanup-view">' in cleanup_view
    assert cleanup_view.index("</section>") < cleanup_view.index("<FaceFrameFindingsTable")
    assert "face_frames_now" in source
    assert "face_frames_insightface" in source
    assert "getFaceMatchBoxStyle" in source
    assert "getFaceFrameApplyIconUrl" in source
    assert "face-match-icon-button-floating" in source
    assert "button_apply_all" in source
    assert "applyAllFaceFrameFindings()" in source
    assert "nextFaceFrameFinding" not in source
    assert "<table" not in source
    assert '!vm.cleanupLoading' in source

    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    assert "resolveLocalIconUrl('face_to_left.png')" in mixin
    assert "async applyAllFaceFrameFindings()" in mixin
    assert "this.faceFrameReviewFindings" in mixin
    assert "await this.applyFaceFrameItems(selectedItemIds)" in mixin


def test_face_frame_apply_uses_persisted_selection_endpoint():
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "/api/cleanup_face_frames_select" in mixin
    assert "/api/cleanup_face_frames_apply" in mixin
    assert "async applyFaceFrameItems(selectedItemIds)" in mixin
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    assert '@router.post("/cleanup_face_frames_select")' in api
    assert '@router.post("/cleanup_face_frames_apply")' in api


def test_face_frame_findings_sync_replaces_scan_progress_with_current_list_entry():
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "syncFaceFrameFindingsProgress()" in mixin
    assert "current_path: currentFinding" in mixin
    assert "kind: 'entries'" in mixin
    assert "processedCount" in mixin


def test_face_frame_status_uses_progress_card_for_total_and_counters_for_details():
    view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    service = Path("src/services/face_frame_standardization_service.py").read_text(encoding="utf-8")

    assert 'v-if="vm.shouldShowCleanupStatusCounters()"' in view
    assert "shouldShowCleanupStatusCounters()" in mixin
    assert "this.selectedRecognitionAction !== 'recognition_build_profiles'" in mixin
    assert "return ''" in mixin
    for counter in ("checked", "findings", "automatic", "written", "errors"):
        assert f'_buildStatusCounter("{counter}"' in service
    assert "cleanup:label_checked_count" in service
    assert "cleanup:label_automatic" in service
    assert "cleanup:label_corrected" in service


def test_face_frame_new_scan_clears_local_review_findings_without_using_saved_list():
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "this.faceFrameOptions.operation_mode !== 'findings' && !cleanupOptions.resume_existing" in mixin
    assert "this.faceFrameFindings = []" in mixin
    assert "this.faceFrameCurrentIndex = 0" in mixin
