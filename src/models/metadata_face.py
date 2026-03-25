from dataclasses import dataclass
from typing import Any, Dict, Optional

from models.bbox import BoundingBox
from models.file_face import FileFace


@dataclass
class MetadataFace(FileFace):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    focus_usage: str = ""
    orientation: Optional[int] = None

    @classmethod
    def from_center_box(
        cls,
        *,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        source: str,
        source_format: str,
        focus_usage: str = "",
        orientation: Optional[int] = None,
    ) -> "MetadataFace":
        bbox = BoundingBox(
            x1=x - (w / 2),
            y1=y - (h / 2),
            x2=x + (w / 2),
            y2=y + (h / 2),
        )
        return cls(
            name=name,
            bbox=bbox,
            source=source,
            source_format=source_format,
            x=x,
            y=y,
            w=w,
            h=h,
            focus_usage=focus_usage,
            orientation=orientation,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataFace":
        return cls.from_center_box(
            name=str(data.get("name") or ""),
            x=float(data.get("x") or 0),
            y=float(data.get("y") or 0),
            w=float(data.get("w") or 0),
            h=float(data.get("h") or 0),
            source=str(data.get("source") or "metadata"),
            source_format=str(data.get("source_format") or ""),
            focus_usage=str(data.get("focus_usage") or ""),
            orientation=int(data.get("orientation")) if data.get("orientation") not in (None, "") else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "source": self.source,
            "source_format": self.source_format,
        }
        if self.focus_usage:
            payload["focus_usage"] = self.focus_usage
        if self.orientation not in (None, 1):
            payload["orientation"] = self.orientation
        return payload
