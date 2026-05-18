#!/usr/bin/env python3
import ast
import os
import sys
import unittest
import textwrap
from pathlib import Path

sys.path.insert(0, os.path.abspath('src'))


class SearchPhotoFaceAutoOrchestrationTests(unittest.TestCase):
    def _function_source(self, function_name):
        source = Path('src/imgdata.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return '\n'.join(lines[node.lineno - 1:node.end_lineno])
        self.fail(f'function not found: {function_name}')

    def _called_method_names(self, source):
        tree = ast.parse(textwrap.dedent(source))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
        return names

    def test_search_photo_face_in_file_uses_existing_face_orchestration(self):
        source = self._function_source('searchPhotoFaceInFile')
        calls = self._called_method_names(source)

        self.assertIn('resolveOrCreatePhotosPersonForExistingFace', calls)
        self.assertNotIn('assignMatchedFaceToKnownPerson', calls)
