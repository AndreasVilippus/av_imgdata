#!/usr/bin/env python3
import ast
import unittest
from pathlib import Path


def _source_files():
    roots = [Path("app"), Path("src")]
    return [
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


class Python38CompatibilityTests(unittest.TestCase):
    def test_source_parses_as_python38(self):
        source_files = _source_files()

        self.assertTrue(source_files)
        for path in source_files:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 8))

    def test_source_does_not_use_runtime_builtin_generics(self):
        blocked = {"list", "dict", "tuple", "set"}
        violations = []

        for path in _source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 8))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
                    continue
                if node.value.id in blocked:
                    violations.append(f"{path}:{node.lineno}: use typing.{node.value.id.title()} for Python 3.8 runtime compatibility")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
