from pathlib import Path


def test_operation_start_and_write_endpoints_use_extended_timeout():
    method_source = Path("ui/src/services/dsm-api-client.js").read_text(encoding="utf-8")

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
