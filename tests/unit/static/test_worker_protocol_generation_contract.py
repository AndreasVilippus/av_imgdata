#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

from services.worker_protocol_generated import (
    CAPABILITIES,
    CONFIG_SCHEMA_VERSION,
    INPUT_MODES,
    PROTOCOL_VERSION,
    STATE_SCHEMA_VERSION,
    TOKEN_SCOPES,
    WORKER_VERSION,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_generated_worker_protocol_files_are_current():
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "generate-worker-protocol.py"), "--check"],
        cwd=str(PROJECT_ROOT),
        check=True,
    )


def test_python_protocol_matches_canonical_descriptor():
    descriptor = json.loads(
        (PROJECT_ROOT / "worker" / "protocol" / "worker-protocol.json").read_text(encoding="utf-8")
    )

    assert PROTOCOL_VERSION == descriptor["protocol_version"]
    assert WORKER_VERSION == descriptor["worker_version"]
    assert CONFIG_SCHEMA_VERSION == descriptor["config_schema_version"]
    assert STATE_SCHEMA_VERSION == descriptor["state_schema_version"]
    assert list(TOKEN_SCOPES) == descriptor["token_scopes"]
    assert list(CAPABILITIES) == descriptor["capabilities"]
    assert list(INPUT_MODES) == descriptor["input_modes"]


def test_cmake_uses_the_canonical_worker_version():
    cmake = (PROJECT_ROOT / "worker" / "CMakeLists.txt").read_text(encoding="utf-8")

    assert f'set(AV_IMGDATA_WORKER_VERSION "{WORKER_VERSION}"' in cmake
    assert 'AV_IMGDATA_WORKER_VERSION="0.1.0-phase-d"' not in cmake
    assert 'AV_IMGDATA_WORKER_VERSION="0.1.0-phase-h1"' not in cmake


def test_cpp_api_loop_uses_generated_protocol_constants():
    source = (PROJECT_ROOT / "worker" / "src" / "api_loop.cpp").read_text(encoding="utf-8")

    assert '#include "av_imgdata/worker_protocol.h"' in source
    assert "av_imgdata::worker::capabilities_json()" in source
    assert "av_imgdata::worker::input_modes_json()" in source
    assert "input_shared_path" not in source
    assert source.index('api_post(config, "register"') < source.index('api_post(config, "heartbeat"')
