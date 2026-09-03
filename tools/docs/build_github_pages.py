#!/usr/bin/env python3
"""Prepare the ImgData Documentation Core for the MkDocs GitHub Pages build."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = REPO_ROOT / "docs" / "core"
SITE_SOURCE_ROOT = REPO_ROOT / "docs" / "site"
STAGING_ROOT = REPO_ROOT / "build" / "docs-site"
PACKAGE_ICON = REPO_ROOT / "ui" / "PACKAGE_ICON_256.png"
LANGUAGES = ("de", "en")

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n", re.DOTALL)
ID_RE = re.compile(r"^id:\s*(?P<id>[^#\s]+)\s*$", re.MULTILINE)


def read_document_id(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise RuntimeError(f"Missing front matter: {path.relative_to(REPO_ROOT)}")
    id_match = ID_RE.search(match.group("meta"))
    if not id_match:
        raise RuntimeError(f"Missing document id: {path.relative_to(REPO_ROOT)}")
    return id_match.group("id")


def strip_front_matter(text: str) -> str:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return text
    return text[match.end() :]


def markdown_files(language: str) -> dict[Path, Path]:
    root = CORE_ROOT / language
    return {
        path.relative_to(root): path
        for path in sorted(root.rglob("*.md"))
    }


def validate_language_pairs() -> None:
    documents = {language: markdown_files(language) for language in LANGUAGES}
    german = set(documents["de"])
    english = set(documents["en"])

    missing_en = sorted(german - english)
    missing_de = sorted(english - german)
    if missing_en or missing_de:
        messages: list[str] = []
        messages.extend(f"Missing English document: {path}" for path in missing_en)
        messages.extend(f"Missing German document: {path}" for path in missing_de)
        raise RuntimeError("\n".join(messages))

    for relative in sorted(german):
        german_id = read_document_id(documents["de"][relative])
        english_id = read_document_id(documents["en"][relative])
        if german_id != english_id:
            raise RuntimeError(
                f"Document id mismatch for {relative}: de={german_id!r}, en={english_id!r}"
            )


def copy_core_language(language: str) -> None:
    source_root = CORE_ROOT / language
    target_root = STAGING_ROOT / language

    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        target = target_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            target.write_text(
                strip_front_matter(source.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
        else:
            shutil.copy2(source, target)


def prepare_site() -> None:
    validate_language_pairs()

    shutil.rmtree(STAGING_ROOT, ignore_errors=True)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SITE_SOURCE_ROOT / "index.md", STAGING_ROOT / "index.md")
    assets = STAGING_ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SITE_SOURCE_ROOT / "extra.css", assets / "extra.css")
    if PACKAGE_ICON.is_file():
        shutil.copy2(PACKAGE_ICON, assets / "package-icon.png")

    for language in LANGUAGES:
        copy_core_language(language)

    print(f"Prepared GitHub Pages sources in {STAGING_ROOT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    prepare_site()
