import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .connection import Database, DatabaseError
from .repositories.name_mappings import NameMappingRepository
from .repositories.face_match_findings import FaceMatchFindingsRepository
from .repositories.app_state import AppStateRepository
from .repositories.check_suppressions import CheckSuppressionRepository
from .repositories.persisted_findings import PersistedFindingsRepository


LEGACY_NAME_MAPPINGS_MIGRATION = 2
LEGACY_NAME_MAPPINGS_MIGRATION_NAME = "import_legacy_name_mappings_json"
SQLITE_RUNTIME_MIGRATION = 4
SQLITE_RUNTIME_MIGRATION_NAME = "sqlite_runtime_state_and_remove_sync_tables"
LEGACY_FINDINGS_MIGRATION = 5
LEGACY_FINDINGS_MIGRATION_NAME = "import_legacy_findings_json"


def _read_legacy_mappings(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception as exc:
        raise DatabaseError(f"cannot import legacy name mappings from {path}: {exc}") from exc
    values = raw.get("name_mappings") if isinstance(raw, dict) else raw
    return [dict(item) for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def migrate_legacy_name_mappings(database: Database, legacy_path: Path) -> None:
    database.initialize()
    repository = NameMappingRepository(database)
    with database.transaction() as connection:
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (LEGACY_NAME_MAPPINGS_MIGRATION,),
        ).fetchone()
        if migrated:
            return
        mappings: Iterable[Dict[str, Any]] = _read_legacy_mappings(legacy_path)
        repository.upsert_many(mappings, connection=connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, name, checksum) VALUES (?, ?, NULL)",
            (LEGACY_NAME_MAPPINGS_MIGRATION, LEGACY_NAME_MAPPINGS_MIGRATION_NAME),
        )


def migrate_legacy_findings(database: Database, package_var: Path) -> None:
    """Import old findings files once; operational findings access stays SQLite-only."""
    database.initialize()
    with database.read() as connection:
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (LEGACY_FINDINGS_MIGRATION,),
        ).fetchone()
    if migrated:
        return

    face_match_findings = FaceMatchFindingsRepository(database)
    if not face_match_findings.read(include_entries=False):
        payload = _read_legacy_dict(package_var / "analysis_findings" / "face_match.json")
        if payload:
            face_match_findings.write(payload)

    findings = PersistedFindingsRepository(database)
    for finding_type in (
        "dimension_issues",
        "duplicate_faces",
        "position_deviations",
        "name_conflicts",
        "face_match_candidates",
    ):
        if findings.read(finding_type, include_entries=False):
            continue
        payload = _read_legacy_dict(
            package_var / "analysis_findings" / f"{finding_type}.json"
        )
        if payload:
            findings.write(finding_type, payload)

    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, name, checksum) VALUES (?, ?, NULL)",
            (LEGACY_FINDINGS_MIGRATION, LEGACY_FINDINGS_MIGRATION_NAME),
        )
        connection.execute(f"PRAGMA user_version = {LEGACY_FINDINGS_MIGRATION}")


def migrate_runtime_persistence(database: Database, package_var: Path) -> None:
    database.initialize()
    with database.read() as connection:
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (SQLITE_RUNTIME_MIGRATION,),
        ).fetchone()
    if migrated:
        return

    app_state = AppStateRepository(database)
    latest = _read_legacy_dict(package_var / "file_analysis.json")
    if latest:
        app_state.set("file_analysis:latest", latest)
    runtime_dir = package_var / "runtime_state"
    if runtime_dir.is_dir():
        for path in runtime_dir.glob("*.json"):
            payload = _read_legacy_dict(path)
            if payload:
                state_type, state_key = _legacy_runtime_identity(path.stem)
                app_state.set(f"runtime:{state_type}:{state_key}", payload)

    suppressions = CheckSuppressionRepository(database)
    ignore_dir = package_var / "ignore_lists"
    for review_type in ("duplicate_faces", "position_deviations", "name_conflicts"):
        path = ignore_dir / f"checks_ignore_{review_type}.txt"
        if path.is_file():
            tokens = list(dict.fromkeys(
                line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            ))
            suppressions.replace(review_type, tokens)

    connection = database.connect()
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP VIEW IF EXISTS open_face_candidates")
        connection.execute("DROP VIEW IF EXISTS active_name_mappings")
        connection.execute("DROP VIEW IF EXISTS active_face_suppressions")
        connection.execute("DROP TRIGGER IF EXISTS trg_name_mappings_updated_at")
        connection.execute("DROP TRIGGER IF EXISTS trg_face_suppressions_updated_at")
        _rebuild_active_tables_without_sync_foreign_keys(connection)
        for table in (
            "scan_run_files",
            "scan_runs",
            "face_assignment_actions",
            "face_match_candidates",
            "photos_faces",
            "photos_people",
            "metadata_faces",
            "file_metadata_cache",
            "files",
            "scan_roots",
            "operation_log",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.commit()
    finally:
        connection.close()

    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, name, checksum) VALUES (?, ?, NULL)",
            (SQLITE_RUNTIME_MIGRATION, SQLITE_RUNTIME_MIGRATION_NAME),
        )


def _read_legacy_dict(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise DatabaseError(f"cannot import legacy JSON from {path}: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def _legacy_runtime_identity(stem: str) -> Tuple[str, str]:
    for state_type in (
        "file_analysis_progress",
        "face_match_progress",
        "checks_progress",
        "cleanup_progress",
    ):
        prefix = f"{state_type}_"
        if stem.startswith(prefix):
            return state_type, stem[len(prefix):]
    state_type, _, state_key = stem.partition("_")
    return state_type, state_key or "default"


def _rebuild_active_tables_without_sync_foreign_keys(connection: Any) -> None:
    connection.executescript(
        """
        ALTER TABLE name_mappings RENAME TO name_mappings_legacy_sync;
        CREATE TABLE name_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            normalized_source_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            normalized_target_name TEXT NOT NULL,
            target_photos_person_id INTEGER,
            source_kind TEXT NOT NULL DEFAULT 'metadata',
            mapping_kind TEXT NOT NULL DEFAULT 'alias',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            priority INTEGER NOT NULL DEFAULT 100,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (normalized_source_name, source_kind)
        );
        INSERT INTO name_mappings
        SELECT id, source_name, normalized_source_name, target_name,
               normalized_target_name, target_photos_person_id, source_kind,
               mapping_kind, enabled, priority, note, created_at, updated_at
        FROM name_mappings_legacy_sync;
        DROP TABLE name_mappings_legacy_sync;

        ALTER TABLE face_suppressions RENAME TO face_suppressions_legacy_sync;
        CREATE TABLE face_suppressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suppression_key TEXT NOT NULL UNIQUE,
            suppression_type TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'candidate',
            normalized_name TEXT,
            region_fingerprint TEXT,
            reason TEXT,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO face_suppressions(
            id, suppression_key, suppression_type, scope, normalized_name,
            region_fingerprint, reason, enabled, created_at, updated_at
        )
        SELECT id, suppression_key, suppression_type, scope, normalized_name,
               region_fingerprint, reason, enabled, created_at, updated_at
        FROM face_suppressions_legacy_sync;
        DROP TABLE face_suppressions_legacy_sync;

        CREATE VIEW active_name_mappings AS
        SELECT * FROM name_mappings WHERE enabled = 1;
        CREATE VIEW active_face_suppressions AS
        SELECT * FROM face_suppressions WHERE enabled = 1;
        CREATE TRIGGER trg_name_mappings_updated_at
        AFTER UPDATE ON name_mappings
        BEGIN
            UPDATE name_mappings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        CREATE TRIGGER trg_face_suppressions_updated_at
        AFTER UPDATE ON face_suppressions
        BEGIN
            UPDATE face_suppressions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """
    )
