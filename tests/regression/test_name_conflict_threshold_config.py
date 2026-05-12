import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from handler.file_handler import FileHandler
from services.config_service import ConfigService


def _face(name, source_format, x, y, w=0.2, h=0.2, source="metadata"):
    return {
        "name": name,
        "source": source,
        "source_format": source_format,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
    }


def test_name_conflict_overlap_threshold_is_normalized():
    config = ConfigService.normalizeConfig({
        "analysis": {
            "CHECKS": {
                "NAME_CONFLICT_OVERLAP_THRESHOLD": 2.0,
                "NAME_CONFLICT_MIN_BEST_MATCH_MARGIN": -1,
                "NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH": True,
            }
        }
    })
    checks = config["analysis"]["CHECKS"]

    assert checks["NAME_CONFLICT_OVERLAP_THRESHOLD"] == 1.0
    assert checks["NAME_CONFLICT_MIN_BEST_MATCH_MARGIN"] == 0.0
    assert checks["NAME_CONFLICT_REQUIRE_MUTUAL_BEST_MATCH"] is True


def test_high_name_conflict_threshold_reduces_pair_photo_false_positive():
    handler = FileHandler()
    left = _face("Max", "ACD", 0.50, 0.50)
    right = _face("Moritz", "MICROSOFT", 0.57, 0.50)

    assert handler._countOverlappingNameConflicts(
        [left, right],
        overlap_threshold=0.5,
        require_mutual_best_match=False,
    ) == 1

    assert handler._countOverlappingNameConflicts(
        [left, right],
        overlap_threshold=0.85,
        require_mutual_best_match=False,
    ) == 0


def test_mutual_best_match_ignores_non_best_overlapping_candidate():
    handler = FileHandler()

    acd_max = _face("Max", "ACD", 0.50, 0.50)
    ms_max = _face("Max", "MICROSOFT", 0.50, 0.50)
    ms_moritz = _face("Moritz", "MICROSOFT", 0.57, 0.50)

    assert handler._countOverlappingNameConflicts(
        [acd_max, ms_max, ms_moritz],
        overlap_threshold=0.5,
        require_mutual_best_match=False,
    ) == 1

    assert handler._countOverlappingNameConflicts(
        [acd_max, ms_max, ms_moritz],
        overlap_threshold=0.5,
        require_mutual_best_match=True,
    ) == 0
