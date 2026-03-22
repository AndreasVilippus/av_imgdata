from typing import Dict, List

from models.bbox import BoundingBox
from models.photos_face import PhotosFace
from models.file_face import FileFace


def compute(left: BoundingBox, right: BoundingBox) -> float:
    x_left = max(left.x1, right.x1)
    y_top = max(left.y1, right.y1)
    x_right = min(left.x2, right.x2)
    y_bottom = min(left.y2, right.y2)
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    union = left.area() + right.area() - intersection
    if union <= 0:
        return 0.0
    return intersection / union

class FaceMatcher:

    def __init__(self, iou_threshold: float = 0.6):
        self.iou_threshold = iou_threshold

    def match(
        self,
        photos_faces: List[PhotosFace],
        file_faces: List[FileFace]
    ) -> List[Dict[str, object]]:

        matches = []

        for p in photos_faces:
            for file_index, x in enumerate(file_faces):
                score = compute(p.bbox, x.bbox)

                if score >= self.iou_threshold:
                    matches.append({
                        "face_id": p.face_id,
                        "person_id": p.person_id,
                        "file_face_index": file_index,
                        "file_name": x.name,
                        "source": x.source,
                        "source_format": x.source_format,
                        "iou": score
                    })

        return matches
