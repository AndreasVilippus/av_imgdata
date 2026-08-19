from pathlib import Path


def _method_body(source: str, method_name: str) -> str:
    start = source.index(f"def {method_name}(")
    next_def = source.find("\n    def ", start + 1)
    return source[start:] if next_def < 0 else source[start:next_def]


def test_face_match_resume_cursors_keep_changed_since_days_for_filtered_scans():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")
    call_marker = "_buildFaceMatchResumeCursor("
    for method_name in (
        "searchPhotoFaceInFile",
        "searchFileFaceInSources",
        "searchMissingPhotosFaces",
        "searchMissingPhotosFacesWithInsightFace",
    ):
        method = _method_body(source, method_name)
        positions = []
        offset = 0
        while True:
            pos = method.find(call_marker, offset)
            if pos < 0:
                break
            positions.append(pos)
            offset = pos + len(call_marker)

        assert positions, method_name
        missing = [
            pos
            for pos in positions
            if "changed_since_days=normalized_changed_since_days" not in method[pos:pos + 1700]
        ]
        assert not missing, method_name
