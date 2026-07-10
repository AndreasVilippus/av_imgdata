#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone

from api import worker_admin_api


def _iso(value):
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_admin_status_masks_secrets_and_reports_enrollment_state(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    state = {
        "enrollments": {
            "pending": {
                "code_hash": "secret-hash",
                "created_at": _iso(now),
                "expires_at": _iso(now + timedelta(minutes=10)),
                "used_at": None,
                "worker_id": None,
            },
            "completed": {
                "code_hash": "other-secret-hash",
                "created_at": _iso(now - timedelta(minutes=5)),
                "expires_at": _iso(now + timedelta(minutes=5)),
                "used_at": _iso(now - timedelta(minutes=1)),
                "worker_id": "worker-01",
            },
        },
        "workers": {
            "worker-01": {
                "status": "ready",
                "version": "1.0",
                "capabilities": ["face_native_embed"],
                "last_seen_at": _iso(now),
            }
        },
        "tokens": {"token-id": {"token_hash": "must-not-leak"}},
    }
    state_path = tmp_path / "worker-api-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("SYNOPKG_PKGVAR", str(tmp_path))
    monkeypatch.delenv("AV_IMGDATA_WORKER_API_STATE_PATH", raising=False)

    result = worker_admin_api._admin_status()

    assert result["enrollments"][0]["status"] in {"waiting", "enrolled"}
    by_id = {entry["enrollment_id"]: entry for entry in result["enrollments"]}
    assert by_id["pending"]["status"] == "waiting"
    assert by_id["completed"]["status"] == "enrolled"
    assert "code_hash" not in by_id["pending"]
    assert "tokens" not in result
    assert result["workers"][0]["worker_id"] == "worker-01"
