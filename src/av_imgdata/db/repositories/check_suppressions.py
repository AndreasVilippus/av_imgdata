from typing import List

from ..connection import Database


class CheckSuppressionRepository:
    def __init__(self, database: Database):
        self.database = database

    def list_tokens(self, review_type: str) -> List[str]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT token FROM check_suppressions WHERE review_type = ? ORDER BY rowid",
                (str(review_type or "").strip().lower(),),
            ).fetchall()
        return [str(row["token"]) for row in rows]

    def replace(self, review_type: str, tokens: List[str]) -> bool:
        normalized_type = str(review_type or "").strip().lower()
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM check_suppressions WHERE review_type = ?", (normalized_type,))
            connection.executemany(
                "INSERT INTO check_suppressions(review_type, token) VALUES (?, ?)",
                [(normalized_type, token) for token in tokens],
            )
        return True
