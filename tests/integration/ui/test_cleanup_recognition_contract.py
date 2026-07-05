from pathlib import Path


def test_cleanup_exposes_recognition_actions_and_standard_options():
    view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")
    checks_view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")
    checks_options = Path("ui/src/components/checks/InsightFaceAssignmentOptions.vue").read_text(encoding="utf-8")
    face_match_view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")
    options = Path("ui/src/components/cleanup/RecognitionOptions.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    face_match_mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    for action in (
        "recognition_build_profiles",
        "recognition_check_reference_outliers",
    ):
        assert f'value="{action}"' in view
        assert f"'{action}'" in mixin
    assert 'value="recognition_check_person_assignments"' not in view
    assert 'value="recognition_check_person_assignments"' in checks_view
    assert "import InsightFaceAssignmentOptions from '../components/checks/InsightFaceAssignmentOptions.vue';" in checks_view
    assert "import InsightFaceAssignmentReview from '../components/cleanup/RecognitionFindingsReview.vue';" in checks_view
    assert "InsightFaceAssignmentOptions: () => import" not in checks_view
    assert "InsightFaceAssignmentReview: () => import" not in checks_view
    assert "checksInsightFaceAutoSelectSafe" in checks_options
    assert "checksChangedSinceDays" in checks_options
    assert "updateChecksInsightFaceAutoSelectSafe" in checks_options
    assert "updateChecksChangedSinceDays" in checks_options
    assert "min_faces_per_person" in checks_options
    assert "cleanup:recognition_min_faces" in checks_options
    assert 'value="recognition_analyze_unknown_faces"' not in view
    assert 'value="search_missing_faces_insightface"' in face_match_view
    assert 'value="recognition_analyze_unknown_faces"' in face_match_view
    assert "faceMatchInsightFaceNativeProcessorStatus()" in face_match_mixin
    assert "nativeProcessors.FACE_PROCESSOR" in face_match_mixin
    assert "nativeStatus.hot_path_available === true" in face_match_mixin
    assert "nativeStatus.available === true" in face_match_mixin
    assert "return !!(nativeStatus && nativeStatus.hot_path_available === true && nativeStatus.available === true);" in face_match_mixin
    assert "faceMatchInsightFaceUnavailableMessage" in face_match_view
    assert "faceMatchRecognizeMissingInsightFacePersons" in face_match_view
    assert "faceMatchSkipUnknownInsightFacePersons" in face_match_view
    assert "skip_unknown_persons:" in face_match_mixin
    assert 'v-if="vm.faceMatchSupportsAutoAssignKnown"' in face_match_view
    assert "faceMatchSupportsAutoAssignKnown()" in face_match_mixin
    assert "auto: this.faceMatchSupportsAutoAssignKnown && this.faceMatchAutoAssignKnown" in face_match_mixin
    assert "stoppingMessageKey: 'face_match:output_stopping'" in face_match_mixin
    assert "faceMatchRecognitionActionSelected" in face_match_view
    assert '<RecognitionOptions v-if="vm.faceMatchRecognitionActionSelected"' not in face_match_view
    assert "import RecognitionOptions" not in face_match_view
    assert "vm.faceMatchSupportsSaveOnly" in face_match_view
    assert "vm.faceMatchUseStoredFindings" in face_match_view
    assert "vm.recognitionOptions.include_hidden_persons" in face_match_view
    assert "vm.recognitionOptions.selection_mode === 'safe_only'" in face_match_view
    assert "vm.recognitionOptions.changed_since_days" in face_match_view
    assert "vm.recognitionOptions.min_faces_per_person" in face_match_view
    assert "syncFaceMatchRecognitionOptions()" in face_match_mixin
    assert "operation_mode: operationMode" in face_match_mixin
    assert "getCleanupStatusProgress()" in face_match_view
    assert "getCleanupStatusCounters()" in face_match_view
    assert ':status-text="vm.getCleanupStatusHeadline()"' in checks_view
    assert "stoppingMessageKey: 'checks:progress_stopping'" in Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    assert 'v-if="vm.isInsightFaceAssignmentCheck && Number(vm.getCleanupStatusProgress().total) <= 0 && !vm.isCleanupStatusHeadlineCounterOnly()"' in checks_view
    assert "isCleanupStatusHeadlineCounterOnly()" in mixin
    assert "selectedCleanupAction === 'recognition_build_profiles'" not in view
    assert "cleanup-recognition-counter" not in view
    assert ':status-text="vm.getCleanupProgressOverviewStatusText()"' in view
    assert "shouldShowCleanupStatusCounters()" in view
    assert "cleanup:label_scanned" in Path("src/services/face_recognition_service.py").read_text(encoding="utf-8")
    assert "progress_kind" in Path("src/services/face_recognition_service.py").read_text(encoding="utf-8")
    assert "recognize_persons:" in face_match_mixin
    for mode in ("immediate", "save_only", "findings"):
        assert f'value="{mode}"' in options
    assert "sm-form-select" in options
    assert "sm-form-input sm-form-number-input" in options
    assert "cleanup:recognition_advanced_title" not in options
    assert "recognitionOptions" in mixin
    assert "...this.recognitionOptions" in mixin
    assert "resume_existing: !!options.resumeExisting" in mixin


def test_recognition_actions_do_not_fall_back_to_name_cleanup():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")

    for action in (
        "recognition_build_profiles",
        "recognition_check_reference_outliers",
        "recognition_analyze_unknown_faces",
        "recognition_check_person_assignments",
    ):
        assert f'"{action}"' in source
    assert "if normalized_action in FaceRecognitionService.ACTIONS:" in source
    assert "self.face_recognition.start(" in source


def test_recognition_cleanup_progress_action_is_view_scoped():
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    helper_start = mixin.find("\t\tgetCleanupProgressAction()")
    assert helper_start >= 0
    helper_end = mixin.find("\n\t\t},", helper_start)
    assert helper_end > helper_start
    helper = mixin[helper_start:helper_end]

    assert "activeView === 'checks'" in helper
    assert "this.isInsightFaceAssignmentCheck" in helper
    assert "return 'recognition_check_person_assignments'" in helper
    assert "activeView === 'face_match'" in helper
    assert "this.faceMatchRecognitionActionSelected" in helper
    assert "return 'recognition_analyze_unknown_faces'" in helper
    assert "const runtimeAction = String(this.cleanupRuntimeAction || '').trim();" in helper
    assert "return runtimeAction;" in helper
    assert "return String(this.selectedCleanupAction || 'normalize_names')" in helper

    fetch_start = mixin.find("\t\t\tasync fetchCleanupProgress()")
    if fetch_start < 0:
        fetch_start = mixin.find("\t\t\tasync fetchCleanupProgress(options = {})")
    assert fetch_start >= 0
    fetch_end = mixin.find("\n\t\t\t},", fetch_start)
    assert fetch_end > fetch_start
    fetch = mixin[fetch_start:fetch_end]
    assert "const action = String(options.actionOverride || this.getCleanupProgressAction()).trim();" in fetch
    assert "this.cleanupRuntimeAction || this.selectedCleanupAction || 'normalize_names'" not in fetch


def test_face_match_recognition_status_is_action_scoped():
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "isCleanupProgressForAction(action)" in mixin
    assert "progress.action" in mixin
    assert "progressAction === expectedAction" in mixin
    assert "vm.isCleanupProgressForAction('recognition_analyze_unknown_faces')" in view
    assert "vm.$avt('face_match:status_idle', 'No action running.')" in view


def test_recognition_review_uses_persisted_findings_and_apply_endpoints():
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    review = Path("ui/src/components/cleanup/RecognitionFindingsReview.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    for endpoint in ("recognition_findings", "recognition_review", "recognition_suggestions_apply"):
        assert f'@router.post("/{endpoint}")' in api
        assert f"/api/{endpoint}" in mixin
    assert 'class="panel face-match-split-panel"' in review
    assert "face-match-icon-button-floating" in review
    assert "getRecognitionApplyIconUrl" in review
    assert "getRecognitionExcludeReferenceBaseIconUrl" in review
    assert "getRecognitionExcludeReferenceOverlayIconUrl" in review
    assert "face-match-icon-overlay" in review
    assert "resolveLocalIconUrl('face.png')" in mixin
    assert "resolveLocalIconUrl('del_icon.png')" in mixin
    assert "recognitionCurrentFinding.current_person_name" in review
    assert "action: this.selectedRecognitionAction" in mixin
