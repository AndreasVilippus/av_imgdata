-- AV_ImgData SQLite schema
-- Schema version: 5
-- Target: SQLite, package-local database imgdata.sqlite3

PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    checksum TEXT,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'json',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS name_mappings (
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

CREATE INDEX IF NOT EXISTS idx_name_mappings_normalized_source_name
ON name_mappings(normalized_source_name);

CREATE TABLE IF NOT EXISTS face_suppressions (
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

CREATE INDEX IF NOT EXISTS idx_face_suppressions_enabled
ON face_suppressions(enabled);

CREATE TABLE IF NOT EXISTS check_suppressions (
    review_type TEXT NOT NULL,
    token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (review_type, token)
);

CREATE TABLE IF NOT EXISTS persisted_findings (
    finding_type TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL DEFAULT '{}',
    entry_count INTEGER NOT NULL DEFAULT 0 CHECK (entry_count >= 0),
    status TEXT,
    action TEXT,
    check_type TEXT,
    shared_folder TEXT,
    save_only INTEGER NOT NULL DEFAULT 0 CHECK (save_only IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS persisted_finding_entries (
    finding_type TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    image_path TEXT,
    source_name TEXT,
    entry_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (finding_type, position),
    FOREIGN KEY (finding_type) REFERENCES persisted_findings(finding_type) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_persisted_finding_entries_image_path
ON persisted_finding_entries(finding_type, image_path);

CREATE TABLE IF NOT EXISTS face_match_findings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    job_id TEXT,
    status TEXT,
    action TEXT,
    shared_folder TEXT,
    auto INTEGER NOT NULL DEFAULT 0 CHECK (auto IN (0, 1)),
    save_only INTEGER NOT NULL DEFAULT 0 CHECK (save_only IN (0, 1)),
    transferred_count INTEGER NOT NULL DEFAULT 0 CHECK (transferred_count >= 0),
    entry_count INTEGER NOT NULL DEFAULT 0 CHECK (entry_count >= 0),
    started_at TEXT,
    finished_at TEXT,
    last_updated_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_match_finding_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL CHECK (position >= 0),
    action TEXT,
    image_path TEXT,
    source_name TEXT,
    entry_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (finding_id) REFERENCES face_match_findings(id) ON DELETE CASCADE,
    UNIQUE (finding_id, position)
);

CREATE INDEX IF NOT EXISTS idx_face_match_finding_entries_image_path
ON face_match_finding_entries(image_path);

CREATE VIEW IF NOT EXISTS active_name_mappings AS
SELECT * FROM name_mappings WHERE enabled = 1;

CREATE VIEW IF NOT EXISTS active_face_suppressions AS
SELECT * FROM face_suppressions WHERE enabled = 1;

CREATE TRIGGER IF NOT EXISTS trg_app_state_updated_at
AFTER UPDATE ON app_state
BEGIN
    UPDATE app_state SET updated_at = CURRENT_TIMESTAMP WHERE key = OLD.key;
END;

CREATE TRIGGER IF NOT EXISTS trg_name_mappings_updated_at
AFTER UPDATE ON name_mappings
BEGIN
    UPDATE name_mappings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_face_suppressions_updated_at
AFTER UPDATE ON face_suppressions
BEGIN
    UPDATE face_suppressions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_face_match_findings_updated_at
AFTER UPDATE ON face_match_findings
BEGIN
    UPDATE face_match_findings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

INSERT OR IGNORE INTO schema_migrations(version, name, checksum)
VALUES (1, 'initial_sqlite_schema', NULL);

PRAGMA user_version = 5;

COMMIT;
