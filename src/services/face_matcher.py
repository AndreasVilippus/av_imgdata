from typing import Dict, List, Tuple

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

    @staticmethod
    def _sourceKey(face: FileFace) -> Tuple[str, str]:
        return (
            str(face.source or "").strip(),
            str(face.source_format or "").strip(),
        )

    def match(
        self,
        photos_faces: List[PhotosFace],
        file_faces: List[FileFace]
    ) -> List[Dict[str, object]]:

        candidates_by_source: Dict[Tuple[str, str], List[Dict[str, object]]] = {}

        for p in photos_faces:
            for file_index, x in enumerate(file_faces):
                score = compute(p.bbox, x.bbox)

                if score < self.iou_threshold:
                    continue

                source_key = self._sourceKey(x)
                candidates_by_source.setdefault(source_key, []).append({
                    "face_id": p.face_id,
                    "person_id": p.person_id,
                    "file_face_index": file_index,
                    "file_name": x.name,
                    "source": x.source,
                    "source_format": x.source_format,
                    "iou": score
                })

        matches: List[Dict[str, object]] = []

        for source_key in sorted(candidates_by_source.keys()):
            candidates = candidates_by_source[source_key]
            candidates.sort(
                key=lambda item: (
                    -float(item.get("iou") or 0.0),
                    int(item.get("face_id") or 0),
                    int(item.get("file_face_index") or 0),
                )
            )

            used_photos_face_ids = set()
            used_file_face_indices = set()

            for candidate in candidates:
                face_id = candidate["face_id"]
                file_index = candidate["file_face_index"]

                if face_id in used_photos_face_ids:
                    continue
                if file_index in used_file_face_indices:
                    continue

                matches.append(candidate)
                used_photos_face_ids.add(face_id)
                used_file_face_indices.add(file_index)

        return matches
