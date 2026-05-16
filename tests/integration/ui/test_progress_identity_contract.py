from pathlib import Path


def _method(source: str, name: str) -> str:
    start = source.find(f"\n\t\t{name}")
    if start >= 0:
        start += 1
    else:
        start = source.find(name)
    assert start >= 0, f"Missing method: {name}"
    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not find end for method: {name}"
    return source[start:end]


def test_checks_progress_identity_rejects_anonymous_updates_after_operation_id_is_known():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method = _method(source, "isChecksProgressUpdateStale(current, next)")

    assert "currentOperationId" in method
    assert "nextOperationId" in method
    assert "currentOperationId && !nextOperationId" in method
    assert "return true" in method[method.find("currentOperationId && !nextOperationId"):]
    assert "currentRevision" in method
    assert "nextRevision" in method
    assert "nextRevision < currentRevision" in method


def test_face_match_progress_identity_rejects_anonymous_updates_after_operation_id_is_known():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")
    method = _method(source, "isFaceMatchProgressUpdateStale(current, next)")

    assert "currentOperationId" in method
    assert "nextOperationId" in method
    assert "currentOperationId && !nextOperationId" in method
    assert "return true" in method[method.find("currentOperationId && !nextOperationId"):]
    assert "currentRevision" in method
    assert "nextRevision" in method
    assert "nextRevision < currentRevision" in method


def test_cleanup_progress_has_operation_id_or_revision_staleness_guard():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")

    assert "isCleanupProgressUpdateStale(" in source
    method = _method(source, "isCleanupProgressUpdateStale(current, next)")
    assert "operation_id" in method
    assert "revision" in method


def test_file_analysis_progress_has_operation_id_or_revision_staleness_guard():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")

    assert "isFileAnalysisProgressUpdateStale(" in source
    method = _method(source, "isFileAnalysisProgressUpdateStale(current, next)")
    assert "operation_id" in method
    assert "revision" in method
