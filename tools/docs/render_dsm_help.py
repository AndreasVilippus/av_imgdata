#!/usr/bin/env python3
"""Render Documentation Core Markdown into DSM 7.4 help HTML.

The renderer intentionally supports a conservative Markdown subset so the package
build does not require an additional Python Markdown dependency.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "docs" / "core"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "ui" / "help"
LOCALES = {"de": "ger", "en": "enu"}

DSM_HEAD = """<!DOCTYPE html>
<html class=\"img-no-display\">
<head>
<meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\" >
<meta http-equiv=\"X-UA-Compatible\" content=\"IE=edge,chrome=1\">

<link href=\"../../../../help/help.css\" type=\"text/css\" rel=\"stylesheet\"  />
<link href=\"../../../../help/scrollbar/flexcroll.css\" type=\"text/css\" rel=\"stylesheet\"  />
<script type=\"text/javascript\" src=\"../../../../help/scrollbar/flexcroll.js\"></script>
<script type=\"text/javascript\" src=\"../../../../help/scrollbar/initFlexcroll.js\"></script>
</head>
<body>"""
DSM_FOOT = "</body>\n</html>\n"


def strip_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    metadata: dict[str, str] = {}
    end = None
    current_key = ""
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            end = index
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_key:
            old = metadata.get(current_key, "")
            value = line[4:].strip()
            metadata[current_key] = f"{old},{value}".strip(",")
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            current_key = key.strip()
            metadata[current_key] = value.strip().strip("'\"")

    if end is None:
        raise ValueError("unterminated Markdown front matter")
    return metadata, "\n".join(lines[end + 1 :]).lstrip("\n")


def render_inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    escaped = html.escape(text, quote=False)

    escaped = re.sub(
        r"`([^`]+)`",
        lambda match: stash(f"<code>{match.group(1)}</code>"),
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: stash(
            f'<a href="{html.escape(html.unescape(match.group(2)), quote=True)}">{match.group(1)}</a>'
        ),
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)

    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", value)
    return escaped


def render_markdown(text: str, *, index_page: bool = False) -> str:
    lines = text.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            output.append(f"<p>{render_inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            # DSM File Station uses h4 entries on its start page. Keep the
            # document title as h1 and render index topic headings as h4.
            if index_page and level == 2:
                level = 4
            output.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            continue

        if re.match(r"^([-*_])(?:\s*\1){2,}$", stripped):
            flush_paragraph()
            close_list()
            output.append("<hr />")
            continue

        unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            wanted = "ul" if unordered else "ol"
            if list_type != wanted:
                close_list()
                list_type = wanted
                output.append(f"<{wanted}>")
            item = (unordered or ordered).group(1)
            output.append(f"<li>{render_inline(item)}</li>")
            continue

        paragraph.append(stripped)

    if in_code:
        raise ValueError("unterminated fenced code block")
    flush_paragraph()
    close_list()
    return "\n".join(output)


def render_file(source: Path, destination: Path) -> None:
    metadata, markdown = strip_front_matter(source.read_text(encoding="utf-8"))
    document_id = metadata.get("id", source.stem)
    index_page = document_id == "index"
    body = render_markdown(markdown, index_page=index_page)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"{DSM_HEAD}\n{body}\n{DSM_FOOT}", encoding="utf-8")


def render_tree(source_root: Path, output_root: Path) -> list[Path]:
    rendered: list[Path] = []
    for source_locale, dsm_locale in LOCALES.items():
        source_dir = source_root / source_locale
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.rglob("*.md")):
            relative = source.relative_to(source_dir).with_suffix(".html")
            destination = output_root / dsm_locale / relative
            render_file(source, destination)
            rendered.append(destination)
    if not rendered:
        raise RuntimeError(f"no Markdown help pages found below {source_root}")
    return rendered


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="render to memory-equivalent temporary files and verify committed output is current",
    )
    return parser.parse_args(argv)


def check_tree(source_root: Path, output_root: Path) -> int:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="av-imgdata-dsm-help-") as tmp:
        tmp_root = Path(tmp)
        generated = render_tree(source_root, tmp_root)
        stale: list[str] = []
        for generated_file in generated:
            relative = generated_file.relative_to(tmp_root)
            committed = output_root / relative
            if not committed.is_file() or committed.read_bytes() != generated_file.read_bytes():
                stale.append(str(relative))
        if stale:
            print("DSM help output is stale or missing:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    if args.check:
        return check_tree(source_root, output_root)
    rendered = render_tree(source_root, output_root)
    for path in rendered:
        print(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
