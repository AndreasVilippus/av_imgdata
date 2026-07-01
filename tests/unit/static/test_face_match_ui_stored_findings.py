from pathlib import Path


def test_stored_face_match_transfer_can_remove_metadata_entry_without_face_id():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async advanceFaceMatchFindingsAfterTransfer(data)" in source
    assert "const currentIndex = Math.max(0, Number(this.faceMatchFindingIndex) || 0)" in source
    assert "const removedByBackend = !!(findingsUpdate && findingsUpdate.removed)" in source
    assert "const removedCount = Math.max(0, Number(findingsUpdate && findingsUpdate.removed_count) || 0)" in source
    assert "if (!faceId && removedByBackend && removedCount > 0 && index === currentIndex)" in source
    assert "index !== currentIndex" in source
    assert "const nextIndex = Math.min(currentIndex, remainingEntries.length - 1)" in source


def test_stored_face_match_transfer_still_removes_existing_photos_face_by_face_id():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "if (faceId)" in source
    assert "const entryFaceId = Number(entry && entry.face && entry.face.face_id)" in source
    assert "Number.isFinite(entryFaceId) && entryFaceId === faceId" in source


def test_stored_face_match_status_fetch_failure_keeps_existing_status():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    method_start = source.index("async fetchFaceMatchFindingsStatus()")
    method_end = source.index("async reconcileStoredFaceMatchFindingsAfterMutationError", method_start)
    method_source = source[method_start:method_end]

    assert "this.faceMatchFindingsStatus = {};" not in method_source
    assert "this.faceMatchFindingsStatus = this.faceMatchFindingsStatus && typeof this.faceMatchFindingsStatus === 'object'" in method_source


def test_stored_face_match_mutation_error_reconciles_from_backend():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async reconcileStoredFaceMatchFindingsAfterMutationError(err)" in source
    assert "getFaceMatchErrorMessage(err, fallback = 'Unknown error')" in source
    assert "const message = this.getFaceMatchErrorMessage(err);" in source
    assert "await this.loadStoredFaceMatchFindings()" in source
    assert source.count("await this.reconcileStoredFaceMatchFindingsAfterMutationError(err)") >= 3


def test_face_match_mutations_show_pending_output_before_backend_write():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "setFaceMatchMutationPending(messageKey, fallback, imagePath, personName = '')" in source
    assert "face_match:output_assign_metadata_face_starting" in source
    assert "face_match:output_assign_photos_face_starting" in source
    assert "face_match:output_create_metadata_face_starting" in source
    assert "face_match:output_apply_metadata_face_starting" in source


def test_file_source_preview_labels_distinguish_name_source_and_file_target():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    assert "face_match:title_name_source" in source
    assert "face_match:title_file_face_target" in source
    assert "faceMatchImageContextTitle()" in source
    assert "faceMatchImageContextPath()" in source
    assert "vm.faceMatchImageContextTitle" in view
    assert "vm.faceMatchImageContextPath" in view


def test_face_match_image_preview_uses_backend_fallback_after_thumbnail_error():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/FaceMatchView.vue").read_text(encoding="utf-8")

    assert "getCurrentFaceMatchImageFallbackUrl()" in source
    assert "this.getBackendImagePreviewUrl(imagePath)" in source
    assert "!this.isBrowserImageCompatiblePath(imagePath)" in source
    assert "handleFaceMatchImagePreviewError(event)" in source
    assert "image.dataset.avFallbackApplied = 'true'" in source
    assert "image.src = fallbackUrl" in source
    assert view.count('@error="vm.handleFaceMatchImagePreviewError"') == 4


def test_file_image_preview_url_building_is_centralized():
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")
    face_match = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    checks = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    cleanup = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "getBackendImagePreviewUrl(path)" in app
    assert "isBrowserImageCompatiblePath(path)" in app
    assert face_match.count("/webman/3rdparty/AV_ImgData/index.cgi/api/file_image") == 0
    assert checks.count("/webman/3rdparty/AV_ImgData/index.cgi/api/file_image") == 0
    assert cleanup.count("/webman/3rdparty/AV_ImgData/index.cgi/api/file_image") == 0


def test_dsm_api_type_error_gets_explicit_network_failure_message():
    source = Path("ui/src/services/dsm-api-client.js").read_text(encoding="utf-8")
    method_start = source.index("async function callDsmApi(apiPath, body = {}, options = {})")
    method_end = source.index("return {", method_start)
    method_source = source[method_start:method_end]

    assert "err instanceof TypeError" in method_source
    assert "error:network_request_failed" in method_source
