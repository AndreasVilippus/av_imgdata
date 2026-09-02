#!/usr/bin/env python3
"""Render Documentation Core Markdown into DSM 7.4 help HTML.

The renderer intentionally supports a conservative Markdown subset so the package
build does not require an additional Python Markdown dependency.
"""

from __future__ import annotations

import argparse
import json
import html
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "docs" / "core"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "ui" / "help"
DEFAULT_TOC_PATH = REPO_ROOT / "ui" / "helptoc.conf"
DEFAULT_INFO_PATH = REPO_ROOT / "INFO.sh"
LOCALES = {"de": "ger", "en": "enu"}
HELPTOC_TITLE = "helptoc:imgdata"
HELPSET = "help"
STRINGSET = "texts"

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


def read_info_value(info_path: Path, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=(?P<quote>[\"']?)(?P<value>.*?)(?P=quote)$")
    for line in info_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group("value")
    raise RuntimeError(f"{key} not found in {info_path}")


def collect_helptoc_entries(source_root: Path) -> list[dict[str, str]]:
    """Collect visible DSM navigation entries from the canonical German source tree.

    A document is included when it targets DSM, is not the root index, and defines
    an explicit DSM title key. English must use the same document IDs and ordering,
    so one locale is sufficient for navigation generation.
    """
    source_dir = source_root / "de"
    entries: list[tuple[int, str, dict[str, str]]] = []

    for source in sorted(source_dir.rglob("*.md")):
        metadata, _ = strip_front_matter(source.read_text(encoding="utf-8"))
        document_id = metadata.get("id", source.stem)
        targets = {item.strip() for item in metadata.get("targets", "").split(",") if item.strip()}
        dsm_title_key = metadata.get("dsm_title_key", "").strip()

        if document_id == "index" or "dsm" not in targets or not dsm_title_key:
            continue

        try:
            order = int(metadata.get("order", "1000") or "1000")
        except ValueError as exc:
            raise ValueError(f"invalid order in {source}: {metadata.get('order')!r}") from exc

        relative = source.relative_to(source_dir).with_suffix(".html").as_posix()
        entries.append(
            (
                order,
                document_id,
                {
                    "title": dsm_title_key,
                    "content": relative,
                },
            )
        )

    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in entries]


def build_helptoc(app_id: str, source_root: Path) -> dict[str, object]:
    return {
        "app": app_id,
        "title": HELPTOC_TITLE,
        "content": "index.html",
        "helpset": HELPSET,
        "stringset": STRINGSET,
        "toc": collect_helptoc_entries(source_root),
    }


def write_helptoc(toc_path: Path, info_path: Path, source_root: Path) -> None:
    app_id = read_info_value(info_path, "dsmappname")
    toc_path.write_text(
        json.dumps(build_helptoc(app_id, source_root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--toc-path", type=Path, default=DEFAULT_TOC_PATH)
    parser.add_argument("--info-path", type=Path, default=DEFAULT_INFO_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="render to memory-equivalent temporary files and verify committed output is current",
    )
    return parser.parse_args(argv)


def check_tree(source_root: Path, output_root: Path, toc_path: Path, info_path: Path) -> int:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="av-imgdata-dsm-help-") as tmp:
        tmp_root = Path(tmp)
        tmp_toc = tmp_root / "helptoc.conf"
        generated = render_tree(source_root, tmp_root)
        write_helptoc(tmp_toc, info_path, source_root)
        stale: list[str] = []
        for generated_file in generated:
            relative = generated_file.relative_to(tmp_root)
            committed = output_root / relative
            if not committed.is_file() or committed.read_bytes() != generated_file.read_bytes():
                stale.append(str(relative))
        if not toc_path.is_file() or toc_path.read_bytes() != tmp_toc.read_bytes():
            stale.append(str(toc_path.relative_to(REPO_ROOT) if toc_path.is_relative_to(REPO_ROOT) else toc_path))
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
    toc_path = args.toc_path.resolve()
    info_path = args.info_path.resolve()
    if args.check:
        return check_tree(source_root, output_root, toc_path, info_path)
    rendered = render_tree(source_root, output_root)
    write_helptoc(toc_path, info_path, source_root)
    for path in rendered:
        print(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path)
    print(toc_path.relative_to(REPO_ROOT) if toc_path.is_relative_to(REPO_ROOT) else toc_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
