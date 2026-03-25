from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.metadata_face import MetadataFace


@dataclass
class MetadataPayload:
    image_path: str
    xmp_path: str = ""
    has_sidecar: bool = False
    xmp_source: str = ""
    has_xmp: bool = False
    faces: List[MetadataFace] = field(default_factory=list)
    image_dimensions: Dict[str, Any] = field(default_factory=dict)
    image_orientation: Optional[int] = None
    mwg_applied_to_dimensions_present: bool = False
    mwg_applied_to_dimensions: Dict[str, Any] = field(default_factory=dict)
    mwg_applied_to_dimensions_matches_current: Optional[bool] = None
    mwg_orientation_transform_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "xmp_path": self.xmp_path,
            "has_sidecar": self.has_sidecar,
            "xmp_source": self.xmp_source,
            "has_xmp": self.has_xmp,
            "faces": [face.to_dict() for face in self.faces],
            "image_dimensions": dict(self.image_dimensions),
            "image_orientation": self.image_orientation,
            "mwg_applied_to_dimensions_present": self.mwg_applied_to_dimensions_present,
            "mwg_applied_to_dimensions": dict(self.mwg_applied_to_dimensions),
            "mwg_applied_to_dimensions_matches_current": self.mwg_applied_to_dimensions_matches_current,
            "mwg_orientation_transform_required": self.mwg_orientation_transform_required,
        }
