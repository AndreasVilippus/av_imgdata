import json
from typing import Any, Dict, List

from ..connection import Database


class PersistedFindingsRepository:
    def __init__(self, database: Database):
        self.database = database

    def read(self, finding_type: str, *, include_entries: bool = True) -> Dict[str, Any]:
        normalized = str(finding_type or "").strip().lower()
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT payload_json, entry_count FROM persisted_findings WHERE finding_type = ?",
                (normalized,),
            ).fetchone()
            if not row:
                return {}
            entry_rows = connection.execute(
                """
                SELECT entry_json FROM persisted_finding_entries
                WHERE finding_type = ? ORDER BY position
                """,
                (normalized,),
            ).fetchall() if include_entries else []
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["count"] = int(row["entry_count"] or 0)
        if include_entries:
            entries: List[Dict[str, Any]] = []
            for entry_row in entry_rows:
                try:
                    entry = json.loads(str(entry_row["entry_json"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
            payload["entries"] = entries
        return payload

    def write(self, finding_type: str, payload: Dict[str, Any]) -> bool:
        normalized = str(finding_type or "").strip().lower()
        if not normalized or not isinstance(payload, dict):
            return False
        entries = [dict(entry) for entry in payload.get("entries", []) if isinstance(entry, dict)]
        metadata = {key: value for key, value in payload.items() if key not in {"entries", "count"}}
        paths = payload.get("paths") if isinstance(payload.get("paths"), list) else []
        item_count = len(entries) if entries else max(0, int(payload.get("count") or len(paths)))
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO persisted_findings(
                    finding_type, payload_json, entry_count, status, action,
                    check_type, shared_folder, save_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_type) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    entry_count = excluded.entry_count,
                    status = excluded.status,
                    action = excluded.action,
                    check_type = excluded.check_type,
                    shared_folder = excluded.shared_folder,
                    save_only = excluded.save_only,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized,
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                    item_count,
                    str(payload.get("status") or ""),
                    str(payload.get("action") or ""),
                    str(payload.get("check_type") or ""),
                    str(payload.get("shared_folder") or ""),
                    int(bool(payload.get("save_only"))),
                ),
            )
            connection.execute(
                "DELETE FROM persisted_finding_entries WHERE finding_type = ?",
                (normalized,),
            )
            connection.executemany(
                """
                INSERT INTO persisted_finding_entries(
                    finding_type, position, image_path, source_name, entry_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        normalized,
                        position,
                        str(entry.get("image_path") or ""),
                        str(entry.get("source_name") or ""),
                        json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
                    )
                    for position, entry in enumerate(entries)
                ],
            )
        return True

    def append(self, finding_type: str, entries: List[Dict[str, Any]]) -> bool:
        payload = self.read(finding_type)
        existing = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        payload["entries"] = [*existing, *[dict(entry) for entry in entries if isinstance(entry, dict)]]
        return self.write(finding_type, payload)

    def delete(self, finding_type: str) -> bool:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM persisted_findings WHERE finding_type = ?",
                (str(finding_type or "").strip().lower(),),
            )
        return True
