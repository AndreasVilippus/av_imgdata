import json
from typing import Any, Optional

from ..connection import Database


class AppStateRepository:
    def __init__(self, database: Database):
        self.database = database

    def set(self, key: str, value: Any) -> bool:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return False
        value_type = "json"
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO app_state(key, value, value_type)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    value_type = excluded.value_type
                WHERE app_state.value != excluded.value
                   OR app_state.value_type != excluded.value_type
                """,
                (normalized_key, serialized, value_type),
            )
        return True

    def get(self, key: str, default: Any = None) -> Any:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT value, value_type FROM app_state WHERE key = ?",
                (str(key or "").strip(),),
            ).fetchone()
        if not row:
            return default
        if row["value_type"] == "json":
            try:
                return json.loads(row["value"])
            except (TypeError, ValueError):
                return default
        return row["value"]

    def delete(self, key: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM app_state WHERE key = ?",
                (str(key or "").strip(),),
            )
        return cursor.rowcount > 0
