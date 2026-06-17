from pathlib import Path


def _method_body(source: str, method_name: str) -> str:
    for marker in (f"\t\t{method_name}(", f"\t\tasync {method_name}("):
        start = source.find(marker)
        if start >= 0:
            break
    else:
        raise AssertionError(f"Method not found: {method_name}")

    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not find end of method {method_name}"
    return source[start:end]


def test_cleanup_ui_has_schema_status_helpers_before_rendering_progress():
    source = Path("ui/src/mixins/cleanupMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/CleanupView.vue").read_text(encoding="utf-8")

    assert "getCleanupStatusProgress(" in source
    progress_helper = _method_body(source, "getCleanupStatusProgress")
    assert "status.schema_version === 1" in progress_helper
    assert "status.progress" in progress_helper

    assert "getCleanupStatusCounters(" in source
    counter_helper = _method_body(source, "getCleanupStatusCounters")
    assert "status.schema_version === 1" in counter_helper
    assert "status.counters" in counter_helper

    assert "vm.getCleanupStatusProgress()" in view
    assert "vm.getCleanupStatusCounters()" in view


def test_file_analysis_ui_has_schema_status_helpers_before_rendering_progress():
    source = Path("ui/src/mixins/statusMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/StatusView.vue").read_text(encoding="utf-8")

    assert "getFileAnalysisStatusProgress(" in source
    progress_helper = _method_body(source, "getFileAnalysisStatusProgress")
    assert "status.schema_version === 1" in progress_helper
    assert "status.progress" in progress_helper

    assert "getFileAnalysisStatusCounters(" in source
    counter_helper = _method_body(source, "getFileAnalysisStatusCounters")
    assert "status.schema_version === 1" in counter_helper
    assert "status.counters" in counter_helper

    assert "vm.getFileAnalysisStatusProgress()" in view
    assert "vm.getFileAnalysisStatusCounters()" in view


def test_status_view_places_system_before_files_and_pip_packages_below_files():
    view = Path("ui/src/views/StatusView.vue").read_text(encoding="utf-8")

    system_pos = view.index("status:system_title")
    files_pos = view.index("status:files_title")
    pip_pos = view.index("status:pip_packages_title")

    assert system_pos < files_pos < pip_pos
    assert "vm.getStatusPipPackageStatusBlocks(packageStatus)" in view
    assert "vm.getStatusPipPackageStatusBlockLabel(statusBlock)" in view
