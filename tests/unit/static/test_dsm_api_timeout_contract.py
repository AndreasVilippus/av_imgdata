from pathlib import Path


def test_slow_operation_endpoints_use_extended_timeout():
    method_source = Path("ui/src/services/dsm-api-client.js").read_text(encoding="utf-8")

    for endpoint in (
        "status",
        "checks_start",
        "checks_progress",
        "checks_findings_status",
        "face_matching_action",
        "face_matching_progress",
        "face_matching_stop",
        "face_matching_findings_status",
        "file_analysis_start",
        "file_analysis_progress",
        "cleanup_start",
        "cleanup_progress",
        "exiftool_status",
        "face_assign_match",
        "face_create_match",
        "face_apply_metadata_match",
        "face_assign_metadata_match",
        "face_create_metadata_match",
        "pip_packages_status",
        "pip_wheelhouse_packages",
        "recognition_findings",
        "recognition_review",
        "recognition_suggestions_apply",
    ):
        assert f"{endpoint}: 120000" in method_source
