from models.bbox import BoundingBox
from dataclasses import dataclass

@dataclass
class FileFace:
    name: str
    bbox: BoundingBox
    source: str
    source_format: str