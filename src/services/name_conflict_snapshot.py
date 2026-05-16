#!/usr/bin/env python3
"""Stable identity helpers for name_conflicts snapshot processing.

The current face name is intentionally excluded from every identity token. A
name_conflicts auto-fix changes a name; including that name in the key would
make the same physical face pair look new after mutation.
"""

import json
from typing import Any, Dict, List

from services.face_coordinate_precision import FACE_COORDINATE_DIGITS, format_face_coordinate


_NAME_FIELDS = {
    "name",
    "person_name",
    "face_name",
    "target_name",
    "source_name",
}


def _quantized_float_token(value: Any, digits: int = FACE_COORDINATE_DIGITS) -> str:
    if digits == FACE_COORDINATE_DIGITS:
        return format_face_coordinate(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return f"{0.0:.{digits}f}"


def face_identity_token(face: Dict[str, Any]) -> str:
    if not isinstance(face, dict):
        return "face:invalid"

    face_id = face.get("face_id")
    if face_id is not None:
        return f"photos:face:{str(face_id).strip()}"

    source = str(face.get("source") or "").strip().lower()
    source_format = str(face.get("source_format") or face.get("format") or "").strip().upper()

    if all(key in face for key in ("x", "y", "w", "h")):
        return "|".join(
            [
                "metadata",
                source_format,
                source,
                _quantized_float_token(face.get("x")),
                _quantized_float_token(face.get("y")),
                _quantized_float_token(face.get("w")),
                _quantized_float_token(face.get("h")),
            ]
        )

    bbox = face.get("bbox")
    if isinstance(bbox, dict):
        top_left = bbox.get("top_left") if isinstance(bbox.get("top_left"), dict) else {}
        bottom_right = bbox.get("bottom_right") if isinstance(bbox.get("bottom_right"), dict) else {}
        return "|".join(
            [
                "bbox",
                source_format,
                source,
                _quantized_float_token(top_left.get("x")),
                _quantized_float_token(top_left.get("y")),
                _quantized_float_token(bottom_right.get("x")),
                _quantized_float_token(bottom_right.get("y")),
            ]
        )

    normalized = {
        key: value
        for key, value in face.items()
        if key not in _NAME_FIELDS
    }
    return "fallback:" + json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)


def name_conflict_combination_key(image_path: str, left_face: Dict[str, Any], right_face: Dict[str, Any]) -> str:
    left_token = face_identity_token(left_face)
    right_token = face_identity_token(right_face)
    first, second = sorted([left_token, right_token])
    return f"name_conflicts|{str(image_path or '').strip()}|{first}|{second}"


def extract_name_conflict_faces_from_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return []

    candidates: List[Dict[str, Any]] = []

    for key in (
        "faces",
        "conflict_faces",
        "overlapping_faces",
        "name_conflict_faces",
    ):
        value = entry.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])

    for key in (
        "left_face",
        "right_face",
        "source_face",
        "target_face",
        "original_face_data",
        "replacement_face_data",
        "metadata_face",
        "photos_face",
    ):
        value = entry.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for face in candidates:
        token = face_identity_token(face)
        if token in seen:
            continue
        seen.add(token)
        deduped.append(face)
    return deduped


def name_conflict_entry_combination_keys(entry: Dict[str, Any]) -> List[str]:
    image_path = str(entry.get("image_path") or "").strip()
    if not image_path:
        return []

    faces = extract_name_conflict_faces_from_entry(entry)
    if len(faces) < 2:
        normalized = {
            key: value
            for key, value in entry.items()
            if key not in _NAME_FIELDS
        }
        return [
            "name_conflicts|entry|"
            + image_path
            + "|"
            + json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
        ]

    keys: List[str] = []
    for index, left in enumerate(faces):
        for right in faces[index + 1:]:
            keys.append(name_conflict_combination_key(image_path, left, right))
    return keys


def already_processed(entry: Dict[str, Any], processed_keys: set) -> bool:
    return bool(set(name_conflict_entry_combination_keys(entry)).intersection(processed_keys))


def mark_processed(entry: Dict[str, Any], processed_keys: set) -> None:
    processed_keys.update(name_conflict_entry_combination_keys(entry))
