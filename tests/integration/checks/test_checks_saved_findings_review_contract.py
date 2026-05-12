import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


def _service():
    return ImgDataService(SessionManager())


def test_saved_name_conflict_entry_materializes_when_live_review_returns_empty():
    service = _service()

    def empty_core(**_kwargs):
        return {
            "entry": None,
            "item": None,
            "auto_applied_count": 0,
        }

    service._resolveChecksReviewEntryCore = empty_core

    entry = {
        "review_type": "name_conflicts",
        "image_path": "/volume1/photo/tests/conflict.jpg",
        "left_face_signature": {
            "source": "embedded_xmp_exiftool",
            "source_format": "ACD",
            "name": "Person A",
            "x": 0.1,
            "y": 0.2,
            "w": 0.3,
            "h": 0.4,
        },
        "right_face_signature": {
            "source": "embedded_xmp_exiftool",
            "source_format": "MWG_REGIONS",
            "name": "Person B",
            "x": 0.1,
            "y": 0.2,
            "w": 0.3,
            "h": 0.4,
        },
    }

    resolved = service._resolveChecksReviewEntry(entry=entry)

    assert resolved["entry"] is entry
    assert resolved["from_stored_finding"] is True
    assert resolved["item"]["review_type"] == "name_conflicts"
    assert resolved["item"]["image_path"] == entry["image_path"]
    assert resolved["item"]["left_name"] == "Person A"
    assert resolved["item"]["right_name"] == "Person B"
    assert resolved["item"]["left_face_target"]["source_format"] == "ACD"
    assert resolved["item"]["right_face_target"]["source_format"] == "MWG_REGIONS"


def test_saved_pair_review_fallback_covers_other_pair_checks():
    service = _service()
    service._resolveChecksReviewEntryCore = lambda **_kwargs: {
        "entry": None,
        "item": None,
        "auto_applied_count": 0,
    }

    for review_type in ("duplicate_faces", "position_deviations"):
        entry = {
            "review_type": review_type,
            "image_path": f"/volume1/photo/tests/{review_type}.jpg",
            "left_face_signature": {"source_format": "ACD", "name": "Person A", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
            "right_face_signature": {"source_format": "MICROSOFT", "name": "Person A", "x": 0.2, "y": 0.3, "w": 0.3, "h": 0.4},
        }

        resolved = service._resolveChecksReviewEntry(entry=entry)

        assert resolved["entry"] is entry
        assert resolved["item"]["review_type"] == review_type
        assert resolved["item"]["from_stored_finding"] is True


def test_saved_review_fallback_does_not_reopen_auto_applied_results():
    service = _service()
    service._resolveChecksReviewEntryCore = lambda **_kwargs: {
        "entry": None,
        "item": None,
        "auto_applied_count": 1,
    }

    entry = {
        "review_type": "name_conflicts",
        "image_path": "/volume1/photo/tests/conflict.jpg",
        "left_face_signature": {"source_format": "ACD", "name": "Person A"},
        "right_face_signature": {"source_format": "MICROSOFT", "name": "Person B"},
    }

    resolved = service._resolveChecksReviewEntry(entry=entry)

    assert resolved["entry"] is None
    assert resolved["item"] is None
    assert resolved["auto_applied_count"] == 1
