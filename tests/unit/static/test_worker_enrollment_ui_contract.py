#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_external_worker_ui_formats_utc_times_and_deletes_workers():
    source = (ROOT / "ui" / "src" / "views" / "ExternalWorkerView.vue").read_text(encoding="utf-8")

    assert "new Date(value)" in source
    assert "toLocaleString()" in source
    assert "formatLocalTime(activeEnrollment.expires_at)" in source
    assert "formatLocalTime(worker.last_seen_at)" in source
    assert "external_worker_delete" in source
    assert "window.confirm" in source
    assert "STATE_PATH" not in source


def test_configuration_ui_exposes_worker_pipeline_settings():
    source = (ROOT / "ui" / "src" / "views" / "ConfigurationView.vue").read_text(encoding="utf-8")
    cleanup = (ROOT / "ui" / "src" / "mixins" / "cleanupMixin.js").read_text(encoding="utf-8")

    assert "config:section_worker_pipeline" in source
    assert "configModel.worker_api.ENABLED" in source
    assert "RECOGNITION_BATCH_SIZE" in source
    assert "RECOGNITION_EXTERNAL_WORKER_PREFETCH_BATCHES" in source
    assert "recognition_batch_size = Math.max" in cleanup
    assert "external_worker_prefetch_batches = Boolean" in cleanup


def test_windows_initializer_never_silently_ignores_enrollment_code():
    source = (ROOT / "worker" / "packaging" / "windows" / "Initialize-AVImgDataWorker.ps1").read_text(encoding="utf-8")

    assert "$hasToken -and $hasEnrollmentCode -and -not $ForceEnroll" in source
    assert "The code was not used" in source
    assert "-ForceEnroll" in source
    assert "[System.IO.Path]::IsPathRooted($ConfigPath)" in source
    assert "Join-Path $BundleRoot $ConfigPath" in source
    assert "worker.token.json" in source
    assert "[switch]$InsecureTls" in source
    assert "ServerCertificateValidationCallback" in source
    assert '@("--insecure-tls")' in source


def test_admin_api_exposes_authenticated_worker_delete():
    source = (ROOT / "src" / "api" / "worker_admin_api.py").read_text(encoding="utf-8")

    assert '@router.post("/external_worker_delete")' in source
    assert "_prepare_session_request(request)" in source
    assert "delete_worker(worker_id=worker_id)" in source


def test_worker_start_scripts_allow_missing_token_for_enrollment():
    windows = (ROOT / "worker" / "packaging" / "windows" / "Start-AVImgDataWorker.ps1").read_text(encoding="utf-8")
    unix = (ROOT / "worker" / "packaging" / "unix" / "start-av-imgdata-worker.sh").read_text(encoding="utf-8")

    assert "[string]$EnrollmentCode" in windows
    assert "[switch]$InsecureTls" in windows
    assert "foreach ($required in @($ApiLoop, $WorkerBin, $ConfigPath, $InitializeScript))" in windows
    assert 'Read-Host "Worker token not found. Enter registration code"' in windows
    assert "ModelPack = $ModelPack" in windows
    assert "$initializeArgs.EnrollmentCode = $EnrollmentCode" in windows
    assert "$initializeArgs.InsecureTls = $true" in windows
    assert "& $InitializeScript @initializeArgs" in windows
    assert '"Models:    synchronized from DSM authority"' in windows
    assert '@("--insecure-tls")' in windows

    assert "--enrollment-code" in unix
    assert "--insecure-tls" in unix
    assert 'for required in "$API_LOOP" "$WORKER_BIN" "$CONFIG_PATH" "$INIT_SCRIPT"; do' in unix
    assert 'Worker token not found. Enter registration code: ' in unix
    assert 'set -- sh "$INIT_SCRIPT"' in unix
    assert "Models:    synchronized from DSM authority" in unix
    assert 'set -- "$@" --insecure-tls' in unix


def test_worker_start_scripts_sync_models_before_claiming_jobs():
    windows = (ROOT / "worker" / "packaging" / "windows" / "Start-AVImgDataWorker.ps1").read_text(encoding="utf-8")
    unix = (ROOT / "worker" / "packaging" / "unix" / "start-av-imgdata-worker.sh").read_text(encoding="utf-8")

    assert windows.index("& $InitializeScript @initializeArgs") < windows.index("& $ApiLoop @loopArgs")
    assert unix.index('"$@"\n\nprintf') < unix.index('set -- "$API_LOOP"')
