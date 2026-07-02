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


def test_pip_packages_ui_can_load_select_install_and_reinstall_wheelhouse_packages():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/externalLibrariesMixin.js").read_text(encoding="utf-8")
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    client = Path("ui/src/services/dsm-api-client.js").read_text(encoding="utf-8")

    assert "vm.loadPipWheelhousePackages" in view
    assert "vm.selectedPipWheelhousePackageName" in view
    assert "vm.installSelectedPipWheelhousePackage(false)" in view
    assert "vm.installSelectedPipWheelhousePackage(true)" in view
    assert "/api/pip_wheelhouse_packages" in mixin
    assert "/api/pip_wheelhouse_package_install" in mixin
    assert "@router.post(\"/pip_wheelhouse_packages\")" in api
    assert "@router.post(\"/pip_wheelhouse_package_install\")" in api
    assert "pip_wheelhouse_package_install: 900000" in client


def test_native_face_processor_config_is_visible_with_python_fallback():
    view = Path("ui/src/views/ExternalLibrariesView.vue").read_text(encoding="utf-8")
    mixin = Path("ui/src/mixins/externalLibrariesMixin.js").read_text(encoding="utf-8")
    config = Path("src/services/config_service.py").read_text(encoding="utf-8")

    assert "native_processors" in view
    assert "FACE_PROCESSOR" in view
    assert "setExternalLibrariesNativeProcessorConfigValue" in view
    assert "label_enable_native_face_processor" in view
    assert "label_native_face_processor_path" in view
    assert "INSIGHTFACE_LICENSE_ACKNOWLEDGED" in view
    assert "label_acknowledge_insightface_model_license" in view
    assert "native_face_processor_license_hint" in view
    assert "native_processors" in mixin
    assert "INSIGHTFACE_LICENSE_ACKNOWLEDGED: false" in mixin
    assert "FALLBACK_TO_PYTHON" not in mixin
    assert '"native_processors"' in config
    assert '"FACE_PROCESSOR"' in config
    assert '"INSIGHTFACE_LICENSE_ACKNOWLEDGED": False' in config


def test_configuration_view_exposes_backend_debug_log_path():
    view = Path("ui/src/views/ConfigurationView.vue").read_text(encoding="utf-8")
    ger = Path("ui/texts/ger/strings").read_text(encoding="utf-8")
    enu = Path("ui/texts/enu/strings").read_text(encoding="utf-8")

    assert "configModel.debug.BACKEND_DEBUG_LOG_PATH" in view
    assert "config:label_backend_debug_log_path" in view
    assert "config:placeholder_backend_debug_log_path" in view
    assert "config:hint_backend_debug_log_path_input" in view
    assert "label_backend_debug_log_path=" in ger
    assert "label_backend_debug_log_path=" in enu
