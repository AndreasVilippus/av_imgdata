import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_name_conflicts_refresh_guard_is_not_auto_only():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")

    assert 'if normalized_type == "name_conflicts":' in source
    assert 'if normalized_type == "name_conflicts" and bool(request_context.get("auto"))' not in source
    assert '"refresh_skipped": True' in source
    assert '"snapshot_mode": True' in source


def test_name_conflicts_snapshot_reason_is_generic():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")

    assert "name_conflicts_snapshot_mode" in source
