import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_name_conflicts_refresh_returns_no_findings_update():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    start = source.find("def _safe_refresh_checks_mutation_state")
    function_excerpt = source[start:start + 3000]

    assert 'if normalized_type == "name_conflicts":' in function_excerpt
    assert "return None, None" in function_excerpt
    assert '"entries": []' not in function_excerpt
    assert '"image_entries": []' not in function_excerpt


def test_ui_ignores_snapshot_findings_update_defensively():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "findingsUpdate.refresh_skipped" in source
    assert "findingsUpdate.snapshot_mode" in source
    assert "sourceMode === 'snapshot'" in source
