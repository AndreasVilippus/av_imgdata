from typing import Any, Dict

from models.bbox import BoundingBox
from services.bbox_normalizer import scale_bbox_about_center


PROFILES: Dict[str, Dict[str, float]] = {
    "tight": {"scale_x": 1.00, "scale_y": 1.00, "shift_y": 0.00},
    "normal": {"scale_x": 1.15, "scale_y": 1.25, "shift_y": -0.03},
    "photos_compatible": {"scale_x": 1.20, "scale_y": 1.35, "shift_y": -0.05},
    "acdsee_compatible": {"scale_x": 1.10, "scale_y": 1.20, "shift_y": -0.03},
}


def normalize_profile(profile: Any) -> str:
    normalized = str(profile or "normal").strip().lower()
    return normalized if normalized in PROFILES else "normal"


def target_frame(detected: BoundingBox, *, profile: Any = "normal") -> BoundingBox:
    values = PROFILES[normalize_profile(profile)]
    return scale_bbox_about_center(
        detected,
        scale_x=values["scale_x"],
        scale_y=values["scale_y"],
        shift_y=values["shift_y"],
    )
