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


def test_windows_initializer_never_silently_ignores_enrollment_code():
    source = (ROOT / "worker" / "packaging" / "windows" / "Initialize-AVImgDataWorker.ps1").read_text(encoding="utf-8")

    assert "$hasToken -and $hasEnrollmentCode -and -not $ForceEnroll" in source
    assert "The code was not used" in source
    assert "-ForceEnroll" in source
    assert "[System.IO.Path]::IsPathRooted($ConfigPath)" in source
    assert "Join-Path $BundleRoot $ConfigPath" in source
    assert "worker.token.json" in source


def test_admin_api_exposes_authenticated_worker_delete():
    source = (ROOT / "src" / "api" / "worker_admin_api.py").read_text(encoding="utf-8")

    assert '@router.post("/external_worker_delete")' in source
    assert "_prepare_session_request(request)" in source
    assert "delete_worker(worker_id=worker_id)" in source
