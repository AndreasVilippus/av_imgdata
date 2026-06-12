import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Dict, Iterator, Optional, Set

from .path import get_db_path


class DatabaseError(RuntimeError):
    """Controlled package error for SQLite initialization and access failures."""


class Database:
    _initialization_guard = Lock()
    _initialization_locks: Dict[str, Lock] = {}
    _initialized_paths: Set[str] = set()

    def __init__(self, db_path: Optional[str] = None, schema_path: Optional[str] = None):
        self.path = Path(db_path) if db_path else get_db_path()
        self.schema_path = (
            Path(schema_path)
            if schema_path
            else Path(__file__).resolve().with_name("schema.sql")
        )
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            return connection
        except sqlite3.Error as exc:
            raise DatabaseError(f"cannot open SQLite database {self.path}: {exc}") from exc
        except OSError as exc:
            raise DatabaseError(f"cannot prepare SQLite directory {self.path.parent}: {exc}") from exc

    def initialize(self) -> None:
        if self._initialized:
            return
        path_key = str(self.path.resolve())
        with self._initialization_guard:
            if path_key in self._initialized_paths and self.path.exists():
                self._initialized = True
                return
            self._initialized_paths.discard(path_key)
            initialization_lock = self._initialization_locks.setdefault(path_key, Lock())

        with initialization_lock:
            with self._initialization_guard:
                if path_key in self._initialized_paths and self.path.exists():
                    self._initialized = True
                    return
            try:
                schema = self.schema_path.read_text(encoding="utf-8")
                with self.connect() as connection:
                    connection.execute("PRAGMA journal_mode = WAL")
                    connection.executescript(schema)
            except (OSError, sqlite3.Error) as exc:
                raise DatabaseError(f"cannot initialize SQLite database {self.path}: {exc}") from exc
            with self._initialization_guard:
                self._initialized_paths.add(path_key)
            self._initialized = True

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        connection = self.connect()
        try:
            with connection:
                yield connection
        except sqlite3.Error as exc:
            raise DatabaseError(f"SQLite transaction failed for {self.path}: {exc}") from exc
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        connection = self.connect()
        try:
            yield connection
        except sqlite3.Error as exc:
            raise DatabaseError(f"SQLite read failed for {self.path}: {exc}") from exc
        finally:
            connection.close()
