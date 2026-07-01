import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from services.config_service import ConfigService

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IEXEC)


def test_start_script_updates_install_on_start_config(tmp_path: Path) -> None:
    pkgdest = tmp_path / "pkgdest"
    pkgvar = tmp_path / "pkgvar"
    pkgdest.mkdir(parents=True)
    pkgvar.mkdir(parents=True)

    venv_bin = pkgdest / "var" / "venv" / "bin"
    venv_bin.mkdir(parents=True)

    # Ensure start script's PYTHONPATH points to the real package sources
    src_link = pkgdest / "src"
    try:
        src_link.symlink_to(REPO_ROOT / "src")
    except Exception:
        # If symlink creation fails, fall back to copying minimal package
        pass

    python_stub = venv_bin / "python"
    python_stub.write_text(
        """#!/bin/sh
if [ "$1" = "-c" ]; then
    exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "av_imgdata.db.bootstrap" ]; then
    # Simulate successful DB bootstrap in test environment
    exit 0
fi
exec python3 "$@"
""",
        encoding="utf-8",
    )
    make_executable(python_stub)
    pip_stub = venv_bin / "pip"
    pip_stub.write_text(
        """#!/bin/sh
exit 0
""",
        encoding="utf-8",
    )
    make_executable(pip_stub)

    uvicorn_stub = venv_bin / "uvicorn"
    uvicorn_stub.write_text(
        """#!/bin/sh
while true; do
  sleep 10
  continue
 done
""",
        encoding="utf-8",
    )
    make_executable(uvicorn_stub)

    config = {
        "pip_packages": {
            "INSIGHTFACE": {
                "ENABLED": True,
                "INSTALL_ON_START": True,
                "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                "WHEELHOUSE_ENABLED": False,
                "WHEELHOUSE_MANIFEST_URL": "https://example.invalid/releases/download/dsm7-x86_64-python38/wheelhouse-manifest.json",
                "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
            }
        }
    }
    config_path = pkgvar / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    wrapper_script = f"""#!/bin/sh
set -e
export SYNOPKG_PKGDEST={pkgdest}
export SYNOPKG_PKGVAR={pkgvar}
export PYTHON={python_stub}
export UVICORN={uvicorn_stub}
"{REPO_ROOT}/scripts/start-stop-status" start
"""

    wrapper_path = tmp_path / "run_start.sh"
    wrapper_path.write_text(wrapper_script, encoding="utf-8")
    make_executable(wrapper_path)

    result = subprocess.run([str(wrapper_path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"Start script failed (stdout={result.stdout!r}, stderr={result.stderr!r})"
        )

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    insightface = updated["pip_packages"]["INSIGHTFACE"]

    expected_defaults = ConfigService.defaultConfig()["pip_packages"]["INSIGHTFACE"]
    assert insightface["WHEELHOUSE_ENABLED"] is True
    assert insightface["WHEELHOUSE_MANIFEST_URL"] == expected_defaults["WHEELHOUSE_MANIFEST_URL"]
    assert insightface["WHEELHOUSE_TARGET"] == expected_defaults["WHEELHOUSE_TARGET"]
    assert insightface["REQUIREMENTS_FILE"] == expected_defaults["REQUIREMENTS_FILE"]

    pid_file = pkgvar / "AV_ImgData.pid"
    assert pid_file.exists(), "Start script should write a PID file"
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass
    time.sleep(0.1)
