from typing import Any, Dict, List, Optional

from ..connection import Database


class FaceSuppressionRepository:
    def __init__(self, database: Database):
        self.database = database

    def suppress(
        self,
        suppression_key: str,
        suppression_type: str = "manual",
        *,
        scope: str = "candidate",
        normalized_name: Optional[str] = None,
        region_fingerprint: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> bool:
        key = str(suppression_key or "").strip()
        if not key:
            return False
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO face_suppressions(
                    suppression_key,
                    suppression_type,
                    scope,
                    normalized_name,
                    region_fingerprint,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(suppression_key) DO UPDATE SET
                    suppression_type = excluded.suppression_type,
                    scope = excluded.scope,
                    normalized_name = excluded.normalized_name,
                    region_fingerprint = excluded.region_fingerprint,
                    reason = excluded.reason,
                    enabled = 1
                """,
                (key, suppression_type, scope, normalized_name, region_fingerprint, reason),
            )
        return True

    def unsuppress(self, suppression_key: str) -> bool:
        key = str(suppression_key or "").strip()
        if not key:
            return False
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE face_suppressions SET enabled = 0 WHERE suppression_key = ?",
                (key,),
            )
        return cursor.rowcount > 0

    def is_suppressed(self, suppression_key: str) -> bool:
        key = str(suppression_key or "").strip()
        if not key:
            return False
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT 1 FROM active_face_suppressions WHERE suppression_key = ?",
                (key,),
            ).fetchone()
        return bool(row)

    def list_keys(self, prefix: str = "") -> List[str]:
        normalized_prefix = str(prefix or "")
        with self.database.read() as connection:
            if normalized_prefix:
                rows = connection.execute(
                    """
                    SELECT suppression_key
                    FROM active_face_suppressions
                    WHERE suppression_key LIKE ?
                    ORDER BY id
                    """,
                    (normalized_prefix + "%",),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT suppression_key FROM active_face_suppressions ORDER BY id"
                ).fetchall()
        return [str(row["suppression_key"]) for row in rows]

    def disable_prefix(self, prefix: str) -> int:
        normalized_prefix = str(prefix or "")
        if not normalized_prefix:
            return 0
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE face_suppressions SET enabled = 0 WHERE enabled = 1 AND suppression_key LIKE ?",
                (normalized_prefix + "%",),
            )
        return max(0, int(cursor.rowcount or 0))

    def get(self, suppression_key: str) -> Optional[Dict[str, Any]]:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM active_face_suppressions WHERE suppression_key = ?",
                (str(suppression_key or "").strip(),),
            ).fetchone()
        return dict(row) if row else None
