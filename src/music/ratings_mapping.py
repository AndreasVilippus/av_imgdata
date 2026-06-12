import re
from typing import Any, Dict, Optional


def _number(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def stars_to_percent(stars: Any) -> Optional[int]:
    value = _number(stars)
    if value is None or value < 0 or value > 5:
        return None
    return round(value * 20)


def popm_to_stars(value: Any) -> Optional[int]:
    """Map Windows Media Player/ExifTool POPM values as used by dev/pg.php."""
    raw = str(value or "").strip()
    match = re.search(r"(?:Rating\s*=\s*)?(\d+(?:\.\d+)?)", raw, flags=re.IGNORECASE)
    number = _number(match.group(1)) if match else _number(value)
    if number is None or number <= 0:
        return None
    for upper, stars in ((1, 1), (64, 2), (128, 3), (196, 4), (255, 5)):
        if number <= upper:
            return stars
    return 5


def normalize_rating(value: Any, schema: str) -> Dict[str, Any]:
    normalized_schema = str(schema or "").strip().lower()
    stars: Optional[float] = None
    if normalized_schema in {"popm", "windows_popm", "popularimeter"}:
        stars = popm_to_stars(value)
    elif normalized_schema in {"stars", "ds_audio", "audio_station"}:
        stars = _number(value)
    elif normalized_schema in {"percent", "rating_percent", "vorbis_rating", "rating"}:
        number = _number(value)
        if number is not None:
            stars = number / 20 if number > 5 else number
    elif normalized_schema in {"fmps_rating", "fmps"}:
        number = _number(value)
        if number is not None:
            stars = number * 5 if number <= 1 else number
    elif normalized_schema in {"mp4_rating", "itunes_rating"}:
        number = _number(value)
        if number is not None:
            stars = number / 20 if number > 5 else number

    if stars is None or stars < 0 or stars > 5:
        return {
            "source_rating_raw": value,
            "source_rating_schema": normalized_schema or "unknown",
            "rating_stars": None,
            "rating_percent": None,
        }
    rounded_stars = round(stars * 2) / 2
    return {
        "source_rating_raw": value,
        "source_rating_schema": normalized_schema or "unknown",
        "rating_stars": rounded_stars,
        "rating_percent": stars_to_percent(rounded_stars),
    }
