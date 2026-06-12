from av_imgdata.db.connection import Database
from services.face_match_findings_service import FaceMatchFindingsService


def test_face_match_findings_service_writes_and_reads_sqlite(tmp_path):
    service = FaceMatchFindingsService(Database(str(tmp_path / "imgdata.sqlite3")))
    replacement = {
        "status": "running",
        "action": "mark_missing_photos_faces",
        "entries": [{"image_path": "/volume1/photo/sqlite.jpg"}],
    }
    assert service.write(replacement)

    assert service.read()["entries"] == replacement["entries"]
