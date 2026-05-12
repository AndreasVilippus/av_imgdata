import re
from pathlib import Path


TEXTS_ROOT = Path("ui/texts")
UI_SRC_ROOT = Path("ui/src")
SUPPORTED_LANGUAGES = ("ger", "enu")


def _parse_strings_file(path: Path) -> dict:
    current_section = ""
    keys = {}

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue

        if "=" not in line or not current_section:
            continue

        key = line.split("=", 1)[0].strip()
        if not key:
            continue

        full_key = f"{current_section}:{key}"
        keys[full_key] = line_number

    return keys


def _translation_keys(language: str) -> dict:
    path = TEXTS_ROOT / language / "strings"
    assert path.exists(), f"Missing translation file: {path}"
    return _parse_strings_file(path)


def _ui_text_references() -> dict:
    pattern = re.compile(r"\$avt\(\s*(['\"])([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+)\1")
    references = {}

    for path in sorted(UI_SRC_ROOT.rglob("*")):
        if path.suffix not in {".js", ".vue"}:
            continue

        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            key = match.group(2)
            line_number = source.count("\n", 0, match.start()) + 1
            references.setdefault(key, []).append(f"{path}:{line_number}")

    return references


def _format_missing(missing: list[str], references: dict | None = None) -> str:
    lines = []
    for key in sorted(missing):
        if references and references.get(key):
            lines.append(f"{key} referenced at {', '.join(references[key][:5])}")
        else:
            lines.append(key)
    return "\n".join(lines)


def test_german_and_english_translation_key_sets_match():
    german = set(_translation_keys("ger"))
    english = set(_translation_keys("enu"))

    missing_in_german = sorted(english - german)
    missing_in_english = sorted(german - english)

    assert not missing_in_german, (
        "Keys present in ui/texts/enu/strings but missing in ui/texts/ger/strings:\n"
        + _format_missing(missing_in_german)
    )
    assert not missing_in_english, (
        "Keys present in ui/texts/ger/strings but missing in ui/texts/enu/strings:\n"
        + _format_missing(missing_in_english)
    )


def test_all_ui_text_references_exist_in_german_and_english():
    references = _ui_text_references()
    assert references, "No $avt('section:key', ...) references found below ui/src"

    for language in SUPPORTED_LANGUAGES:
        keys = set(_translation_keys(language))
        missing = sorted(key for key in references if key not in keys)

        assert not missing, (
            f"UI text references missing in ui/texts/{language}/strings:\n"
            + _format_missing(missing, references)
        )
