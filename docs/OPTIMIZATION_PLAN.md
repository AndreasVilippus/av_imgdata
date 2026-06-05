# Optimization Plan

This document tracks technical optimization topics for `AV_ImgData`.

## SQL persistence layer

### Decision

Use **SQLite** as the package-local persistence layer.

SQLite is the best fit for this package because `AV_ImgData` is a Synology DSM package with `noarch` package metadata and currently stores runtime data in the package-var directory. A package-local embedded database keeps the package self-contained and avoids service dependencies such as PostgreSQL, MariaDB, MongoDB, or Redis.

The database file should be stored below the writable package-var directory:

```text
${SYNOPKG_PKGVAR}/imgdata.sqlite3
```

Fallback path when `SYNOPKG_PKGVAR` is unavailable:

```text
/var/packages/AV_ImgData/var/imgdata.sqlite3
```

### Scope

SQLite should be used for dynamic runtime data that benefits from indexes, constraints, migrations, and transactional updates:

- persistent name mappings
- scan and normalization state
- file and metadata caches
- metadata face records
- face suppression records for known-uninteresting faces
- schema migration state

The existing `config.json` should initially remain file-based. Configuration is small, human-readable, and stable enough not to require SQL storage in the first migration step.

### Non-goals

Do not add a server database dependency to the package for this optimization step.

Not selected:

- PostgreSQL: strong database, but unnecessary service dependency for this package
- MariaDB/MySQL: only useful if the package intentionally depends on an external DSM database service
- MongoDB: too heavy for this structured local state
- Redis: suitable as cache, not as the primary persistent store
- DuckDB: good analytical embedded database, but not the best primary transactional store for package runtime state
- LMDB/RocksDB/LevelDB: embedded and fast, but less convenient for relational state, schema migrations, and ad-hoc inspection

### Proposed backend layout

```text
src/av_imgdata/db/
├── __init__.py
├── path.py
├── connection.py
├── schema.py
├── migrations.py
└── repositories/
    ├── name_mappings.py
    ├── scan_state.py
    ├── face_suppression.py
    └── file_cache.py
```

Access to SQLite should go through repository classes. Avoid SQL statements spread across API handlers, scanner logic, or UI-facing modules.

### Connection defaults

Recommended connection settings:

```python
import os
import sqlite3
from pathlib import Path

PACKAGE_NAME = "AV_ImgData"


def get_pkgvar_dir() -> Path:
    value = os.environ.get("SYNOPKG_PKGVAR")
    if value:
        return Path(value)
    return Path(f"/var/packages/{PACKAGE_NAME}/var")


def get_db_path() -> Path:
    return get_pkgvar_dir() / "imgdata.sqlite3"


def connect() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA journal_mode = WAL")
    return con
```

Notes:

- `foreign_keys` must be enabled per connection.
- `busy_timeout` reduces transient failures during parallel access.
- `WAL` should be used when supported by the DSM filesystem. Backup and support documentation must include `imgdata.sqlite3-wal` and `imgdata.sqlite3-shm`.

### Initial schema

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS name_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'metadata',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_name, source_kind)
);

CREATE INDEX IF NOT EXISTS idx_name_mappings_source_name
ON name_mappings(source_name);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    mtime_ns INTEGER,
    size_bytes INTEGER,
    content_hash TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_path
ON files(path);

CREATE TABLE IF NOT EXISTS metadata_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    source_schema TEXT NOT NULL,
    face_name TEXT,
    region_x REAL,
    region_y REAL,
    region_w REAL,
    region_h REAL,
    fingerprint TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_metadata_faces_file_id
ON metadata_faces(file_id);

CREATE INDEX IF NOT EXISTS idx_metadata_faces_face_name
ON metadata_faces(face_name);

CREATE TABLE IF NOT EXISTS face_suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suppression_key TEXT NOT NULL UNIQUE,
    suppression_type TEXT NOT NULL,
    file_path TEXT,
    face_name TEXT,
    region_x REAL,
    region_y REAL,
    region_w REAL,
    region_h REAL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Migration from JSON

The first migration should import the existing runtime name mappings from:

```text
${SYNOPKG_PKGVAR}/name_mappings.json
```

Fallback path:

```text
/var/packages/AV_ImgData/var/name_mappings.json
```

Migration rules:

1. Create or open `imgdata.sqlite3`.
2. Apply schema migrations idempotently.
3. If migration version `1` is not present, read `name_mappings.json` if it exists.
4. Insert mappings into `name_mappings` with `source_kind = 'metadata'` unless the JSON format already carries a more specific source kind.
5. Mark migration version `1` as applied.
6. Do not delete `name_mappings.json` during the migration.
7. After a successful migration, write new mapping changes only to SQLite.

### Face suppression workflow

The `face_suppression` table is the persistence mechanism for faces that are known but intentionally irrelevant.

Use cases:

- A metadata face should no longer be proposed although it remains present in image metadata.
- A Synology Photos face should be ignored for package matching logic.
- A repeated false-positive region should be suppressed by fingerprint or region key.

Recommended suppression key variants:

```text
metadata-face:<file-hash>:<region-fingerprint>
metadata-name:<normalized-name>
photos-face:<photos-person-id-or-face-id>
manual:<stable-user-defined-key>
```

Scanner and check logic should evaluate suppression before returning candidates to the UI.

### Repository contract

Example repository interface:

```python
class NameMappingRepository:
    def get_target_name(self, source_name: str, source_kind: str = "metadata") -> str | None:
        ...

    def upsert_mapping(self, source_name: str, target_name: str, source_kind: str = "metadata") -> None:
        ...

    def list_mappings(self) -> list[dict]:
        ...
```

Equivalent repositories should be introduced for scan state, face suppression, and file cache data.

### Package lifecycle impact

Package scripts should ensure that the package-var directory exists before the backend opens SQLite.

Runtime and backup-relevant files:

```text
config.json
name_mappings.json
imgdata.sqlite3
imgdata.sqlite3-wal
imgdata.sqlite3-shm
```

Uninstall behavior:

- Do not remove SQLite data during normal package removal unless DSM explicitly performs a data purge.
- Do not silently overwrite a corrupted database.
- Prefer a startup error with clear diagnostics over automatic destructive recovery.

### Test plan

Unit tests should use a temporary SQLite file, never the real DSM package-var directory.

Required tests:

- package-var path resolution with `SYNOPKG_PKGVAR`
- fallback path resolution without `SYNOPKG_PKGVAR`
- schema creation is idempotent
- migration from missing `name_mappings.json`
- migration from existing `name_mappings.json`
- name mapping insert and update via upsert
- unique constraint on `(source_name, source_kind)`
- metadata face rows cascade-delete when their file row is removed
- face suppression prevents duplicate suppression keys
- scan state can be updated by key
- read access works while another connection is open
- write contention produces a controlled timeout or retryable package error
- startup does not silently replace a corrupt database

### Logical validation already performed

The proposed schema was checked with an isolated SQLite database using Python's standard `sqlite3` module.

Validated behavior:

- schema can be applied repeatedly without failure
- `PRAGMA journal_mode = WAL` can be activated in a normal writable filesystem
- `name_mappings` supports conflict-based upsert through `(source_name, source_kind)`
- `metadata_faces` rows are deleted through `ON DELETE CASCADE` when their parent file is removed
- `face_suppression.suppression_key` rejects duplicates
- `scan_state` supports key-based update semantics

No DSM runtime test has been performed yet. The next implementation step must add repository-level tests to the existing Python test suite and then run the package build wrapper.

### Implementation order

1. Add `src/av_imgdata/db/` with path, connection, schema, and migration modules.
2. Add tests for path resolution, schema creation, and migration state.
3. Add `NameMappingRepository` and migrate current name-mapping callers.
4. Import existing `name_mappings.json` on first startup.
5. Add `FaceSuppressionRepository`.
6. Filter suppressed faces before returning match/check candidates to the UI.
7. Add file and metadata cache tables where repeated scans currently recompute stable data.
8. Update README with the runtime database location and backup notes.
9. Run the existing package build wrapper from the toolkit root.

### Acceptance criteria

The optimization is ready when all criteria are met:

- existing behavior for name mappings remains unchanged from the UI perspective
- a fresh install creates SQLite state automatically
- an existing install imports `name_mappings.json` exactly once
- deleting or suppressing an irrelevant face prevents it from being proposed again by package logic
- tests cover schema, migration, repositories, and suppression behavior
- the package build wrapper completes successfully
