from pathlib import Path


def test_database_lists_ui_has_navigation_search_pagination_edit_and_delete():
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")
    sidebar = Path("ui/src/components/AppSidebarNav.vue").read_text(encoding="utf-8")
    view = Path("ui/src/views/DatabaseListsView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/databaseListsMixin.js").read_text(encoding="utf-8")

    assert "selectedOption === 'database_lists'" in app
    assert "$emit('select', 'database_lists')" in sidebar
    assert "databaseListSearch" in view
    assert "databaseListPageSize" in view
    assert "saveDatabaseNameMapping" in view
    assert "startDatabaseNameMappingEdit(entry)" in view
    assert "deleteDatabaseNameMapping(entry)" in view
    assert "/api/database_name_mappings" in mixin
    assert "/api/database_name_mapping_save" in mixin
    assert "/api/database_name_mapping_delete" in mixin
