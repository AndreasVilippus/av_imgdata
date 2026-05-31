from pathlib import Path


def test_app_delegates_dsm_api_behavior_to_service():
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")
    client = Path("ui/src/services/dsm-api-client.js").read_text(encoding="utf-8")

    assert "createDsmApiClient" in app
    assert "this.dsmApiClient.callDsmApi(apiPath, body, options)" in app
    assert "synocredential._instance.Resume()" not in app
    assert "synocredential._instance.Resume()" in client
    assert "new AbortController()" not in app
    assert "new AbortController()" in client


def test_app_delegates_backend_error_formatting_to_service():
    app = Path("ui/src/App.vue").read_text(encoding="utf-8")
    formatter = Path("ui/src/services/backend-error-formatter.js").read_text(encoding="utf-8")

    assert "createBackendErrorFormatter" in app
    assert "this.backendErrorFormatter.formatBackendError(backendError, fallback)" in app
    assert "details.retryable === true" not in app
    assert "details.retryable === true" in formatter


def test_structure_check_validates_dsm_cookies_in_extracted_client():
    checker = Path("tools/check_syntax_and_structure.py").read_text(encoding="utf-8")

    assert 'dsm_api_client_path = ROOT / "ui" / "src" / "services" / "dsm-api-client.js"' in checker
    assert 'f"{cookie_name}: readCookie(\'{cookie_name}\')"' in checker
    assert 'ui/src/App.vue: DSM cookie' not in checker
