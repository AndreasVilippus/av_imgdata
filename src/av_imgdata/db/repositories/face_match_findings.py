import json
from typing import Any, Dict

from ..connection import Database


class FaceMatchFindingsRepository:
    """SQLite persistence for the single active face-match findings list."""

    _CANONICAL_KEYS = {
        "job_id",
        "status",
        "action",
        "shared_folder",
        "auto",
        "save_only",
        "transferred_count",
        "count",
        "started_at",
        "finished_at",
        "last_updated_at",
        "entries",
    }

    def __init__(self, database: Database):
        self.database = database

    def read(self, *, include_entries: bool = True) -> Dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM face_match_findings WHERE id = 1"
            ).fetchone()
            if not row:
                return {}
            entry_rows = (
                connection.execute(
                    """
                    SELECT entry_json
                    FROM face_match_finding_entries
                    WHERE finding_id = 1
                    ORDER BY position
                    """
                ).fetchall()
                if include_entries
                else []
            )

        try:
            payload = json.loads(str(row["metadata_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update(
            {
                "job_id": str(row["job_id"] or ""),
                "status": str(row["status"] or ""),
                "action": str(row["action"] or ""),
                "shared_folder": str(row["shared_folder"] or ""),
                "auto": bool(row["auto"]),
                "save_only": bool(row["save_only"]),
                "transferred_count": int(row["transferred_count"] or 0),
                "count": int(row["entry_count"] or 0),
                "started_at": str(row["started_at"] or ""),
                "finished_at": str(row["finished_at"] or ""),
                "last_updated_at": str(row["last_updated_at"] or ""),
            }
        )
        if include_entries:
            entries = []
            for entry_row in entry_rows:
                try:
                    entry = json.loads(str(entry_row["entry_json"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
            payload["entries"] = entries
            payload["count"] = len(entries)
        return payload

    def write(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        normalized_entries = [dict(entry) for entry in entries if isinstance(entry, dict)]
        metadata = {
            key: value
            for key, value in payload.items()
            if key not in self._CANONICAL_KEYS
        }
        parameters = (
            str(payload.get("job_id") or ""),
            str(payload.get("status") or ""),
            str(payload.get("action") or ""),
            str(payload.get("shared_folder") or ""),
            int(bool(payload.get("auto"))),
            int(bool(payload.get("save_only"))),
            max(0, int(payload.get("transferred_count") or 0)),
            len(normalized_entries),
            str(payload.get("started_at") or ""),
            str(payload.get("finished_at") or ""),
            str(payload.get("last_updated_at") or ""),
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO face_match_findings(
                    id, job_id, status, action, shared_folder, auto, save_only,
                    transferred_count, entry_count, started_at, finished_at,
                    last_updated_at, metadata_json
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    job_id = excluded.job_id,
                    status = excluded.status,
                    action = excluded.action,
                    shared_folder = excluded.shared_folder,
                    auto = excluded.auto,
                    save_only = excluded.save_only,
                    transferred_count = excluded.transferred_count,
                    entry_count = excluded.entry_count,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    last_updated_at = excluded.last_updated_at,
                    metadata_json = excluded.metadata_json
                """,
                parameters,
            )
            connection.execute(
                "DELETE FROM face_match_finding_entries WHERE finding_id = 1"
            )
            connection.executemany(
                """
                INSERT INTO face_match_finding_entries(
                    finding_id, position, action, image_path, source_name, entry_json
                )
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        position,
                        str(entry.get("action") or payload.get("action") or ""),
                        str(entry.get("image_path") or ""),
                        str(entry.get("source_name") or ""),
                        json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
                    )
                    for position, entry in enumerate(normalized_entries)
                ],
            )
        return True

    def delete(self) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute("DELETE FROM face_match_findings WHERE id = 1")
        return cursor.rowcount > 0
