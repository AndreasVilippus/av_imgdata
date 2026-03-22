from models.bbox import BoundingBox
from dataclasses import dataclass

@dataclass
class PhotosFace:
    face_id: int
    person_id: int
    bbox: BoundingBox