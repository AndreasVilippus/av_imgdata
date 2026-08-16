#!/usr/bin/env python3
from pathlib import Path


def test_worker_does_not_require_local_license_acknowledgement():
    source = Path("worker/src/main.cpp").read_text(encoding="utf-8")

    assert "LICENSE_ACK.json" not in source
    assert "license_ack_present" not in source
    assert "usage_ack_required" not in source
    assert '\"license_authority\": \"dsm\"' in source


def test_worker_governance_documents_dsm_as_license_authority():
    governance = Path("docs/face-model-governance.md").read_text(encoding="utf-8")

    assert "Workers do not create or require a local `LICENSE_ACK.json`" in governance
    assert '"license_authority": "dsm"' in governance


def test_worker_bundle_readme_does_not_expect_local_license_acknowledgement():
    build_script = Path("tools/build-worker.sh").read_text(encoding="utf-8")
    model_readme = build_script.split("cat >\"${readme}\" <<'MODEL_README'", 1)[1].split("MODEL_README", 1)[0]

    assert "Workers do not require a local LICENSE_ACK.json" in model_readme
    assert ".models/face/buffalo_l/LICENSE_ACK.json" not in model_readme
