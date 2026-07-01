from pathlib import Path


def test_cleanup_exposes_recognition_actions_and_standard_options():
    view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")
    face_match_view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")
    options = Path("ui/src/components/cleanup/RecognitionOptions.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    face_match_mixin = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    for action in (
        "recognition_build_profiles",
        "recognition_check_reference_outliers",
        "recognition_check_person_assignments",
    ):
        assert f'value="{action}"' in view
        assert f"'{action}'" in mixin
    assert 'value="recognition_analyze_unknown_faces"' not in view
    assert 'value="search_missing_faces_insightface"' in face_match_view
    assert 'value="recognition_analyze_unknown_faces"' in face_match_view
    assert "faceMatchRecognizeMissingInsightFacePersons" in face_match_view
    assert "faceMatchSkipUnknownInsightFacePersons" in face_match_view
    assert "skip_unknown_persons:" in face_match_mixin
    assert "faceMatchRecognitionActionSelected" in face_match_view
    assert "getCleanupStatusProgress()" in face_match_view
    assert "getCleanupStatusCounters()" in face_match_view
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
