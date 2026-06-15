from typing import Any, Dict

from models.bbox import BoundingBox
from services.bbox_normalizer import scale_bbox_about_center


PROFILES: Dict[str, Dict[str, float]] = {
    "tight": {"scale_x": 1.00, "scale_y": 1.00, "shift_y": 0.00},
    "normal": {"scale_x": 1.15, "scale_y": 1.25, "shift_y": -0.03},
    "photos_compatible": {"scale_x": 1.20, "scale_y": 1.35, "shift_y": -0.05},
    "acdsee_compatible": {"scale_x": 1.10, "scale_y": 1.20, "shift_y": -0.03},
}
STRATEGIES = {
    "insightface_exact",
    "insightface_scaled",
    "keep_existing_center_scale_size",
    "correct_only_if_deviation",
    "average_sources",
    "largest_plausible",
    "custom_margin",
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


def normalize_strategy(strategy: Any) -> str:
    normalized = str(strategy or "insightface_scaled").strip().lower()
    return normalized if normalized in STRATEGIES else "insightface_scaled"


def validate_target_frame(box: BoundingBox) -> bool:
    return (
        box.width() > 0
        and box.height() > 0
        and 0 <= box.x1 < box.x2 <= 1
        and 0 <= box.y1 < box.y2 <= 1
    )


def build_target_frame(
    source_frame: BoundingBox,
    insight_frame: BoundingBox,
    *,
    strategy: Any = "insightface_scaled",
    profile: Any = "normal",
) -> BoundingBox:
    normalized = normalize_strategy(strategy)
    if normalized == "insightface_exact":
        return insight_frame
    if normalized in {"insightface_scaled", "custom_margin"}:
        return target_frame(insight_frame, profile=profile)
    if normalized == "keep_existing_center_scale_size":
        scaled = target_frame(insight_frame, profile=profile)
        center_x, center_y = source_frame.center()
        return scale_bbox_about_center(
            BoundingBox(
                center_x - (scaled.width() / 2),
                center_y - (scaled.height() / 2),
                center_x + (scaled.width() / 2),
                center_y + (scaled.height() / 2),
            )
        )
    if normalized == "average_sources":
        return BoundingBox(
            x1=(source_frame.x1 + insight_frame.x1) / 2,
            y1=(source_frame.y1 + insight_frame.y1) / 2,
            x2=(source_frame.x2 + insight_frame.x2) / 2,
            y2=(source_frame.y2 + insight_frame.y2) / 2,
        )
    if normalized == "largest_plausible":
        return source_frame if source_frame.area() >= insight_frame.area() else insight_frame
    if normalized == "correct_only_if_deviation":
        from services.face_matcher import compute
        return source_frame if compute(source_frame, insight_frame) >= 0.65 else target_frame(insight_frame, profile=profile)
    return target_frame(insight_frame, profile=profile)
