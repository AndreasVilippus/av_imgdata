from pathlib import Path


def _block(source: str, marker: str, end_marker: str) -> str:
    start = source.find(marker)
    assert start >= 0, f"Missing marker: {marker}"
    end = source.find(end_marker, start + len(marker))
    assert end > start, f"Missing end marker: {end_marker}"
    return source[start:end]


def test_face_match_number_from_is_method_not_computed():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    computed = _block(source, "\tcomputed: {", "\twatch: {")
    methods = _block(source, "\tmethods: {", "\t\tgetFaceMatchStatusCounterLabel(")

    assert "faceMatchNumberFrom(...values)" not in computed
    assert "faceMatchNumberFrom(...values)" in methods
    assert "this.faceMatchNumberFrom(" in computed
