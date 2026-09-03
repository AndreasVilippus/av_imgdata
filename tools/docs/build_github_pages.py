#!/usr/bin/env python3
"""Prepare the README-based ImgData GitHub Pages site."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README_EN = REPO_ROOT / "README.md"
README_DE = REPO_ROOT / "docs" / "site" / "README.de.md"
SITE_SOURCE_ROOT = REPO_ROOT / "docs" / "site"
STAGING_ROOT = REPO_ROOT / "build" / "docs-site"
PACKAGE_ICON = REPO_ROOT / "ui" / "PACKAGE_ICON_256.png"
GITHUB_ROOT = "https://github.com/AndreasVilippus/av_imgdata"
REPOSITORY_LINK_RE = re.compile(r"\]\(\./(?P<path>[^)#]+)(?P<fragment>#[^)]+)?\)")


def rewrite_repository_links(text: str) -> str:
    """Convert README repository-relative links into stable GitHub links."""

    def replace(match: re.Match[str]) -> str:
        relative = match.group("path")
        fragment = match.group("fragment") or ""
        target = REPO_ROOT / relative
        kind = "tree" if target.is_dir() else "blob"
        return f"]({GITHUB_ROOT}/{kind}/main/{relative}{fragment})"

    text = REPOSITORY_LINK_RE.sub(replace, text)
    return text.replace(
        "https://github.com/<owner>/<repo>/releases",
        f"{GITHUB_ROOT}/releases",
    )


def prepare_site() -> None:
    for source in (README_EN, README_DE):
        if not source.is_file():
            raise RuntimeError(f"Missing website source: {source.relative_to(REPO_ROOT)}")

    shutil.rmtree(STAGING_ROOT, ignore_errors=True)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    # German is the project-page default. English is the alternate language.
    shutil.copy2(README_DE, STAGING_ROOT / "index.md")
    english_root = STAGING_ROOT / "en"
    english_root.mkdir(parents=True, exist_ok=True)
    english_root.joinpath("index.md").write_text(
        rewrite_repository_links(README_EN.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    assets = STAGING_ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SITE_SOURCE_ROOT / "extra.css", assets / "extra.css")
    if PACKAGE_ICON.is_file():
        shutil.copy2(PACKAGE_ICON, assets / "package-icon.png")

    print(f"Prepared README-based GitHub Pages sources in {STAGING_ROOT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    prepare_site()
