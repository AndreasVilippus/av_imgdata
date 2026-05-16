FACE_COORDINATE_DIGITS = 6
FACE_COORDINATE_TOLERANCE = 10 ** -FACE_COORDINATE_DIGITS


def format_face_coordinate(value) -> str:
    try:
        return f"{float(value):.{FACE_COORDINATE_DIGITS}f}"
    except (TypeError, ValueError):
        return f"{0.0:.{FACE_COORDINATE_DIGITS}f}"


def round_face_coordinate(value):
    try:
        return round(float(value), FACE_COORDINATE_DIGITS)
    except (TypeError, ValueError):
        return value
