from pathlib import Path


def _concept() -> str:
    return Path("docs/status-concept-integrated.md").read_text(encoding="utf-8")


def test_integrated_status_concept_scopes_historical_progress_by_action_and_mode():
    concept = _concept()

    assert "operation`, `mode`, `action`, and `operation_id` form the process identity" in concept
    assert "specific action/check type and mode" in concept
    assert "historical non-running state from a different action/check type or mode" in concept
    assert "neutral/idle for the requested identity" in concept
    assert "A running state from another action/check type or mode may still be returned" in concept


def test_status_concept_defines_state_ownership_and_mode_identity():
    concept = _concept()

    assert "The backend owns status semantics" in concept
    assert "UI renders the status structure" in concept
    assert "`operation`, `mode`, `action`, and `operation_id` form the process identity" in concept
    assert "A `scan` state and a `findings` state must not overwrite each other" in concept
    assert "`immediate` uses only the active run state" in concept
    assert "`save_only` writes a persistent findings list" in concept
    assert "`findings` processes only an explicitly selected persistent findings list" in concept
    assert "A saved findings list is not read by `immediate` or `save_only`" in concept


def test_status_concept_scopes_stop_requested_to_operation_and_mode():
    concept = _concept()

    assert "`stop_requested` applies only to the operation, action/check type, and mode that produced it" in concept
    assert "historical `face_match:progress_stopping` message is normalized to `face_match:progress_stopped`" in concept


def test_status_concept_covers_prioritized_operation_review_list():
    concept = _concept()

    expected_regressions = [
        "UI must not immediately apply scan progress over an active findings review",
        "Checks views must discover running check scans across check types and adopt only matching scan state",
        "Persisted scan progress must not reset a running findings review",
        "cleanup",
        "file_analysis",
    ]
    for expected in expected_regressions:
        assert expected in concept


def test_status_concept_keeps_mode_matrix_for_checks_and_face_match_findings():
    concept = _concept()

    assert "### Stored findings review" in concept
    assert "| `operation` | `checks` |" in concept
    assert "| `operation` | `face_match` |" in concept
    assert "| `mode` | `findings` |" in concept
    assert "| Progress | `entries` |" in concept


def test_status_concept_defines_stale_stopping_as_non_blocking():
    concept = _concept()

    assert "Stale runtime status without a live worker must not keep an active stopping message" in concept
    assert "historical `face_match:progress_stopping` message is normalized" in concept
    assert "cross-operation blocking" in concept


def test_status_concept_defines_saved_findings_as_source_of_truth_after_save_only_run():
    concept = _concept()

    assert "For save-only scans, `findings` counts only entries actually written to the later stored findings list" in concept
    assert "A saved findings list is not read by `immediate` or `save_only` unless the current run explicitly requests a resume" in concept
    assert "Do not show `findings` when `entries.total` already describes list size" in concept
    assert "UI must not add counters from legacy fields such as `findings_count`" in concept


def test_status_concept_defines_save_only_findings_streaming_persistence():
    concept = _concept()

    assert "`save_only` | `true`" in concept
    assert "For save-only scans, `findings` counts only entries actually written to the later stored findings list" in concept
    assert "If auto-transfer is active, `findings` counts only entries that remain in the later findings list" in concept


def test_status_concept_lists_recent_runtime_regressions():
    concept = _concept()

    assert "finished` must not show an active progress bar just because `current == total`" in concept
    assert "`entries.current` must not decrease after `next` or successful apply" in concept
    assert "A removed entry counts as completed" in concept
    assert "Persisted scan progress must not reset a running findings review" in concept
    assert "If auto-transfer is active, `findings` counts only entries that remain in the later findings list" in concept


def test_status_concept_defines_monotonic_face_match_findings_review_position():
    concept = _concept()

    assert "`entries.total` remains the loaded initial list size during review" in concept
    assert "`entries.current` must not decrease after `next` or successful apply" in concept
    assert "A removed entry counts as completed" in concept
    assert "Persisted scan progress must not reset a running findings review" in concept


def test_status_concept_defines_live_face_match_partial_scan_progress_base():
    concept = _concept()

    assert "UI is responsible for" in concept
    assert "preserving local review state until backend mutation responses replace it" in concept
    assert "guarding against stale progress overwrites" in concept


def test_status_concept_requires_preparing_status_for_file_list_scans():
    concept = _concept()

    assert "File-list-based scans should write a preparing status before expensive candidate listing" in concept
    assert "`preparing` | preparing candidates or runtime data" in concept
    assert "`listing_files`" in concept
