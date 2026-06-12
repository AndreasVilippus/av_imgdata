import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "av_imgdata" / "db" / "schema.sql"


def _connect(path):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_schema_applies_idempotently(tmp_path):
    connection = _connect(tmp_path / "imgdata.sqlite3")
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    connection.executescript(schema)
    connection.executescript(schema)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_schema_contains_only_active_runtime_tables(tmp_path):
    connection = _connect(tmp_path / "imgdata.sqlite3")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    assert {
        "app_state",
        "name_mappings",
        "face_suppressions",
        "check_suppressions",
        "persisted_findings",
        "persisted_finding_entries",
        "face_match_findings",
        "face_match_finding_entries",
    } <= tables
    assert not {"files", "metadata_faces", "photos_people", "photos_faces", "scan_runs"} & tables


def test_persisted_finding_entries_cascade_on_delete(tmp_path):
    connection = _connect(tmp_path / "imgdata.sqlite3")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO persisted_findings(finding_type, payload_json) VALUES ('duplicate_faces', '{}')"
    )
    connection.execute(
        """
        INSERT INTO persisted_finding_entries(finding_type, position, entry_json)
        VALUES ('duplicate_faces', 0, '{}')
        """
    )
    connection.execute("DELETE FROM persisted_findings WHERE finding_type = 'duplicate_faces'")

    assert connection.execute("SELECT COUNT(*) FROM persisted_finding_entries").fetchone()[0] == 0
