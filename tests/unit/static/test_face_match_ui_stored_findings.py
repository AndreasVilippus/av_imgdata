from pathlib import Path


def test_stored_face_match_transfer_can_remove_metadata_entry_without_face_id():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "async advanceFaceMatchFindingsAfterTransfer(data)" in source
    assert "const currentIndex = Math.max(0, Number(this.faceMatchFindingIndex) || 0)" in source
    assert "const removedByBackend = !!(findingsUpdate && findingsUpdate.removed)" in source
    assert "const removedCount = Math.max(0, Number(findingsUpdate && findingsUpdate.removed_count) || 0)" in source
    assert "if (!faceId && removedByBackend && removedCount > 0 && index === currentIndex)" in source
    assert "index !== currentIndex" in source
    assert "const nextIndex = Math.min(currentIndex, remainingEntries.length - 1)" in source


def test_stored_face_match_transfer_still_removes_existing_photos_face_by_face_id():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "if (faceId)" in source
    assert "const entryFaceId = Number(entry && entry.face && entry.face.face_id)" in source
    assert "Number.isFinite(entryFaceId) && entryFaceId === faceId" in source
