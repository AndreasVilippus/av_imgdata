from pathlib import Path


def test_duplicate_metadata_face_assignment_uses_metadata_rename_endpoint():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async assignChecksFaceToPerson(side)")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "this.isChecksMetadataFace(face)" in method
    assert "(item.right_face_target || item.right_face)" in method
    assert "(item.left_face_target || item.left_face)" in method
    assert "const shouldRenameOrCreate = this.isChecksMetadataFace(face) || !state.selectedPerson;" in method
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_replace_metadata_face_name" in method
    assert "new_name: targetName" in method
    assert "review_type: item.review_type" in method
    assert "create_missing_person: this.isChecksPhotosFace(face)" in method
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_assign_face_person" in method
    assert "person_id: state.selectedPerson.id" in method
    assert "person_name: targetName" in method


def test_duplicate_face_assignment_allows_typed_metadata_and_photos_names():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("canAssignChecksFaceToPerson(item, side)")
    assert start >= 0
    end = mixin.find("\n\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "const name = String(state.name || '').trim();" in method
    assert "if (!face || !name)" in method
    assert "return this.isChecksMetadataFace(face) || this.isChecksPhotosFace(face)" in method
