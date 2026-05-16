from pathlib import Path


def test_checks_name_mapping_prompt_memory_is_part_of_state():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "checksAcceptedNameMappings: {}" in source
    assert "checksNameMappingKey(sourceName, targetName)" in source
    assert "checksHasAcceptedNameMapping(sourceName, targetName)" in source
    assert "recordChecksAcceptedNameMapping(sourceName, targetName)" in source


def test_checks_saved_mapping_is_remembered_before_next_item():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    record_pos = source.index("if (result.mapping_saved)")
    update_pos = source.index("this.applyChecksFindingsUpdate(result.findings_update, { resolvedDelta: 1 });")

    assert record_pos < update_pos
    assert "this.recordChecksAcceptedNameMapping(sourceName, targetName);" in source


def test_checks_mapping_prompt_uses_runtime_memory():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    method_start = source.index("checksRenameUsesStoredMapping(item, face, newName)")
    suggested_state_start = source.index("const leftName = String(item.left_name || '').trim();", method_start)
    memory_check_pos = source.index("this.checksHasAcceptedNameMapping(faceName, targetName)", method_start)

    assert memory_check_pos < suggested_state_start
