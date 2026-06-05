import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "av_imgdata" / "db" / "schema.sql"


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _load_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_schema_applies_idempotently(tmp_path):
    con = _connect(tmp_path / "imgdata.sqlite3")
    schema = _load_schema()

    con.executescript(schema)
    con.executescript(schema)

    user_version = con.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == 1

    migration = con.execute(
        "SELECT name FROM schema_migrations WHERE version = 1"
    ).fetchone()
    assert migration[0] == "initial_sqlite_schema"


def test_core_face_candidate_and_suppression_flow(tmp_path):
    con = _connect(tmp_path / "imgdata.sqlite3")
    con.executescript(_load_schema())

    con.execute("INSERT INTO scan_roots(root_path) VALUES (?)", ("/photos",))
    scan_root_id = con.execute("SELECT id FROM scan_roots").fetchone()[0]

    con.execute(
        """
        INSERT INTO files(scan_root_id, path, filename, content_hash)
        VALUES (?, ?, ?, ?)
        """,
        (scan_root_id, "/photos/a.jpg", "a.jpg", "hash-a"),
    )
    file_id = con.execute("SELECT id FROM files").fetchone()[0]

    con.execute(
        """
        INSERT INTO metadata_faces(
            file_id,
            source_schema,
            source_index,
            face_name,
            normalized_name,
            region_fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (file_id, "mwg_regions", 0, "Max", "max", "region-a"),
    )
    metadata_face_id = con.execute("SELECT id FROM metadata_faces").fetchone()[0]

    con.execute(
        """
        INSERT INTO photos_people(photos_person_id, display_name, normalized_name)
        VALUES (?, ?, ?)
        """,
        ("photos-person-1", "Max", "max"),
    )
    photos_person_id = con.execute("SELECT id FROM photos_people").fetchone()[0]

    con.execute(
        """
        INSERT INTO face_match_candidates(
            metadata_face_id,
            photos_person_id,
            match_type,
            score
        )
        VALUES (?, ?, ?, ?)
        """,
        (metadata_face_id, photos_person_id, "name", 0.95),
    )

    assert con.execute("SELECT COUNT(*) FROM open_face_candidates").fetchone()[0] == 1

    con.execute(
        """
        INSERT INTO face_suppressions(
            suppression_key,
            suppression_type,
            metadata_face_id,
            reason
        )
        VALUES (?, ?, ?, ?)
        """,
        ("metadata-face:region-a", "metadata_face", metadata_face_id, "test suppression"),
    )

    assert con.execute("SELECT COUNT(*) FROM open_face_candidates").fetchone()[0] == 0


def test_constraints_and_cascade_behaviour(tmp_path):
    con = _connect(tmp_path / "imgdata.sqlite3")
    con.executescript(_load_schema())

    con.execute(
        "INSERT INTO files(path, filename) VALUES (?, ?)",
        ("/photos/a.jpg", "a.jpg"),
    )
    file_id = con.execute("SELECT id FROM files").fetchone()[0]

    con.execute(
        """
        INSERT INTO metadata_faces(file_id, source_schema, source_index, face_name)
        VALUES (?, ?, ?, ?)
        """,
        (file_id, "mwg_regions", 0, "Max"),
    )
    metadata_face_id = con.execute("SELECT id FROM metadata_faces").fetchone()[0]

    con.execute(
        """
        INSERT INTO face_suppressions(suppression_key, suppression_type, metadata_face_id)
        VALUES (?, ?, ?)
        """,
        ("metadata-face:duplicate", "metadata_face", metadata_face_id),
    )

    try:
        con.execute(
            """
            INSERT INTO face_suppressions(suppression_key, suppression_type, metadata_face_id)
            VALUES (?, ?, ?)
            """,
            ("metadata-face:duplicate", "metadata_face", metadata_face_id),
        )
        raise AssertionError("duplicate suppression key was accepted")
    except sqlite3.IntegrityError:
        pass

    con.execute("DELETE FROM files WHERE id = ?", (file_id,))

    assert (
        con.execute(
            "SELECT COUNT(*) FROM metadata_faces WHERE id = ?", (metadata_face_id,)
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            "SELECT COUNT(*) FROM face_suppressions WHERE metadata_face_id = ?",
            (metadata_face_id,),
        ).fetchone()[0]
        == 0
    )


def test_name_mapping_upsert_contract(tmp_path):
    con = _connect(tmp_path / "imgdata.sqlite3")
    con.executescript(_load_schema())

    con.execute(
        """
        INSERT INTO name_mappings(
            source_name,
            normalized_source_name,
            target_name,
            normalized_target_name
        )
        VALUES (?, ?, ?, ?)
        """,
        ("Mäx", "mäx", "Max", "max"),
    )

    con.execute(
        """
        INSERT INTO name_mappings(
            source_name,
            normalized_source_name,
            target_name,
            normalized_target_name
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(normalized_source_name, source_kind) DO UPDATE SET
            target_name = excluded.target_name,
            normalized_target_name = excluded.normalized_target_name
        """,
        ("Mäx", "mäx", "Max Mustermann", "max mustermann"),
    )

    row = con.execute(
        "SELECT target_name, normalized_target_name FROM name_mappings WHERE normalized_source_name = ?",
        ("mäx",),
    ).fetchone()

    assert row == ("Max Mustermann", "max mustermann")
