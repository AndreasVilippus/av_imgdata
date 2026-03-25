from models.bbox import BoundingBox
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class FileFace:
    name: str
    bbox: BoundingBox
    source: str
    source_format: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "source_format": self.source_format,
            "bbox": {
                "x1": self.bbox.x1,
                "y1": self.bbox.y1,
                "x2": self.bbox.x2,
                "y2": self.bbox.y2,
            },
        }
