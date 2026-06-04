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
    assert "selectedPerson = await this.resolveChecksDuplicateExactPerson(side);" in method
    assert "const shouldRenameOrCreate = this.isChecksMetadataFace(face) || !selectedPerson;" in method
    assert "const canCreatePhotosPerson = this.isChecksPhotosFace(face) && !this.getChecksPhotosFacePersonId(face);" in method
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_replace_metadata_face_name" in method
    assert "new_name: targetName" in method
    assert "review_type: item.review_type" in method
    assert "create_missing_person: canCreatePhotosPerson" in method
    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/checks_assign_face_person" in method
    assert "person_id: selectedPerson.id" in method
    assert "person_name: targetName" in method


def test_duplicate_photos_assignment_resolves_exact_person_before_assigning():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("async resolveChecksDuplicateExactPerson(side)")
    assert start >= 0
    end = mixin.find("\n\t\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "/webman/3rdparty/AV_ImgData/index.cgi/api/face_person_suggest" in method
    assert "name_prefix: targetName" in method
    assert "const exact = suggestions.find((person) =>" in method
    assert "this.selectChecksDuplicateSuggestion(side, exact);" in method


def test_known_photos_face_is_not_created_from_text_name():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    start = mixin.find("getChecksPhotosFacePersonId(face)")
    assert start >= 0
    end = mixin.find("\n\t\t\t},", start)
    assert end > start
    method = mixin[start:end]

    assert "const personId = Number(face.person_id);" in method
    assert "return Number.isFinite(personId) && personId > 0 ? personId : null;" in method


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
