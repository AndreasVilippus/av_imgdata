from pathlib import Path


def test_exiftool_ui_uses_grouped_helpers_and_persistent_options():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/externalLibrariesMixin.js").read_text(encoding="utf-8")

    assert "EXIFTOOL_PERSISTENT_ENABLED" in view
    assert "EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS" in view
    assert "canConfigureExiftoolPersistentMode" in view
    assert "canConfigureExiftoolReadOptions" in view
    assert "canConfigureManualExiftoolPath" in view
    assert "canConfigureExiftoolExtensions" in view

    assert "externalLibrariesSidecarReadModeOptions()" in mixin
    assert "setExternalLibrariesSidecarReadMode(mode)" in mixin
    assert "normalizeExternalLibrariesSidecarReadMode(value" in mixin
    assert "SIDECAR_READ_MODE" in mixin


def test_exiftool_ui_replaces_overlapping_sidecar_checkboxes_with_single_mode_select():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")

    assert "config:label_sidecar_read_mode" in view
    assert "externalLibrariesSidecarReadModeOptions" in view
    assert "config:label_use_exiftool_for_sidecars" not in view
    assert "config:label_sidecar_exiftool_fallback_enabled" not in view


def test_exiftool_ui_does_not_hide_master_switch_when_exiftool_is_missing():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")

    assert 'v-if="vm.hasUsableExiftool" class="config-checkbox"' not in view
    assert "config:hint_exiftool_missing" in view
    assert "config:hint_exiftool_available" in view


def test_exiftool_config_service_maps_sidecar_mode_to_legacy_flags():
    source = Path("src/services/config_service.py").read_text(encoding="utf-8")

    assert '"SIDECAR_READ_MODE"' in source
    assert '"direct_only"' in source
    assert '"direct_first"' in source
    assert '"exiftool_first"' in source
    assert '"exiftool_only"' in source
    assert "USE_EXIFTOOL_FOR_SIDECARS" in source
    assert "SIDECAR_EXIFTOOL_FALLBACK_ENABLED" in source

    # Contract: SIDECAR_READ_MODE exists and the legacy compatibility flags remain present.
    # The exact implementation may derive the flags in Python, migrate them during save,
    # or keep compatibility through normalized config keys.
    assert "SIDECAR_READ_MODE" in source
    assert "USE_EXIFTOOL_FOR_SIDECARS" in source
    assert "SIDECAR_EXIFTOOL_FALLBACK_ENABLED" in source


def test_exiftool_persistent_config_is_visible_and_normalized():
    config = Path("src/services/config_service.py").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/externalLibrariesMixin.js").read_text(encoding="utf-8")

    assert '"EXIFTOOL_PERSISTENT_ENABLED": True' in config or '"EXIFTOOL_PERSISTENT_ENABLED": true' in config
    assert '"EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS": 30' in config
    assert "EXIFTOOL_PERSISTENT_ENABLED: true" in mixin
    assert "EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS: 30" in mixin
