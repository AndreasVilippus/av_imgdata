from models.bbox import BoundingBox
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class PhotosFace:
    face_id: int
    person_id: int
    bbox: BoundingBox

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_id": self.face_id,
            "person_id": self.person_id,
            "bbox": {
                "x1": self.bbox.x1,
                "y1": self.bbox.y1,
                "x2": self.bbox.x2,
                "y2": self.bbox.y2,
            },
        }
