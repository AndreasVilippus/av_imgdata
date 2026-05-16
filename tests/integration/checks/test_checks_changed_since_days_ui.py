from pathlib import Path


def test_checks_changed_since_days_input_is_only_visible_for_scan():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    label_pos = view.find("checks:label_changed_since_days")
    assert label_pos >= 0

    label_start = view.rfind("<label", 0, label_pos)
    label_end = view.find("</label>", label_pos)
    assert label_start >= 0
    assert label_end > label_start
    block = view[label_start:label_end]

    assert 'v-if="vm.selectedChecksAction === \'scan\'"' in block
    assert "v-model.number=\"vm.checksChangedSinceDays\"" in block
    assert ':disabled="vm.checksLoading"' in block
    assert "vm.selectedChecksAction !== 'scan'" not in block
