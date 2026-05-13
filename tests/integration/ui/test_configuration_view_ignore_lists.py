from pathlib import Path


def test_configuration_view_renders_ignore_list_status_values_outside_translation_labels():
    view = Path("ui/src/views/ConfigurationView.vue").read_text(encoding="utf-8")

    assert "checksIgnoreListConfigs" in view
    assert "config:label_review_ignore_lists" in view
    assert "{{ getChecksIgnoreListStatus(ignoreList.reviewType).count }}" in view
    assert "{{ getChecksIgnoreListStatus(ignoreList.reviewType).path || '-' }}" in view
    assert "config:label_check_ignore_list_count', 'Entries: {count}'" not in view
    assert "config:label_check_ignore_list_path', 'File: {path}'" not in view
