from services.name_conflict_snapshot import (
    face_identity_token,
    name_conflict_combination_key,
    name_conflict_entry_combination_keys,
)
from services.face_coordinate_precision import FACE_COORDINATE_DIGITS, format_face_coordinate


def test_name_change_does_not_change_face_identity_token():
    before = {
        "source_format": "MWG_REGIONS",
        "source": "metadata",
        "name": "Max",
        "x": 0.5,
        "y": 0.5,
        "w": 0.2,
        "h": 0.2,
    }
    after = dict(before)
    after["name"] = "Moritz"

    assert face_identity_token(before) == face_identity_token(after)


def test_face_identity_token_uses_shared_coordinate_precision():
    face = {
        "source_format": "MWG_REGIONS",
        "source": "metadata",
        "name": "Max",
        "x": 0.1234564,
        "y": 0.2345674,
        "w": 0.3456784,
        "h": 0.4567894,
    }

    token = face_identity_token(face)

    assert FACE_COORDINATE_DIGITS == 6
    for key in ("x", "y", "w", "h"):
        assert format_face_coordinate(face[key]) in token


def test_combination_key_is_unordered():
    image_path = "/volume1/photo/img.jpg"
    left = {"face_id": 10, "name": "Max"}
    right = {"face_id": 11, "name": "Moritz"}

    assert (
        name_conflict_combination_key(image_path, left, right)
        == name_conflict_combination_key(image_path, right, left)
    )


def test_entry_keys_treat_reversed_faces_as_same_combination():
    image_path = "/volume1/photo/img.jpg"
    face_a = {"face_id": 10, "name": "Max"}
    face_b = {"face_id": 11, "name": "Moritz"}

    first = {
        "image_path": image_path,
        "faces": [face_a, face_b],
    }
    second = {
        "image_path": image_path,
        "faces": [face_b, face_a],
    }

    assert name_conflict_entry_combination_keys(first) == name_conflict_entry_combination_keys(second)


def test_fallback_entry_key_excludes_names():
    before = {
        "image_path": "/volume1/photo/img.jpg",
        "name": "Max",
        "target_name": "Moritz",
        "stable_id": "abc",
    }
    after = {
        "image_path": "/volume1/photo/img.jpg",
        "name": "Moritz",
        "target_name": "Moritz",
        "stable_id": "abc",
    }

    assert name_conflict_entry_combination_keys(before) == name_conflict_entry_combination_keys(after)
