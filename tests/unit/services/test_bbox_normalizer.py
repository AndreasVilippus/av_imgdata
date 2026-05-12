from pytest import approx

from services.bbox_normalizer import (
    denormalize_xmp_face,
    normalize_xmp_face,
    to_display_face,
)


def _face(*, x=0.25, y=0.35, w=0.2, h=0.1, orientation=1, source_format="MICROSOFT"):
    return {
        "name": "Person",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "source": "metadata",
        "source_format": source_format,
        "orientation": orientation,
    }


def test_to_display_face_is_idempotent():
    once = to_display_face(_face(x=0.5, y=0.5, w=0.2, h=0.2))
    twice = to_display_face(once)

    assert once == twice
    assert once["display_normalized"] is True
    assert once["bbox"] == approx({
        "x1": 0.4,
        "y1": 0.4,
        "x2": 0.6,
        "y2": 0.6,
    })


def test_to_display_face_normalizes_microsoft_orientation_6_and_adds_bbox():
    face = to_display_face(_face(x=0.2, y=0.3, w=0.4, h=0.1, orientation=6))

    assert face["display_normalized"] is True
    assert face["x"] == approx(0.7)
    assert face["y"] == approx(0.2)
    assert face["w"] == approx(0.1)
    assert face["h"] == approx(0.4)
    assert face["bbox"] == approx({
        "x1": 0.65,
        "y1": 0.0,
        "x2": 0.75,
        "y2": 0.4,
    })


def test_to_display_face_does_not_orientation_normalize_acd_faces():
    face = to_display_face(_face(x=0.2, y=0.3, w=0.4, h=0.1, orientation=6, source_format="ACD"))

    assert face["x"] == approx(0.2)
    assert face["y"] == approx(0.3)
    assert face["w"] == approx(0.4)
    assert face["h"] == approx(0.1)
    assert face["bbox"] == approx({
        "x1": 0.0,
        "y1": 0.25,
        "x2": 0.4,
        "y2": 0.35,
    })


def test_normalize_and_denormalize_xmp_face_roundtrip_for_all_orientations():
    original = _face(x=0.25, y=0.35, w=0.2, h=0.1)

    for orientation in range(1, 9):
        face = dict(original, orientation=orientation)
        normalized = normalize_xmp_face(face)
        denormalized = denormalize_xmp_face(normalized)

        assert denormalized["orientation"] == orientation
        assert denormalized["x"] == approx(face["x"])
        assert denormalized["y"] == approx(face["y"])
        assert denormalized["w"] == approx(face["w"])
        assert denormalized["h"] == approx(face["h"])


def test_normalize_xmp_face_expected_coordinates_for_all_orientations():
    cases = {
        1: (0.25, 0.35, 0.2, 0.1),
        2: (0.75, 0.35, 0.2, 0.1),
        3: (0.75, 0.65, 0.2, 0.1),
        4: (0.25, 0.65, 0.2, 0.1),
        5: (0.35, 0.25, 0.1, 0.2),
        6: (0.65, 0.25, 0.1, 0.2),
        7: (0.65, 0.75, 0.1, 0.2),
        8: (0.35, 0.75, 0.1, 0.2),
    }

    for orientation, expected in cases.items():
        normalized = normalize_xmp_face(_face(orientation=orientation))

        assert (
            normalized["x"],
            normalized["y"],
            normalized["w"],
            normalized["h"],
        ) == approx(expected)
