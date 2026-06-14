from math import hypot
from typing import Dict

from models.bbox import BoundingBox
from services.face_matcher import compute


def frame_metrics(source: BoundingBox, detected: BoundingBox) -> Dict[str, float]:
    source_center = source.center()
    detected_center = detected.center()
    max_area = max(source.area(), detected.area(), 1e-12)
    return {
        "iou": compute(source, detected),
        "center_delta": hypot(
            source_center[0] - detected_center[0],
            source_center[1] - detected_center[1],
        ),
        "size_delta": abs(source.area() - detected.area()) / max_area,
    }


def match_decision(metrics: Dict[str, float]) -> str:
    iou = float(metrics.get("iou") or 0.0)
    center_delta = float(metrics.get("center_delta") or 0.0)
    size_delta = float(metrics.get("size_delta") or 0.0)
    if iou >= 0.65 and center_delta <= 0.08 and size_delta <= 0.50:
        return "safe"
    if iou >= 0.30:
        return "review"
    return "conflict"
