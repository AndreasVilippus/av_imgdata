#!/usr/bin/env python3
"""
Repair searchPhotoFaceInFile() after a partial result_entry guard patch.

Usage from the av_imgdata repository root:

    python3 repair_search_photo_face_result_entry_init_v4.py

Problem:
- The installed/current code has:

      if result_entry is None:
          continue

  but no guaranteed `result_entry = None` before the concrete match block.
- That still raises UnboundLocalError when no result_entry was assigned.

Fix:
- Inside searchPhotoFaceInFile() only.
- Find the first guard `if result_entry is None:` before the save_only block.
- Find the nearest preceding concrete match-result block beginning with
  `matched_person = None`.
- Insert `result_entry = None` directly before that block if missing.
- Ensure nameless file-face matches are skipped only in this workflow.

The patch preserves valid result_entry values built later in the block.
"""

from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path


TARGET = Path("src/imgdata.py")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def find_method(content: str, name: str, next_name: str) -> tuple[str, str, str]:
    start_marker = f"    def {name}("
    end_marker = f"    def {next_name}("
    start = content.find(start_marker)
    if start < 0:
        fail(f"Could not find {name}().")
    end = content.find(end_marker, start)
    if end < 0:
        fail(f"Could not find following {next_name}().")
    return content[:start], content[start:end], content[end:]


def ensure_result_entry_initializer(segment: str) -> str:
    guard_match = re.search(
        r'^(?P<guard_indent>\s*)if result_entry is None:\n(?P=guard_indent)    continue\n(?P=guard_indent)if save_only:\n(?P=guard_indent)    saved_entries\.append\(self\._normalizeFaceMatchEntry\(result_entry\)\)',
        segment,
        flags=re.MULTILINE,
    )
    if not guard_match:
        fail("Could not find the result_entry guard before the save_only block in searchPhotoFaceInFile().")

    prefix = segment[:guard_match.start()]
    block_pattern = re.compile(r'^(?P<indent>\s*)matched_person = None\n', flags=re.MULTILINE)
    block_matches = list(block_pattern.finditer(prefix))
    if not block_matches:
        fail("Could not find preceding `matched_person = None` block.")

    block = block_matches[-1]
    indent = block.group("indent")

    # If already inserted directly before this block, do nothing.
    before_block = segment[max(0, block.start() - 200):block.start()]
    if re.search(rf'\n{re.escape(indent)}result_entry = None\n\s*$', before_block):
        return segment

    return segment[:block.start()] + f"{indent}result_entry = None\n" + segment[block.start():]


def ensure_nameless_skip(segment: str) -> str:
    # Only in searchPhotoFaceInFile(): a file-face match without a name cannot
    # drive mapping/person assignment or a useful named-match UI result.
    if re.search(
        r'^\s*matched_name = str\(matched\.get\("file_name"\) or ""\)\.strip\(\)\n'
        r'\s*if not matched_name:\n'
        r'\s*continue\n'
        r'\s*if matched_name:\n',
        segment,
        flags=re.MULTILINE,
    ):
        return segment

    pattern = re.compile(
        r'^(?P<indent>\s*)matched_name = str\(matched\.get\("file_name"\) or ""\)\.strip\(\)\n'
        r'(?P=indent)if matched_name:\n',
        flags=re.MULTILINE,
    )
    matches = list(pattern.finditer(segment))
    if len(matches) != 1:
        fail(f"Expected one matched_name block in searchPhotoFaceInFile(), found {len(matches)}.")

    match = matches[0]
    indent = match.group("indent")
    replacement = (
        f'{indent}matched_name = str(matched.get("file_name") or "").strip()\n'
        f'{indent}if not matched_name:\n'
        f'{indent}    continue\n'
        f'{indent}if matched_name:\n'
    )
    return segment[:match.start()] + replacement + segment[match.end():]


def main() -> int:
    target = Path.cwd() / TARGET
    if not target.exists() or not target.is_file():
        fail(f"Target file not found: {TARGET}. Run from repository root.")

    content = target.read_text(encoding="utf-8")
    original = content

    before, segment, after = find_method(content, "searchPhotoFaceInFile", "searchFileFaceInSources")
    segment = ensure_result_entry_initializer(segment)
    segment = ensure_nameless_skip(segment)

    patched = before + segment + after

    if patched == original:
        print("No changes needed; searchPhotoFaceInFile already appears repaired.")
    else:
        target.write_text(patched, encoding="utf-8")
        print(f"Patched {TARGET}")

    try:
        py_compile.compile(str(target), doraise=True)
    except py_compile.PyCompileError as exc:
        fail(f"py_compile failed:\n{exc}")

    print("py_compile passed.")
    print("Next recommended checks:")
    print("  SYNOPKG_PKGVAR=\"$(mktemp -d)\" python3 -m unittest discover -s tests -p 'test_*.py'")
    print("  git diff -- src/imgdata.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
