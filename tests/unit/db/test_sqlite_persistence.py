import json
import sqlite3

import pytest

from av_imgdata.db.connection import Database, DatabaseError
from av_imgdata.db.bootstrap import initialize_runtime_database
from av_imgdata.db.migrations import (
    LEGACY_FINDINGS_MIGRATION,
    LEGACY_NAME_MAPPINGS_MIGRATION,
    SQLITE_RUNTIME_MIGRATION,
    migrate_legacy_findings,
    migrate_legacy_name_mappings,
    migrate_runtime_persistence,
)
from av_imgdata.db.path import get_db_path, get_pkgvar_dir
from av_imgdata.db.repositories.face_suppressions import FaceSuppressionRepository
from av_imgdata.db.repositories.face_match_findings import FaceMatchFindingsRepository
from av_imgdata.db.repositories.app_state import AppStateRepository
from av_imgdata.db.repositories.name_mappings import NameMappingRepository
from av_imgdata.db.repositories.persisted_findings import PersistedFindingsRepository


def test_package_var_path_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNOPKG_PKGVAR", str(tmp_path))

    assert get_pkgvar_dir() == tmp_path
    assert get_db_path() == tmp_path / "imgdata.sqlite3"


def test_package_var_fallback_path(monkeypatch):
    monkeypatch.delenv("SYNOPKG_PKGVAR", raising=False)

    assert get_db_path().as_posix() == "/var/packages/AV_ImgData/var/imgdata.sqlite3"


def test_runtime_bootstrap_creates_database_and_imports_legacy_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNOPKG_PKGVAR", str(tmp_path))
    (tmp_path / "name_mappings.json").write_text(
        json.dumps({"name_mappings": [{"source_name": "Alias", "target_name": "Person"}]}),
        encoding="utf-8",
    )
    path = initialize_runtime_database()

    assert path == tmp_path / "imgdata.sqlite3"
    assert NameMappingRepository(Database(str(path))).find_mapping("Alias") == {
        "source_name": "Alias",
        "target_name": "Person",
    }


def test_database_initialization_and_repositories(tmp_path):
    database = Database(str(tmp_path / "imgdata.sqlite3"))
    database.initialize()
    database.initialize()

    mappings = NameMappingRepository(database)
    assert mappings.upsert_mapping("Mäx", "Max")
    assert mappings.upsert_mapping("mäx", "Max Mustermann")
    assert mappings.find_mapping("MÄX") == {
        "source_name": "mäx",
        "target_name": "Max Mustermann",
    }

    suppressions = FaceSuppressionRepository(database)
    assert suppressions.suppress("metadata-name:max", "metadata_name")
    assert suppressions.suppress("metadata-name:max", "metadata_name")
    assert suppressions.is_suppressed("metadata-name:max")
    assert suppressions.unsuppress("metadata-name:max")
    assert not suppressions.is_suppressed("metadata-name:max")

    app_state = AppStateRepository(database)
    assert app_state.set("scan:last", {"path": "/photos", "count": 2})
    assert app_state.get("scan:last") == {"path": "/photos", "count": 2}



def test_name_mapping_repository_lists_filtered_pages_and_deletes_by_id(tmp_path):
    repository = NameMappingRepository(Database(str(tmp_path / "imgdata.sqlite3")))
    repository.upsert_mapping("Alias Alpha", "Person One")
    repository.upsert_mapping("Alias Beta", "Person Two")
    repository.upsert_mapping("Legacy", "Person Three", source_kind="import")

    first_page = repository.list_page(page=1, page_size=2)
    filtered = repository.list_page(search="person two", page=1, page_size=25)

    assert first_page["total"] == 3
    assert len(first_page["entries"]) == 2
    assert filtered["total"] == 1
    assert filtered["entries"][0]["source_name"] == "Alias Beta"
    assert repository.delete_mapping(filtered["entries"][0]["id"])
    assert repository.list_page(search="Alias Beta")["total"] == 0
    assert not repository.delete_mapping(filtered["entries"][0]["id"])


def test_legacy_name_mapping_migration_is_idempotent_and_preserves_source(tmp_path):
    legacy_path = tmp_path / "name_mappings.json"
    legacy_payload = {
        "name_mappings": [
            {"source_name": "Alias", "target_name": "Person"},
            {"source_name": "", "target_name": "Ignored"},
        ]
    }
    legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    database = Database(str(tmp_path / "imgdata.sqlite3"))

    migrate_legacy_name_mappings(database, legacy_path)
    legacy_path.write_text(
        json.dumps({"name_mappings": [{"source_name": "Later", "target_name": "Change"}]}),
        encoding="utf-8",
    )
    migrate_legacy_name_mappings(database, legacy_path)

    assert NameMappingRepository(database).list_mappings() == [
        {"source_name": "Alias", "target_name": "Person"}
    ]
    with database.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (LEGACY_NAME_MAPPINGS_MIGRATION,),
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert legacy_path.exists()


def test_missing_legacy_name_mapping_file_marks_migration_complete(tmp_path):
    database = Database(str(tmp_path / "imgdata.sqlite3"))

    migrate_legacy_name_mappings(database, tmp_path / "missing.json")

    with database.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (LEGACY_NAME_MAPPINGS_MIGRATION,),
        ).fetchone()[0] == 1


def test_corrupt_database_is_not_replaced(tmp_path):
    db_path = tmp_path / "imgdata.sqlite3"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(DatabaseError):
        Database(str(db_path)).initialize()

    assert db_path.read_text(encoding="utf-8") == "not a sqlite database"


def test_read_access_works_while_another_connection_is_open(tmp_path):
    database = Database(str(tmp_path / "imgdata.sqlite3"))
    database.initialize()
    repository = NameMappingRepository(database)
    repository.upsert_mapping("Alias", "Person")

    first = database.connect()
    try:
        assert repository.find_mapping("Alias")["target_name"] == "Person"
    finally:
        first.close()


def test_unused_sync_tables_are_not_created(tmp_path):
    database = Database(str(tmp_path / "imgdata.sqlite3"))
    database.initialize()
    with database.read() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert not {
        "scan_roots",
        "files",
        "file_metadata_cache",
        "metadata_faces",
        "photos_people",
        "photos_faces",
        "face_match_candidates",
        "face_assignment_actions",
        "scan_runs",
        "scan_run_files",
        "operation_log",
    } & tables


def test_face_match_findings_repository_round_trip_and_delete(tmp_path):
    repository = FaceMatchFindingsRepository(Database(str(tmp_path / "imgdata.sqlite3")))
    payload = {
        "job_id": "job-1",
        "status": "finished",
        "action": "mark_missing_photos_faces",
        "shared_folder": "/volume1/photo",
        "auto": False,
        "save_only": True,
        "transferred_count": 2,
        "count": 99,
        "custom_status": "preserved",
        "entries": [
            {
                "action": "mark_missing_photos_faces",
                "image_path": "/volume1/photo/a.jpg",
                "source_name": "Alice",
                "metadata_face": {"name": "Alice"},
            },
            {
                "action": "mark_missing_photos_faces",
                "image_path": "/volume1/photo/b.jpg",
                "source_name": "Bob",
                "metadata_face": {"name": "Bob"},
            },
        ],
    }

    assert repository.write(payload)
    stored = repository.read()
    status = repository.read(include_entries=False)

    assert stored["count"] == 2
    assert stored["entries"] == payload["entries"]
    assert stored["custom_status"] == "preserved"
    assert status["count"] == 2
    assert "entries" not in status
    assert repository.delete()
    assert repository.read() == {}


def test_legacy_findings_migration_replaces_json_with_sqlite_once(tmp_path):
    findings_dir = tmp_path / "analysis_findings"
    findings_dir.mkdir()
    face_match_path = findings_dir / "face_match.json"
    duplicate_path = findings_dir / "duplicate_faces.json"
    face_match_path.write_text(json.dumps({
        "status": "finished",
        "entries": [{"image_path": "/volume1/photo/face.jpg"}],
    }), encoding="utf-8")
    duplicate_path.write_text(json.dumps({
        "status": "finished",
        "entries": [{"image_path": "/volume1/photo/duplicate.jpg"}],
    }), encoding="utf-8")
    database = Database(str(tmp_path / "imgdata.sqlite3"))

    migrate_legacy_findings(database, tmp_path)
    face_match_path.write_text(json.dumps({"status": "changed"}), encoding="utf-8")
    duplicate_path.write_text(json.dumps({"status": "changed"}), encoding="utf-8")
    migrate_legacy_findings(database, tmp_path)

    assert FaceMatchFindingsRepository(database).read()["entries"] == [
        {"image_path": "/volume1/photo/face.jpg"}
    ]
    assert PersistedFindingsRepository(database).read("duplicate_faces")["entries"] == [
        {"image_path": "/volume1/photo/duplicate.jpg"}
    ]
    with database.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (LEGACY_FINDINGS_MIGRATION,),
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_legacy_findings_migration_does_not_replace_existing_sqlite_data(tmp_path):
    findings_dir = tmp_path / "analysis_findings"
    findings_dir.mkdir()
    (findings_dir / "face_match.json").write_text(
        json.dumps({"entries": [{"image_path": "/legacy.jpg"}]}),
        encoding="utf-8",
    )
    database = Database(str(tmp_path / "imgdata.sqlite3"))
    repository = FaceMatchFindingsRepository(database)
    repository.write({"entries": [{"image_path": "/sqlite.jpg"}]})

    migrate_legacy_findings(database, tmp_path)

    assert repository.read()["entries"] == [{"image_path": "/sqlite.jpg"}]


def test_runtime_migration_imports_legacy_state_and_removes_sync_tables(tmp_path):
    db_path = tmp_path / "imgdata.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE photos_people(id INTEGER PRIMARY KEY);
        CREATE TABLE files(id INTEGER PRIMARY KEY);
        CREATE TABLE metadata_faces(id INTEGER PRIMARY KEY);
        CREATE TABLE photos_faces(id INTEGER PRIMARY KEY);
        CREATE TABLE name_mappings(
            id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            normalized_source_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            normalized_target_name TEXT NOT NULL,
            target_photos_person_id INTEGER,
            source_kind TEXT NOT NULL DEFAULT 'metadata',
            mapping_kind TEXT NOT NULL DEFAULT 'alias',
            enabled INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 100,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(normalized_source_name, source_kind),
            FOREIGN KEY(target_photos_person_id) REFERENCES photos_people(id)
        );
        CREATE TABLE face_suppressions(
            id INTEGER PRIMARY KEY,
            suppression_key TEXT NOT NULL UNIQUE,
            suppression_type TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'candidate',
            file_id INTEGER,
            metadata_face_id INTEGER,
            photos_face_id INTEGER,
            photos_person_id INTEGER,
            normalized_name TEXT,
            region_fingerprint TEXT,
            reason TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE face_match_candidates(id INTEGER PRIMARY KEY);
        CREATE TABLE scan_roots(id INTEGER PRIMARY KEY);
        CREATE TABLE scan_runs(id INTEGER PRIMARY KEY);
        CREATE TABLE scan_run_files(id INTEGER PRIMARY KEY);
        CREATE TABLE face_assignment_actions(id INTEGER PRIMARY KEY);
        CREATE TABLE operation_log(id INTEGER PRIMARY KEY);
        INSERT INTO name_mappings(
            source_name, normalized_source_name, target_name, normalized_target_name
        ) VALUES ('Alias', 'alias', 'Person', 'person');
        INSERT INTO face_suppressions(suppression_key, suppression_type)
        VALUES ('face-match:test', 'manual');
        """
    )
    connection.close()
    runtime_path = tmp_path / "runtime_state" / "checks_progress_user_duplicate_faces.json"
    runtime_path.parent.mkdir()
    runtime_path.write_text(json.dumps({"running": False}), encoding="utf-8")

    database = Database(str(db_path))
    migrate_runtime_persistence(database, tmp_path)

    with database.read() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (SQLITE_RUNTIME_MIGRATION,),
        ).fetchone()[0] == 1
    assert "files" not in tables
    assert "photos_people" not in tables
    assert PersistedFindingsRepository(database).read("duplicate_faces") == {}
    assert AppStateRepository(database).get("runtime:checks_progress:user_duplicate_faces") == {
        "running": False
    }
    assert NameMappingRepository(database).find_mapping("Alias")["target_name"] == "Person"
    assert FaceSuppressionRepository(database).is_suppressed("face-match:test")
