#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from handler.file_handler import FileHandler, SidecarLookupCache  # noqa: E402
from parser.metadata_parser import MetadataParser  # noqa: E402
from services.config_service import ConfigService  # noqa: E402


DEFAULT_SCAN_PATHS = [ROOT / "tests"]


def _bool_schema(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return bool(value)


def _read_metadata_schema_config(config: Dict[str, Any]) -> Dict[str, bool]:
    metadata_config = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    schema_config = metadata_config.get("SCHEMAS") if isinstance(metadata_config.get("SCHEMAS"), dict) else {}
    return {
        "ACD": _bool_schema(schema_config.get("ACD"), True),
        "MICROSOFT": _bool_schema(schema_config.get("MICROSOFT"), True),
        "MWG_REGIONS": _bool_schema(schema_config.get("MWG_REGIONS"), True),
    }


def _read_files_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return config.get("files") if isinstance(config.get("files"), dict) else {}


def _counter_add(target: Counter, values: Dict[str, Any]) -> None:
    for key, value in values.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        try:
            target[normalized_key] += int(value or 0)
        except (TypeError, ValueError):
            continue


def _is_xmp_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".xmp"


def _is_image_file(path: Path, extensions: Iterable[str]) -> bool:
    normalized_extensions = {str(item or "").strip().lower().lstrip(".") for item in extensions}
    return path.is_file() and path.suffix.lower().lstrip(".") in normalized_extensions


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    result: List[Path] = []
    seen = set()
    for path in paths:
        try:
            normalized = str(path.expanduser().resolve())
        except OSError:
            normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(Path(normalized))
    return result


def _discover_image_files(paths: Sequence[Path], file_handler: FileHandler) -> List[Path]:
    discovered: List[Path] = []
    extensions = file_handler.effectiveImageExtensions()
    for input_path in paths:
        candidate = input_path.expanduser()
        if candidate.is_dir():
            discovered.extend(Path(item) for item in file_handler.listImageFiles(str(candidate)))
        elif _is_image_file(candidate, extensions):
            discovered.append(candidate)
    return _dedupe_paths(discovered)


def _discover_xmp_files(paths: Sequence[Path]) -> List[Path]:
    discovered: List[Path] = []
    for input_path in paths:
        candidate = input_path.expanduser()
        if candidate.is_dir():
            discovered.extend(path for path in candidate.rglob("*.xmp") if path.is_file() and "@eaDir" not in path.parts)
        elif _is_xmp_file(candidate):
            discovered.append(candidate)
    return _dedupe_paths(discovered)


def _read_image_metadata_context(
    image_path: Path,
    *,
    file_handler: FileHandler,
    sidecar_cache: SidecarLookupCache,
    files_config: Dict[str, Any],
) -> Dict[str, Any]:
    sidecar_path = file_handler.findXmpForImage(str(image_path), lookup_cache=sidecar_cache)
    sidecar_content = file_handler.loadXmpFromFile(sidecar_path) if sidecar_path else None

    max_scan_bytes = int(files_config.get("EMBEDDED_XMP_FULL_SCAN_MAX_BYTES") or 67108864)
    include_embedded = True
    context = file_handler.readJpegContext(
        str(image_path),
        include_xmp=include_embedded,
        max_scan_bytes=max_scan_bytes,
    )
    image_dimensions = {
        "width": context.get("width"),
        "height": context.get("height"),
        "unit": context.get("unit") or "pixel",
    }
    if image_dimensions.get("width") is None and image_dimensions.get("height") is None:
        image_dimensions = file_handler.readImageDimensions(str(image_path))

    embedded_content = context.get("xmp_content") if isinstance(context.get("xmp_content"), str) else None
    embedded_source = str(context.get("xmp_source") or "embedded_xmp")
    if not embedded_content and bool(files_config.get("EMBEDDED_XMP_FULL_SCAN_ENABLED", False)):
        embedded_content = file_handler.loadXmpFromImageParsed(str(image_path), max_bytes=max_scan_bytes)
        embedded_source = "embedded_xmp_full_scan" if embedded_content else embedded_source

    sidecar_read_mode = str(files_config.get("SIDECAR_READ_MODE") or "direct_first").strip().lower()
    prefer_embedded = sidecar_read_mode in {"embedded_first", "image_first"}

    xmp_content = embedded_content if prefer_embedded and embedded_content else sidecar_content or embedded_content
    xmp_path = "" if xmp_content is embedded_content else str(sidecar_path or "")
    xmp_source = embedded_source if xmp_content is embedded_content else "sidecar"

    return {
        "image_path": str(image_path),
        "xmp_path": xmp_path,
        "xmp_content": xmp_content,
        "xmp_source": xmp_source if xmp_content else "",
        "image_dimensions": image_dimensions,
        "image_orientation": context.get("orientation"),
    }


def _parse_metadata_context(
    context: Dict[str, Any],
    *,
    parser: MetadataParser,
    schema_config: Dict[str, bool],
    include_unnamed_acd: bool,
) -> Dict[str, Any]:
    payload = parser.parse(
        image_path=str(context.get("image_path") or ""),
        xmp_content=context.get("xmp_content") if isinstance(context.get("xmp_content"), str) else None,
        xmp_path=str(context.get("xmp_path") or ""),
        xmp_source=str(context.get("xmp_source") or ""),
        image_dimensions=context.get("image_dimensions") if isinstance(context.get("image_dimensions"), dict) else None,
        image_orientation=context.get("image_orientation"),
        use_acd=bool(schema_config.get("ACD", True)),
        use_microsoft=bool(schema_config.get("MICROSOFT", True)),
        use_mwg_regions=bool(schema_config.get("MWG_REGIONS", True)),
        include_unnamed_acd=include_unnamed_acd,
    )
    return payload.to_dict()


def _analyze_metadata_dict(metadata: Dict[str, Any]) -> Dict[str, Any]:
    faces = metadata.get("faces") if isinstance(metadata.get("faces"), list) else []
    named_faces = 0
    unnamed_faces = 0
    person_names = set()
    formats: Counter = Counter()
    sources: Counter = Counter()

    for face in faces:
        if not isinstance(face, dict):
            continue
        name = str(face.get("name") or "").strip()
        if name:
            named_faces += 1
            person_names.add(name.casefold())
        else:
            unnamed_faces += 1
        source_format = str(face.get("source_format") or face.get("format") or "").strip()
        if source_format:
            formats[source_format] += 1
        source = str(face.get("source") or metadata.get("xmp_source") or "metadata").strip()
        if source:
            sources[source] += 1

    return {
        "files_with_face_metadata": 1 if faces else 0,
        "faces_total": len(faces),
        "faces_named": named_faces,
        "faces_unnamed": unnamed_faces,
        "persons_distinct_by_name": len(person_names),
        "formats": dict(sorted(formats.items())),
        "sources": dict(sorted(sources.items())),
    }


def _compact_face(face: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "name",
        "source",
        "source_format",
        "x",
        "y",
        "w",
        "h",
        "unit",
        "focus_usage",
    ]
    return {key: face.get(key) for key in keys if key in face and face.get(key) not in (None, "")}


def scan_paths(
    paths: Sequence[Path],
    *,
    include_xmp_files: bool = False,
    include_all_files: bool = False,
    include_face_details: bool = True,
    include_unnamed_acd: bool = False,
) -> Dict[str, Any]:
    config_service = ConfigService()
    config = config_service.readMergedConfig()
    files_config = _read_files_config(config)
    schema_config = _read_metadata_schema_config(config)
    file_handler = FileHandler(config_service)
    parser = MetadataParser()
    sidecar_cache = SidecarLookupCache()

    image_files = _discover_image_files(paths, file_handler)
    xmp_files = _discover_xmp_files(paths) if include_xmp_files else []

    image_sidecars = set()
    file_entries: List[Dict[str, Any]] = []
    totals = {
        "input_paths": [str(path) for path in paths],
        "image_files_scanned": 0,
        "xmp_files_scanned": 0,
        "files_with_xmp": 0,
        "files_with_face_metadata": 0,
        "faces_total": 0,
        "faces_named": 0,
        "faces_unnamed": 0,
        "persons_distinct_by_name": 0,
        "formats": {},
        "sources": {},
        "files": file_entries,
    }
    all_names = set()
    format_counts: Counter = Counter()
    source_counts: Counter = Counter()

    for image_path in image_files:
        context = _read_image_metadata_context(
            image_path,
            file_handler=file_handler,
            sidecar_cache=sidecar_cache,
            files_config=files_config,
        )
        if context.get("xmp_path"):
            image_sidecars.add(str(Path(str(context["xmp_path"])).resolve()))
        metadata = _parse_metadata_context(
            context,
            parser=parser,
            schema_config=schema_config,
            include_unnamed_acd=include_unnamed_acd,
        )
        analysis = _analyze_metadata_dict(metadata)
        faces = metadata.get("faces") if isinstance(metadata.get("faces"), list) else []
        totals["image_files_scanned"] += 1
        totals["files_with_xmp"] += 1 if metadata.get("has_xmp") else 0
        totals["files_with_face_metadata"] += int(analysis["files_with_face_metadata"])
        totals["faces_total"] += int(analysis["faces_total"])
        totals["faces_named"] += int(analysis["faces_named"])
        totals["faces_unnamed"] += int(analysis["faces_unnamed"])
        _counter_add(format_counts, analysis["formats"])
        _counter_add(source_counts, analysis["sources"])
        for face in faces:
            if isinstance(face, dict) and str(face.get("name") or "").strip():
                all_names.add(str(face.get("name")).strip())
        if include_all_files or faces:
            entry = {
                "image_path": str(image_path),
                "xmp_path": metadata.get("xmp_path") or "",
                "xmp_source": metadata.get("xmp_source") or "",
                "has_xmp": bool(metadata.get("has_xmp")),
                **analysis,
            }
            if include_face_details:
                entry["faces"] = [_compact_face(face) for face in faces if isinstance(face, dict)]
            file_entries.append(entry)

    for xmp_path in xmp_files:
        try:
            resolved_xmp = str(xmp_path.resolve())
        except OSError:
            resolved_xmp = str(xmp_path)
        if resolved_xmp in image_sidecars:
            continue
        xmp_content = file_handler.loadXmpFromFile(str(xmp_path))
        metadata = _parse_metadata_context(
            {
                "image_path": str(xmp_path),
                "xmp_path": str(xmp_path),
                "xmp_content": xmp_content,
                "xmp_source": "standalone_xmp",
                "image_dimensions": {},
                "image_orientation": None,
            },
            parser=parser,
            schema_config=schema_config,
            include_unnamed_acd=include_unnamed_acd,
        )
        analysis = _analyze_metadata_dict(metadata)
        faces = metadata.get("faces") if isinstance(metadata.get("faces"), list) else []
        totals["xmp_files_scanned"] += 1
        totals["files_with_xmp"] += 1 if metadata.get("has_xmp") else 0
        totals["files_with_face_metadata"] += int(analysis["files_with_face_metadata"])
        totals["faces_total"] += int(analysis["faces_total"])
        totals["faces_named"] += int(analysis["faces_named"])
        totals["faces_unnamed"] += int(analysis["faces_unnamed"])
        _counter_add(format_counts, analysis["formats"])
        _counter_add(source_counts, analysis["sources"])
        for face in faces:
            if isinstance(face, dict) and str(face.get("name") or "").strip():
                all_names.add(str(face.get("name")).strip())
        if include_all_files or faces:
            entry = {
                "image_path": str(xmp_path),
                "xmp_path": str(xmp_path),
                "xmp_source": "standalone_xmp",
                "has_xmp": bool(metadata.get("has_xmp")),
                **analysis,
            }
            if include_face_details:
                entry["faces"] = [_compact_face(face) for face in faces if isinstance(face, dict)]
            file_entries.append(entry)

    totals["persons_distinct_by_name"] = len({name.casefold() for name in all_names})
    totals["person_names"] = sorted(all_names, key=lambda value: value.casefold())
    totals["formats"] = dict(sorted(format_counts.items()))
    totals["sources"] = dict(sorted(source_counts.items()))
    totals["files_total_scanned"] = int(totals["image_files_scanned"]) + int(totals["xmp_files_scanned"])
    return totals


def _write_json_output(path: Path, result: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_text_summary(result: Dict[str, Any]) -> None:
    print("Face metadata analysis")
    print("======================")
    print(f"Input paths: {', '.join(result.get('input_paths') or [])}")
    print(f"Images scanned: {int(result.get('image_files_scanned') or 0)}")
    print(f"Standalone XMP scanned: {int(result.get('xmp_files_scanned') or 0)}")
    print(f"Files with XMP: {int(result.get('files_with_xmp') or 0)}")
    print(f"Files with face metadata: {int(result.get('files_with_face_metadata') or 0)}")
    print(f"Faces total: {int(result.get('faces_total') or 0)}")
    print(f"Named faces: {int(result.get('faces_named') or 0)}")
    print(f"Unnamed faces: {int(result.get('faces_unnamed') or 0)}")
    print(f"Distinct person names: {int(result.get('persons_distinct_by_name') or 0)}")
    formats = result.get("formats") if isinstance(result.get("formats"), dict) else {}
    sources = result.get("sources") if isinstance(result.get("sources"), dict) else {}
    if formats:
        print("Formats: " + ", ".join(f"{key}: {value}" for key, value in formats.items()))
    if sources:
        print("Sources: " + ", ".join(f"{key}: {value}" for key, value in sources.items()))
    names = result.get("person_names") if isinstance(result.get("person_names"), list) else []
    if names:
        print("Persons: " + ", ".join(str(name) for name in names))
    files = result.get("files") if isinstance(result.get("files"), list) else []
    if files:
        print("")
        print("Files with detected faces:")
        for entry in files:
            if not isinstance(entry, dict) or int(entry.get("faces_total") or 0) <= 0:
                continue
            print(f"- {entry.get('image_path')} ({entry.get('faces_total')} faces, {entry.get('xmp_source') or 'metadata'})")
            faces = entry.get("faces") if isinstance(entry.get("faces"), list) else []
            for face in faces:
                if not isinstance(face, dict):
                    continue
                name = str(face.get("name") or "<unnamed>")
                source_format = str(face.get("source_format") or "unknown")
                print(f"  - {name} [{source_format}]")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search image/XMP metadata for stored face regions in the current test stock.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=DEFAULT_SCAN_PATHS,
        help="Image, XMP, or directory paths to scan. Defaults to ./tests.",
    )
    parser.add_argument(
        "--include-xmp-files",
        action="store_true",
        help="Also parse standalone .xmp files that are not reached as image sidecars.",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Include files without detected faces in the JSON result.",
    )
    parser.add_argument(
        "--no-face-details",
        action="store_true",
        help="Only write per-file counters, not individual face entries.",
    )
    parser.add_argument(
        "--include-unnamed-acd",
        action="store_true",
        help="Include unnamed ACDSee face regions instead of filtering them out.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete result as JSON instead of a text summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for writing the complete JSON result.",
    )
    parser.add_argument(
        "--fail-if-none",
        action="store_true",
        help="Exit with code 2 if no face metadata is found.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = scan_paths(
        args.paths,
        include_xmp_files=bool(args.include_xmp_files),
        include_all_files=bool(args.all_files),
        include_face_details=not bool(args.no_face_details),
        include_unnamed_acd=bool(args.include_unnamed_acd),
    )
    if args.output:
        _write_json_output(args.output, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_summary(result)
    if args.fail_if_none and int(result.get("faces_total") or 0) <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
