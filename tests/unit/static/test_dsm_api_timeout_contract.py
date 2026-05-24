from pathlib import Path


def test_operation_start_and_write_endpoints_use_extended_timeout():
    source = Path("ui/src/App.vue").read_text(encoding="utf-8")
    method_start = source.index("getDsmApiTimeoutMs(apiPath, options = {})")
    method_end = source.index("formatBackendError", method_start)
    method_source = source[method_start:method_end]

    for endpoint in (
        "checks_start",
        "face_matching_action",
        "file_analysis_start",
        "cleanup_start",
        "face_assign_match",
        "face_create_match",
        "face_apply_metadata_match",
        "face_assign_metadata_match",
        "face_create_metadata_match",
    ):
        assert f"{endpoint}: 120000" in method_source
