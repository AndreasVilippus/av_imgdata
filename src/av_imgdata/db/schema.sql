-- AV_ImgData SQLite schema
-- Schema version: 1
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
    value_type TEXT NOT NULL DEFAULT 'text' CHECK (value_type IN ('text', 'json', 'integer', 'real', 'boolean')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path TEXT NOT NULL UNIQUE,
    label TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    include_hidden INTEGER NOT NULL DEFAULT 0 CHECK (include_hidden IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_root_id INTEGER,
    path TEXT NOT NULL UNIQUE,
    parent_path TEXT,
    filename TEXT NOT NULL,
    extension TEXT,
    mime_type TEXT,
    size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
    mtime_ns INTEGER,
    ctime_ns INTEGER,
    inode TEXT,
    content_hash TEXT,
    content_hash_algorithm TEXT,
    metadata_hash TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TEXT,
    scan_status TEXT NOT NULL DEFAULT 'new' CHECK (scan_status IN ('new', 'queued', 'scanning', 'ok', 'warning', 'error', 'missing', 'ignored')),
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scan_root_id) REFERENCES scan_roots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_files_scan_root_id ON files(scan_root_id);
CREATE INDEX IF NOT EXISTS idx_files_parent_path ON files(parent_path);
CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);
CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_scan_status ON files(scan_status);
CREATE INDEX IF NOT EXISTS idx_files_last_scanned_at ON files(last_scanned_at);

CREATE TABLE IF NOT EXISTS file_metadata_cache (
    file_id INTEGER NOT NULL,
    cache_key TEXT NOT NULL,
    cache_value TEXT NOT NULL,
    cache_format TEXT NOT NULL DEFAULT 'json' CHECK (cache_format IN ('json', 'text')),
    source_tool TEXT,
    source_tool_version TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, cache_key),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metadata_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    source_schema TEXT NOT NULL CHECK (source_schema IN ('acdsee', 'microsoft', 'mwg_regions', 'xmp_mp', 'xmp_mwg_rs', 'unknown')),
    source_tag TEXT,
    source_index INTEGER,
    face_name TEXT,
    normalized_name TEXT,
    role TEXT,
    region_unit TEXT NOT NULL DEFAULT 'relative' CHECK (region_unit IN ('relative', 'pixel', 'unknown')),
    region_x REAL,
    region_y REAL,
    region_w REAL,
    region_h REAL,
    image_width INTEGER CHECK (image_width IS NULL OR image_width >= 0),
    image_height INTEGER CHECK (image_height IS NULL OR image_height >= 0),
    region_fingerprint TEXT,
    raw_region_json TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE (file_id, source_schema, source_index)
);

CREATE INDEX IF NOT EXISTS idx_metadata_faces_file_id ON metadata_faces(file_id);
CREATE INDEX IF NOT EXISTS idx_metadata_faces_face_name ON metadata_faces(face_name);
CREATE INDEX IF NOT EXISTS idx_metadata_faces_normalized_name ON metadata_faces(normalized_name);
CREATE INDEX IF NOT EXISTS idx_metadata_faces_region_fingerprint ON metadata_faces(region_fingerprint);
CREATE INDEX IF NOT EXISTS idx_metadata_faces_is_deleted ON metadata_faces(is_deleted);

CREATE TABLE IF NOT EXISTS photos_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photos_person_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    normalized_name TEXT,
    face_count INTEGER CHECK (face_count IS NULL OR face_count >= 0),
    cover_face_id TEXT,
    is_hidden INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
    is_unknown INTEGER NOT NULL DEFAULT 0 CHECK (is_unknown IN (0, 1)),
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photos_people_display_name ON photos_people(display_name);
CREATE INDEX IF NOT EXISTS idx_photos_people_normalized_name ON photos_people(normalized_name);
CREATE INDEX IF NOT EXISTS idx_photos_people_is_unknown ON photos_people(is_unknown);

CREATE TABLE IF NOT EXISTS photos_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photos_face_id TEXT NOT NULL UNIQUE,
    photos_person_id INTEGER,
    file_id INTEGER,
    photos_file_id TEXT,
    photos_item_id TEXT,
    region_unit TEXT NOT NULL DEFAULT 'relative' CHECK (region_unit IN ('relative', 'pixel', 'unknown')),
    region_x REAL,
    region_y REAL,
    region_w REAL,
    region_h REAL,
    region_fingerprint TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    is_unknown INTEGER NOT NULL DEFAULT 0 CHECK (is_unknown IN (0, 1)),
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photos_person_id) REFERENCES photos_people(id) ON DELETE SET NULL,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_photos_faces_person_id ON photos_faces(photos_person_id);
CREATE INDEX IF NOT EXISTS idx_photos_faces_file_id ON photos_faces(file_id);
CREATE INDEX IF NOT EXISTS idx_photos_faces_region_fingerprint ON photos_faces(region_fingerprint);
CREATE INDEX IF NOT EXISTS idx_photos_faces_is_unknown ON photos_faces(is_unknown);

CREATE TABLE IF NOT EXISTS name_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    normalized_source_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    normalized_target_name TEXT NOT NULL,
    target_photos_person_id INTEGER,
    source_kind TEXT NOT NULL DEFAULT 'metadata' CHECK (source_kind IN ('metadata', 'photos', 'manual', 'import')),
    mapping_kind TEXT NOT NULL DEFAULT 'alias' CHECK (mapping_kind IN ('alias', 'rename', 'merge', 'ignore')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    priority INTEGER NOT NULL DEFAULT 100,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (target_photos_person_id) REFERENCES photos_people(id) ON DELETE SET NULL,
    UNIQUE (normalized_source_name, source_kind)
);

CREATE INDEX IF NOT EXISTS idx_name_mappings_source_name ON name_mappings(source_name);
CREATE INDEX IF NOT EXISTS idx_name_mappings_normalized_source_name ON name_mappings(normalized_source_name);
CREATE INDEX IF NOT EXISTS idx_name_mappings_target_name ON name_mappings(target_name);
CREATE INDEX IF NOT EXISTS idx_name_mappings_target_person_id ON name_mappings(target_photos_person_id);
CREATE INDEX IF NOT EXISTS idx_name_mappings_enabled ON name_mappings(enabled);

CREATE TABLE IF NOT EXISTS face_suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suppression_key TEXT NOT NULL UNIQUE,
    suppression_type TEXT NOT NULL CHECK (suppression_type IN ('metadata_face', 'metadata_name', 'photos_face', 'photos_person', 'file', 'region', 'manual')),
    scope TEXT NOT NULL DEFAULT 'candidate' CHECK (scope IN ('candidate', 'scan', 'ui', 'all')),
    file_id INTEGER,
    metadata_face_id INTEGER,
    photos_face_id INTEGER,
    photos_person_id INTEGER,
    normalized_name TEXT,
    region_fingerprint TEXT,
    reason TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (metadata_face_id) REFERENCES metadata_faces(id) ON DELETE CASCADE,
    FOREIGN KEY (photos_face_id) REFERENCES photos_faces(id) ON DELETE CASCADE,
    FOREIGN KEY (photos_person_id) REFERENCES photos_people(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_face_suppressions_type ON face_suppressions(suppression_type);
CREATE INDEX IF NOT EXISTS idx_face_suppressions_enabled ON face_suppressions(enabled);
CREATE INDEX IF NOT EXISTS idx_face_suppressions_metadata_face_id ON face_suppressions(metadata_face_id);
CREATE INDEX IF NOT EXISTS idx_face_suppressions_photos_face_id ON face_suppressions(photos_face_id);
CREATE INDEX IF NOT EXISTS idx_face_suppressions_normalized_name ON face_suppressions(normalized_name);
CREATE INDEX IF NOT EXISTS idx_face_suppressions_region_fingerprint ON face_suppressions(region_fingerprint);

CREATE TABLE IF NOT EXISTS face_match_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_face_id INTEGER NOT NULL,
    photos_person_id INTEGER,
    photos_face_id INTEGER,
    match_type TEXT NOT NULL CHECK (match_type IN ('name', 'mapping', 'region', 'fingerprint', 'manual', 'combined')),
    score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'rejected', 'suppressed', 'stale')),
    explanation TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (metadata_face_id) REFERENCES metadata_faces(id) ON DELETE CASCADE,
    FOREIGN KEY (photos_person_id) REFERENCES photos_people(id) ON DELETE CASCADE,
    FOREIGN KEY (photos_face_id) REFERENCES photos_faces(id) ON DELETE CASCADE,
    UNIQUE (metadata_face_id, photos_person_id, photos_face_id, match_type)
);

CREATE INDEX IF NOT EXISTS idx_face_match_candidates_metadata_face_id ON face_match_candidates(metadata_face_id);
CREATE INDEX IF NOT EXISTS idx_face_match_candidates_photos_person_id ON face_match_candidates(photos_person_id);
CREATE INDEX IF NOT EXISTS idx_face_match_candidates_status ON face_match_candidates(status);
CREATE INDEX IF NOT EXISTS idx_face_match_candidates_score ON face_match_candidates(score);

CREATE TABLE IF NOT EXISTS face_assignment_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_face_id INTEGER,
    photos_face_id INTEGER,
    photos_person_id INTEGER,
    action_type TEXT NOT NULL CHECK (action_type IN ('assign_existing', 'create_person', 'rename_person', 'delete_metadata_face', 'suppress_face', 'unsuppress_face', 'skip')),
    action_status TEXT NOT NULL DEFAULT 'pending' CHECK (action_status IN ('pending', 'running', 'done', 'failed', 'rolled_back')),
    requested_name TEXT,
    previous_value TEXT,
    new_value TEXT,
    request_payload_json TEXT,
    response_payload_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (metadata_face_id) REFERENCES metadata_faces(id) ON DELETE SET NULL,
    FOREIGN KEY (photos_face_id) REFERENCES photos_faces(id) ON DELETE SET NULL,
    FOREIGN KEY (photos_person_id) REFERENCES photos_people(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_face_assignment_actions_metadata_face_id ON face_assignment_actions(metadata_face_id);
CREATE INDEX IF NOT EXISTS idx_face_assignment_actions_photos_person_id ON face_assignment_actions(photos_person_id);
CREATE INDEX IF NOT EXISTS idx_face_assignment_actions_status ON face_assignment_actions(action_status);
CREATE INDEX IF NOT EXISTS idx_face_assignment_actions_created_at ON face_assignment_actions(created_at);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL CHECK (run_type IN ('full', 'incremental', 'file', 'photos_people', 'metadata_only', 'normalization')),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    root_path TEXT,
    files_seen INTEGER NOT NULL DEFAULT 0 CHECK (files_seen >= 0),
    files_scanned INTEGER NOT NULL DEFAULT 0 CHECK (files_scanned >= 0),
    metadata_faces_found INTEGER NOT NULL DEFAULT 0 CHECK (metadata_faces_found >= 0),
    photos_people_seen INTEGER NOT NULL DEFAULT 0 CHECK (photos_people_seen >= 0),
    photos_faces_seen INTEGER NOT NULL DEFAULT 0 CHECK (photos_faces_seen >= 0),
    candidates_created INTEGER NOT NULL DEFAULT 0 CHECK (candidates_created >= 0),
    suppressions_applied INTEGER NOT NULL DEFAULT 0 CHECK (suppressions_applied >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_runs_status ON scan_runs(status);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started_at ON scan_runs(started_at);

CREATE TABLE IF NOT EXISTS scan_run_files (
    scan_run_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'seen' CHECK (status IN ('seen', 'scanned', 'skipped', 'warning', 'error', 'missing')),
    message TEXT,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (scan_run_id, file_id),
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scan_run_files_file_id ON scan_run_files(file_id);
CREATE INDEX IF NOT EXISTS idx_scan_run_files_status ON scan_run_files(status);

CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('debug', 'info', 'warning', 'error')),
    entity_type TEXT,
    entity_id INTEGER,
    message TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_operation_log_operation_type ON operation_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_operation_log_severity ON operation_log(severity);
CREATE INDEX IF NOT EXISTS idx_operation_log_entity ON operation_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_created_at ON operation_log(created_at);

CREATE VIEW IF NOT EXISTS active_name_mappings AS
SELECT *
FROM name_mappings
WHERE enabled = 1;

CREATE VIEW IF NOT EXISTS active_face_suppressions AS
SELECT *
FROM face_suppressions
WHERE enabled = 1;

CREATE VIEW IF NOT EXISTS open_face_candidates AS
SELECT
    c.id AS candidate_id,
    c.metadata_face_id,
    mf.file_id,
    f.path AS file_path,
    mf.face_name AS metadata_face_name,
    mf.normalized_name AS metadata_normalized_name,
    c.photos_person_id,
    pp.photos_person_id AS external_photos_person_id,
    pp.display_name AS photos_person_name,
    c.photos_face_id,
    pf.photos_face_id AS external_photos_face_id,
    c.match_type,
    c.score,
    c.status,
    c.explanation,
    c.created_at,
    c.updated_at
FROM face_match_candidates c
JOIN metadata_faces mf ON mf.id = c.metadata_face_id
JOIN files f ON f.id = mf.file_id
LEFT JOIN photos_people pp ON pp.id = c.photos_person_id
LEFT JOIN photos_faces pf ON pf.id = c.photos_face_id
WHERE c.status = 'open'
  AND mf.is_deleted = 0
  AND NOT EXISTS (
      SELECT 1
      FROM face_suppressions s
      WHERE s.enabled = 1
        AND (
            s.metadata_face_id = mf.id
            OR (s.normalized_name IS NOT NULL AND s.normalized_name = mf.normalized_name)
            OR (s.region_fingerprint IS NOT NULL AND s.region_fingerprint = mf.region_fingerprint)
            OR s.file_id = mf.file_id
        )
  );

CREATE TRIGGER IF NOT EXISTS trg_app_state_updated_at
AFTER UPDATE ON app_state
FOR EACH ROW
BEGIN
    UPDATE app_state SET updated_at = CURRENT_TIMESTAMP WHERE key = OLD.key;
END;

CREATE TRIGGER IF NOT EXISTS trg_scan_roots_updated_at
AFTER UPDATE ON scan_roots
FOR EACH ROW
BEGIN
    UPDATE scan_roots SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_files_updated_at
AFTER UPDATE ON files
FOR EACH ROW
BEGIN
    UPDATE files SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_file_metadata_cache_updated_at
AFTER UPDATE ON file_metadata_cache
FOR EACH ROW
BEGIN
    UPDATE file_metadata_cache SET updated_at = CURRENT_TIMESTAMP WHERE file_id = OLD.file_id AND cache_key = OLD.cache_key;
END;

CREATE TRIGGER IF NOT EXISTS trg_metadata_faces_updated_at
AFTER UPDATE ON metadata_faces
FOR EACH ROW
BEGIN
    UPDATE metadata_faces SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_photos_people_updated_at
AFTER UPDATE ON photos_people
FOR EACH ROW
BEGIN
    UPDATE photos_people SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_photos_faces_updated_at
AFTER UPDATE ON photos_faces
FOR EACH ROW
BEGIN
    UPDATE photos_faces SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_name_mappings_updated_at
AFTER UPDATE ON name_mappings
FOR EACH ROW
BEGIN
    UPDATE name_mappings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_face_suppressions_updated_at
AFTER UPDATE ON face_suppressions
FOR EACH ROW
BEGIN
    UPDATE face_suppressions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_face_match_candidates_updated_at
AFTER UPDATE ON face_match_candidates
FOR EACH ROW
BEGIN
    UPDATE face_match_candidates SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_face_assignment_actions_updated_at
AFTER UPDATE ON face_assignment_actions
FOR EACH ROW
BEGIN
    UPDATE face_assignment_actions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

INSERT OR IGNORE INTO schema_migrations (version, name, checksum)
VALUES (1, 'initial_sqlite_schema', NULL);

PRAGMA user_version = 1;

COMMIT;
