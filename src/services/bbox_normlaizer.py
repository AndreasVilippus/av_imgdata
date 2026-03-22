from models.bbox import BoundingBox

def from_photos(face_dict) -> BoundingBox:
    return BoundingBox(
        x1=face_dict["bbox"]["top_left"]["x"],
        y1=face_dict["bbox"]["top_left"]["y"],
        x2=face_dict["bbox"]["bottom_right"]["x"],
        y2=face_dict["bbox"]["bottom_right"]["y"],
    )


def from_xmp(face_dict) -> BoundingBox:
    center_x = face_dict["x"]
    center_y = face_dict["y"]
    width = face_dict["w"]
    height = face_dict["h"]
    return BoundingBox(
        x1=center_x - (width / 2),
        y1=center_y - (height / 2),
        x2=center_x + (width / 2),
        y2=center_y + (height / 2),
    )
