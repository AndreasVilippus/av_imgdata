import tempfile
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def isolated_synopkg_pkgvar(monkeypatch):
    """Keep runtime-state writes isolated between tests.

    The package stores progress and findings below SYNOPKG_PKGVAR. Build runs
    provide a temporary package var, but a single shared directory still allows
    one test's persisted stop/progress state to influence later tests. Give each
    test its own package var directory so tests cannot depend on execution
    order or previously persisted runtime state.
    """
    with tempfile.TemporaryDirectory() as tempdir:
        monkeypatch.setenv("SYNOPKG_PKGVAR", tempdir)
        yield
