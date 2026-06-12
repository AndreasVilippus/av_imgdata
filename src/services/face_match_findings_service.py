from typing import Any, Dict

from av_imgdata.db.connection import Database
from av_imgdata.db.repositories.face_match_findings import FaceMatchFindingsRepository


class FaceMatchFindingsService:
    """SQLite-backed active face-match findings."""

    def __init__(self, database: Database):
        self._database = database
        self._repository = FaceMatchFindingsRepository(database)

    def read(self) -> Dict[str, Any]:
        return self._repository.read(include_entries=True)

    def read_status(self) -> Dict[str, Any]:
        return self._repository.read(include_entries=False)

    def write(self, payload: Dict[str, Any]) -> bool:
        return self._repository.write(payload)

    def delete(self) -> bool:
        return self._repository.delete()
