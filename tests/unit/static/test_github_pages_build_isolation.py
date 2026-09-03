from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_BUILD_FILES = (
    ROOT / "tools" / "build-package.sh",
    ROOT / "Makefile",
    ROOT / "SynoBuildConf" / "build",
    ROOT / "SynoBuildConf" / "install",
    ROOT / "ui" / "Makefile",
)


def test_github_pages_tooling_is_not_part_of_package_build():
    forbidden = (
        "requirements-docs.txt",
        "build_github_pages.py",
        "mkdocs build",
        "mkdocs serve",
    )

    for path in PACKAGE_BUILD_FILES:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"GitHub Pages tooling leaked into package build: {path}: {marker}"
