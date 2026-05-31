from pathlib import Path


def test_position_deviation_uses_inner_position_buttons():
    source = Path("ui/src/components/ChecksFacePane.vue").read_text(encoding="utf-8")

    assert 'v-if="vm.isChecksPositionReplacementSupported(item) && vm.canReplaceChecksFacePosition(item, actionFace, positionSourceFace)"' in source
    assert '@click.prevent="vm.replaceChecksMetadataFacePosition(actionFace, positionSourceFace)"' in source
    assert (
        "return this.isLeft ? 'checks-position-button checks-position-button-right' : "
        "'checks-position-button checks-position-button-left';"
    ) in source


def test_duplicate_and_position_deviation_support_action_controls_without_overlap():
    pane = Path("ui/src/components/ChecksFacePane.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    styles = Path("ui/src/styles/app.css").read_text(encoding="utf-8")

    assert 'v-if="vm.isChecksFaceAssignmentSupported(item) && actionFace"' in pane
    assert "actionFace() {" in pane
    assert "return this.targetFace || this.face;" in pane
    assert "vm.getChecksSyncFaceBaseIconUrl()" in pane
    assert "vm.getChecksSyncFaceOverlayIconUrl()" in pane
    assert ".checks-face-name-input-wrap {\n\tfont-weight: 400;\n\tposition: relative;\n\tz-index: 30;" in styles
    assert ".checks-face-name-field .face-match-suggest-list {\n\tz-index: 31;" in styles
    assert "isChecksFaceAssignmentSupported(item) {" in mixin
    assert "return this.isChecksDuplicateFaces(item) || this.isChecksPositionDeviation(item);" in mixin
    assert "isChecksPositionReplacementSupported(item) {" in mixin
    assert "&& this.isChecksPositionReplacementSupported(item)" in mixin
    assert "if (!this.isChecksFaceAssignmentSupported(item) || this.checksActionLocked" in mixin
    assert "if (!this.isChecksFaceAssignmentSupported(item)) {" in mixin
    assert ".checks-position-button {\n\tposition: absolute;\n\ttop: 48px;" in styles
    assert ".checks-sync-button {\n\tposition: absolute;\n\ttop: 88px;" in styles


def test_position_replacement_requires_different_source_formats():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "getChecksFaceSourceFormat(face) {" in mixin
    assert "const targetFormat = this.getChecksFaceSourceFormat(face);" in mixin
    assert "const sourceFormat = this.getChecksFaceSourceFormat(sourceFace);" in mixin
    assert "&& targetFormat !== sourceFormat;" in mixin
