#!/usr/bin/env python3
import ast
from pathlib import Path


def test_source_parses_as_python38():
    roots = [Path("app"), Path("src")]
    source_files = [
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]

    assert source_files
    for path in source_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 8))
