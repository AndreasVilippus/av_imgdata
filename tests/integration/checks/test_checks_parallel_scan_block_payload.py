from pathlib import Path


def test_parallel_checks_scan_block_payload_contains_compatibility_flag():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")
    start = source.find("def _buildChecksStartBlockedPayload(")
    assert start >= 0
    end = source.find("\n    def ", start + 1)
    assert end > start
    method = source[start:end]

    assert "blocked_by_running_scan" in method
