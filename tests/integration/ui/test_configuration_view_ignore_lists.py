from pathlib import Path


def test_configuration_view_configures_but_does_not_clear_ignore_lists():
    view = Path("ui/src/views/ConfigurationView.vue").read_text(encoding="utf-8")

    assert "checksIgnoreListConfigs" in view
    assert "config:label_review_ignore_lists" in view
    assert "{{ getChecksIgnoreListStatus(ignoreList.reviewType).count }}" not in view
    assert "{{ getChecksIgnoreListStatus(ignoreList.reviewType).path || '-' }}" not in view
    assert "clearChecksIgnoreList(" not in view
    assert "/api/checks_ignore_list_clear" not in view
    assert "config:label_check_ignore_list_count', 'Entries: {count}'" not in view
    assert "config:label_check_ignore_list_path', 'File: {path}'" not in view


def test_configuration_view_contains_missing_photos_item_reindex_runtime_setting():
    view = Path("ui/src/views/ConfigurationView.vue").read_text(encoding="utf-8")

    assert 'v-model="configModel.photos.REINDEX_MISSING_ITEMS"' in view
    assert "REINDEX_MISSING_ITEMS: false" in view
