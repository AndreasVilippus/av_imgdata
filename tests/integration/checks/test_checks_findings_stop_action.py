from pathlib import Path


def test_checks_findings_processing_has_stop_state_and_button_label():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "checksStopRequested: false" in mixin
    assert "checksStartRequestInFlight: false" in mixin
    assert "checksStopRequestInFlight: false" in mixin
    assert "checksFindingsActionRunning: false" in mixin
    assert "isChecksFindingsActionRunning()" in mixin
    assert "isChecksReviewActive()" in mixin
    assert "isChecksReviewStopping()" in mixin
    assert "this.selectedChecksAction === 'findings' && this.checksLoading" in mixin
    assert "this.selectedChecksAction === 'scan' && this.checksLoading" not in mixin
    assert "return this.$avt('checks:button_stop', 'Stop')" in mixin


def test_start_checks_review_dispatches_stop_when_findings_are_running():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("startChecksReview(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.isChecksReviewStopping" in method
    assert "return null" in method
    assert "this.isChecksReviewActive" in method
    assert "return this.stopChecksReview()" in method
    assert "this.checksStopRequested = false" in method


def test_stop_checks_review_sets_flag_and_calls_backend_stop():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "stopChecksReview()" in mixin
    assert "this.checksStopRequestInFlight || this.checksStopRequested" in mixin
    assert "this.checksStopRequested = true" in mixin
    assert "this.checksStopRequestInFlight = true" in mixin
    assert "this.checksFindingsActionRunning = false" in mixin
    assert "this.checksStartRequestInFlight = false" in mixin
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_stop" in mixin


def test_checks_stop_state_keeps_button_in_stop_until_backend_finishes():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "isChecksReviewStopping()" in mixin
    stopping_start = mixin.find("isChecksReviewStopping()")
    assert stopping_start >= 0
    stopping = mixin[stopping_start:mixin.find("\n\t\t},", stopping_start)]
    assert "this.checksStopRequested" in stopping
    assert "this.checksStopRequestInFlight" in stopping
    assert "progress.running && progress.stop_requested" in stopping

    label_start = mixin.find("checksPrimaryButtonLabel()")
    assert label_start >= 0
    label = mixin[label_start:mixin.find("\n\t\t},", label_start)]
    assert "this.isChecksReviewActive || this.isChecksReviewStopping" in label
    assert "checks:button_stop" in label


def test_checks_progress_completion_clears_start_and_stop_latches():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("\n\t\tapplyChecksProgress(progress")
    if start >= 0:
        start += 1
    else:
        start = mixin.find("applyChecksProgress(progress")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "nextProgress.running && nextProgress.stop_requested" in method
    assert "this.checksStopRequested = true" in method
    assert "this.checksStopRequestInFlight = false" in method
    assert "if (!nextProgress.running)" in method
    assert "this.checksStopRequested = false" in method
    assert "this.checksStartRequestInFlight = false" in method


def test_fresh_scan_start_invalidates_old_progress_polling():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async startChecksScan(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]
    fresh_start = method[method.find("if (!resumeFromProgress)"):method.find("this.checksEntries = []")]

    assert "this.stopChecksProgressPolling()" in fresh_start
    assert "this.checksProgressRequestId += 1" in fresh_start


def test_checks_actions_respect_stop_requested_state():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "checksStopRequested" in mixin
    assert "this.checksStopRequested = true" in mixin
    assert "this.checksStopRequested = false" in mixin

    # The current optimizations branch does not contain an explicit auto-next
    # loop in checksMixin.js. If such a loop is introduced later, it must either
    # be guarded or call startChecksReview(), which already dispatches Stop.
    unguarded_auto_next = (
        "await this.nextChecksReview();" in mixin
        and "if (!this.checksStopRequested)" not in mixin
    )
    assert not unguarded_auto_next


def test_load_checks_item_loop_stops_when_stop_requested():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async loadChecksItemAtIndex(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "while (resolvedIndex < this.checksEntries.length)" in method
    assert "if (this.checksStopRequested)" in method
    assert "root.stop_requested" in method
    assert "break;" in method


def test_load_checks_item_loop_counts_unresolved_entries_as_skipped():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async loadChecksItemAtIndex(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    guard = "if (!Object.keys(item).length && autoAppliedCount <= 0 && !findingsUpdated)"
    assert guard in method
    guard_start = method.find(guard)
    assert guard_start >= 0
    guard_block = method[guard_start:method.find("\n\t\t\t\t}", guard_start)]
    assert "skipped_count: (Number(currentProgress.skipped_count) || 0) + 1" in guard_block
    assert "checks:status_finding_skipped" in guard_block
    assert "resolvedIndex += 1" in guard_block
    assert "continue;" in guard_block


def test_ensure_checks_result_item_loaded_stops_on_backend_stop_response():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async ensureChecksResultItemLoaded(")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "if (this.checksStopRequested)" in method
    assert "root.stop_requested" in method
    assert "this.checksStopRequested = true" in method
    assert "return;" in method


def test_checks_findings_mutations_continue_from_original_index_after_update():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    for name in (
        "async ignoreChecksCurrentItem()",
        "async deleteChecksMetadataFace(face)",
        "async replaceChecksMetadataFaceName(face, newName, options = {})",
        "async replaceChecksMetadataFacePosition(face, sourceFace)",
        "async assignChecksFaceToPerson(side)",
    ):
        start = mixin.find(name)
        assert start >= 0, name
        end = mixin.find("\n\t\t},", start)
        assert end > start, name
        method = mixin[start:end]

        assert "const reloadIndex = this.checksCurrentIndex;" in method
        assert "await this.loadChecksItemAtIndex(reloadIndex);" in method
        assert "await this.loadChecksItemAtIndex(this.checksCurrentIndex);" not in method
