from models.bbox import BoundingBox


def _as_face_dict(face_like):
    if isinstance(face_like, dict):
        return face_like
    if hasattr(face_like, "to_dict"):
        return face_like.to_dict()
    return {
        "x": getattr(face_like, "x", 0),
        "y": getattr(face_like, "y", 0),
        "w": getattr(face_like, "w", 0),
        "h": getattr(face_like, "h", 0),
        "orientation": getattr(face_like, "orientation", None),
        "name": getattr(face_like, "name", ""),
        "source": getattr(face_like, "source", "metadata"),
        "source_format": getattr(face_like, "source_format", ""),
    }


def from_photos(face_dict) -> BoundingBox:
    return BoundingBox(
        x1=face_dict["bbox"]["top_left"]["x"],
        y1=face_dict["bbox"]["top_left"]["y"],
        x2=face_dict["bbox"]["bottom_right"]["x"],
        y2=face_dict["bbox"]["bottom_right"]["y"],
    )


def normalize_xmp_face(face_dict) -> dict:
    face_dict = _as_face_dict(face_dict)
    center_x = face_dict["x"]
    center_y = face_dict["y"]
    width = face_dict["w"]
    height = face_dict["h"]

    orientation = int(face_dict.get("orientation") or 1)
    if orientation == 2:
        center_x = 1 - center_x
    elif orientation == 3:
        center_x = 1 - center_x
        center_y = 1 - center_y
    elif orientation == 4:
        center_y = 1 - center_y
    elif orientation == 5:
        center_x, center_y, width, height = center_y, center_x, height, width
    elif orientation == 6:
        center_x, center_y, width, height = 1 - center_y, center_x, height, width
    elif orientation == 7:
        center_x, center_y, width, height = 1 - center_y, 1 - center_x, height, width
    elif orientation == 8:
        center_x, center_y, width, height = center_y, 1 - center_x, height, width

    normalized = dict(face_dict)
    normalized["x"] = center_x
    normalized["y"] = center_y
    normalized["w"] = width
    normalized["h"] = height
    normalized["orientation"] = orientation
    return normalized


def from_xmp(face_dict) -> BoundingBox:
    normalized = normalize_xmp_face(face_dict)
    center_x = normalized["x"]
    center_y = normalized["y"]
    width = normalized["w"]
    height = normalized["h"]
    return BoundingBox(
        x1=center_x - (width / 2),
        y1=center_y - (height / 2),
        x2=center_x + (width / 2),
        y2=center_y + (height / 2),
    )
