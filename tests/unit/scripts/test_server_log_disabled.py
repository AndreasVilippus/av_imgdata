from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "start-stop-status"


def test_server_log_is_disabled_without_rotation_monitor():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'LEGACY_LOG_FILE="${VAR_DIR}/server.log"' in source
    assert 'LOG_FILE="/dev/null"' in source
    assert 'rm -f "${LEGACY_LOG_FILE}" "${LEGACY_LOG_FILE}".*' in source
    assert "--no-access-log" in source
    assert "--log-level critical" in source
    assert "start_log_rotation_monitor" not in source
