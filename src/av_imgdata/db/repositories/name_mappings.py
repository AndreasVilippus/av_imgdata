from typing import Any, Dict, Iterable, List, Optional

from ..connection import Database


def normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


class NameMappingRepository:
    SOURCE_KINDS = {"metadata", "photos", "manual", "import"}

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row_to_mapping(row: Any) -> Dict[str, Any]:
        return {
            "source_name": str(row["source_name"]),
            "target_name": str(row["target_name"]),
        }

    def list_mappings(self) -> List[Dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT source_name, target_name
                FROM active_name_mappings
                ORDER BY id
                """
            ).fetchall()
        return [self._row_to_mapping(row) for row in rows]

    def list_page(self, *, search: str = "", page: int = 1, page_size: int = 25) -> Dict[str, Any]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(100, int(page_size)))
        search_value = str(search or "").strip()
        where_sql = ""
        parameters: List[Any] = []
        if search_value:
            where_sql = """
                WHERE source_name LIKE ? COLLATE NOCASE
                   OR target_name LIKE ? COLLATE NOCASE
                   OR source_kind LIKE ? COLLATE NOCASE
                   OR mapping_kind LIKE ? COLLATE NOCASE
            """
            search_pattern = f"%{search_value}%"
            parameters.extend([search_pattern] * 4)
        with self.database.read() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM name_mappings {where_sql}",
                parameters,
            ).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    source_name,
                    target_name,
                    source_kind,
                    mapping_kind,
                    enabled,
                    priority,
                    note,
                    created_at,
                    updated_at
                FROM name_mappings
                {where_sql}
                ORDER BY normalized_source_name, id
                LIMIT ? OFFSET ?
                """,
                [*parameters, normalized_page_size, (normalized_page - 1) * normalized_page_size],
            ).fetchall()
        return {
            "entries": [{key: row[key] for key in row.keys()} for row in rows],
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": total,
        }

    def delete_mapping(self, mapping_id: int) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM name_mappings WHERE id = ?",
                (int(mapping_id),),
            )
        return cursor.rowcount > 0

    def clear_mappings(self) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute("DELETE FROM name_mappings")
        return max(0, int(cursor.rowcount or 0))

    def update_mapping_target(self, mapping_id: int, target_name: str) -> bool:
        target_value = str(target_name or "").strip()
        normalized_target = normalize_name(target_value)
        if not normalized_target:
            return False
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE name_mappings
                SET target_name = ?, normalized_target_name = ?, enabled = 1
                WHERE id = ?
                """,
                (target_value, normalized_target, int(mapping_id)),
            )
        return cursor.rowcount > 0

    def find_mapping(self, source_name: str, source_kind: str = "metadata") -> Optional[Dict[str, Any]]:
        normalized_source = normalize_name(source_name)
        if not normalized_source:
            return None
        with self.database.read() as connection:
            row = connection.execute(
                """
                SELECT source_name, target_name
                FROM active_name_mappings
                WHERE normalized_source_name = ? AND source_kind = ?
                """,
                (normalized_source, source_kind),
            ).fetchone()
        return self._row_to_mapping(row) if row else None

    def upsert_mapping(
        self,
        source_name: str,
        target_name: str,
        source_kind: str = "metadata",
        *,
        connection: Any = None,
    ) -> bool:
        source_value = str(source_name or "").strip()
        target_value = str(target_name or "").strip()
        normalized_source = normalize_name(source_value)
        normalized_target = normalize_name(target_value)
        if not normalized_source or not normalized_target:
            return False
        normalized_source_kind = str(source_kind or "metadata").strip().lower()
        if normalized_source_kind not in self.SOURCE_KINDS:
            normalized_source_kind = "metadata"
        parameters = (
            source_value,
            normalized_source,
            target_value,
            normalized_target,
            normalized_source_kind,
        )
        sql = """
            INSERT INTO name_mappings(
                source_name,
                normalized_source_name,
                target_name,
                normalized_target_name,
                source_kind
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(normalized_source_name, source_kind) DO UPDATE SET
                source_name = excluded.source_name,
                target_name = excluded.target_name,
                normalized_target_name = excluded.normalized_target_name,
                enabled = 1
        """
        if connection is not None:
            connection.execute(sql, parameters)
            return True
        with self.database.transaction() as own_connection:
            own_connection.execute(sql, parameters)
        return True

    def upsert_many(self, mappings: Iterable[Dict[str, Any]], *, connection: Any = None) -> int:
        count = 0
        if connection is not None:
            for mapping in mappings:
                if self.upsert_mapping(
                    mapping.get("source_name"),
                    mapping.get("target_name"),
                    str(mapping.get("source_kind") or "metadata"),
                    connection=connection,
                ):
                    count += 1
            return count
        with self.database.transaction() as own_connection:
            return self.upsert_many(mappings, connection=own_connection)
