from pathlib import Path


def test_cleanup_exposes_recognition_actions_and_standard_options():
    view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")
    options = Path("ui/src/components/cleanup/RecognitionOptions.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    for action in (
        "recognition_build_profiles",
        "recognition_check_reference_outliers",
        "recognition_analyze_unknown_faces",
    ):
        assert f'value="{action}"' in view
        assert f"'{action}'" in mixin
    for mode in ("immediate", "save_only", "findings"):
        assert f'value="{mode}"' in options
    assert "sm-form-select" in options
    assert "sm-form-input sm-form-number-input" in options
    assert "recognitionOptions" in mixin
    assert "isRecognitionCleanupAction ? this.recognitionOptions" in mixin


def test_recognition_actions_do_not_fall_back_to_name_cleanup():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")

    for action in (
        "recognition_build_profiles",
        "recognition_check_reference_outliers",
        "recognition_analyze_unknown_faces",
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
