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
    assert 'class="checks-number-field"' in block
    assert "v-model.number=\"vm.checksChangedSinceDays\"" in block
    assert 'class="checks-number-input"' in block
    assert ':disabled="vm.checksLoading"' in block
    assert 'class="face-match-switch"' not in block
    assert "vm.selectedChecksAction !== 'scan'" not in block

    switches_row_start = view.rfind('class="checks-actions-row checks-actions-row-switches"', 0, label_pos)
    assert switches_row_start >= 0
    assert view.find("checks:switch_auto_apply_suggested_names", switches_row_start, label_pos) >= 0
    assert view.find("checks:switch_auto_apply_suggested_duplicates", switches_row_start, label_pos) >= 0


def test_checks_changed_since_days_field_is_right_aligned():
    styles = Path("ui/src/styles/app.css").read_text(encoding="utf-8")

    selector_pos = styles.find(".checks-number-field")
    assert selector_pos >= 0
    block_start = styles.find("{", selector_pos)
    block_end = styles.find("}", block_start)
    assert block_start >= 0
    assert block_end > block_start
    block = styles[block_start:block_end]

    assert "margin-left: auto;" in block
