from pathlib import Path

from .connection import Database
from .migrations import (
    migrate_legacy_findings,
    migrate_legacy_name_mappings,
    migrate_runtime_persistence,
)
from .path import get_db_path, get_pkgvar_dir


def initialize_runtime_database() -> Path:
    database = Database(str(get_db_path()))
    migrate_legacy_name_mappings(database, get_pkgvar_dir() / "name_mappings.json")
    migrate_runtime_persistence(database, get_pkgvar_dir())
    migrate_legacy_findings(database, get_pkgvar_dir())
    return database.path


def main() -> int:
    path = initialize_runtime_database()
    print(f"SQLite runtime database ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
