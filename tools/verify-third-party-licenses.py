#!/usr/bin/env python3
"""Generate and verify third-party notices for bundled native runtimes."""

import argparse
import json
import re
import sys
from pathlib import Path


COMPONENTS = [
    {
        "id": "onnxruntime",
        "name": "ONNX Runtime",
        "license": "MIT",
        "source": "https://github.com/microsoft/onnxruntime",
        "patterns": [r"^(?:lib)?onnxruntime(?:_providers_shared)?(?:\.dll|\.so(?:\..*)?)$"],
        "evidence": ["onnxruntime", "ThirdPartyNotices"],
    },
    {
        "id": "libjpeg",
        "name": "libjpeg/libjpeg-turbo compatible runtime",
        "license": "IJG/BSD/zlib-style terms depending on provider",
        "source": "https://libjpeg-turbo.org/",
        "patterns": [r"^(?:lib)?jpeg(?:-[0-9]+)?\.dll$", r"^libjpeg\.so(?:\..*)?$", r"^libturbojpeg\.dll$"],
        "evidence": ["jpeg", "libjpeg-turbo"],
    },
    {
        "id": "libvips",
        "name": "libvips",
        "license": "LGPL-2.1-or-later",
        "source": "https://github.com/libvips/libvips",
        "patterns": [r"^libvips(?:-[0-9]+)?\.dll$", r"^libvips\.so(?:\..*)?$"],
        "evidence": ["libvips", "vips-"],
    },
    {
        "id": "libheif",
        "name": "libheif",
        "license": "LGPL",
        "source": "https://github.com/strukturag/libheif",
        "patterns": [r"^libheif\.dll$", r"^libheif\.so(?:\..*)?$"],
        "evidence": ["libheif"],
    },
    {
        "id": "libde265",
        "name": "libde265",
        "license": "LGPL",
        "source": "https://github.com/strukturag/libde265",
        "patterns": [r"^libde265\.dll$", r"^libde265\.so(?:\..*)?$"],
        "evidence": ["libde265"],
    },
    {
        "id": "libaom",
        "name": "libaom",
        "license": "BSD-2-Clause",
        "source": "https://aomedia.googlesource.com/aom",
        "patterns": [r"^libaom\.dll$", r"^libaom\.so(?:\..*)?$"],
        "evidence": ["aom", "libaom"],
    },
    {
        "id": "glib",
        "name": "GLib/GObject/GIO/GModule/GThread",
        "license": "LGPL-2.1-or-later",
        "source": "https://gitlab.gnome.org/GNOME/glib",
        "patterns": [
            r"^libg(?:lib|object|io|module|thread)-2\.0(?:-[0-9]+)?\.dll$",
            r"^libg(?:lib|object|io|module|thread)-2\.0\.so(?:\..*)?$",
        ],
        "evidence": ["glib", "gobject", "gio", "gmodule", "gthread"],
    },
    {
        "id": "libffi",
        "name": "libffi",
        "license": "MIT-style",
        "source": "https://github.com/libffi/libffi",
        "patterns": [r"^libffi-[0-9]+\.dll$", r"^libffi\.so(?:\..*)?$"],
        "evidence": ["libffi"],
    },
    {
        "id": "pcre",
        "name": "PCRE",
        "license": "BSD-style",
        "source": "https://www.pcre.org/",
        "patterns": [r"^libpcre(?:-[0-9]+)?\.dll$", r"^libpcre\.so(?:\..*)?$"],
        "evidence": ["pcre"],
    },
    {
        "id": "expat",
        "name": "Expat",
        "license": "MIT",
        "source": "https://libexpat.github.io/",
        "patterns": [r"^libexpat(?:-[0-9]+)?\.dll$", r"^libexpat\.so(?:\..*)?$"],
        "evidence": ["expat"],
    },
    {
        "id": "zlib",
        "name": "zlib",
        "license": "zlib",
        "source": "https://zlib.net/",
        "patterns": [r"^libz[0-9]*\.dll$", r"^libz\.so(?:\..*)?$"],
        "evidence": ["zlib", "libz"],
    },
    {
        "id": "libpng",
        "name": "libpng",
        "license": "libpng",
        "source": "https://libpng.org/pub/png/libpng.html",
        "patterns": [r"^libpng(?:16)?(?:-[0-9]+)?\.dll$", r"^libpng16\.so(?:\..*)?$"],
        "evidence": ["libpng", "png"],
    },
    {
        "id": "libspng",
        "name": "libspng",
        "license": "BSD-2-Clause",
        "source": "https://github.com/randy408/libspng",
        "patterns": [r"^libspng(?:-[0-9]+)?\.dll$", r"^libspng\.so(?:\..*)?$"],
        "evidence": ["spng", "libspng"],
    },
    {
        "id": "libtiff",
        "name": "libtiff",
        "license": "BSD-style",
        "source": "https://gitlab.com/libtiff/libtiff",
        "patterns": [r"^libtiff(?:-[0-9]+)?\.dll$", r"^libtiff\.so(?:\..*)?$"],
        "evidence": ["libtiff", "tiff"],
    },
    {
        "id": "libwebp",
        "name": "libwebp/libwebpmux/libwebpdemux/libsharpyuv",
        "license": "BSD-style",
        "source": "https://chromium.googlesource.com/webm/libwebp",
        "patterns": [
            r"^libwebp(?:mux|demux)?(?:-[0-9]+)?\.dll$",
            r"^libwebp(?:mux|demux)?\.so(?:\..*)?$",
            r"^libsharpyuv(?:-[0-9]+)?\.dll$",
            r"^libsharpyuv\.so(?:\..*)?$",
        ],
        "evidence": ["libwebp", "webp", "sharpyuv"],
    },
    {
        "id": "lcms2",
        "name": "Little CMS/lcms2",
        "license": "MIT",
        "source": "https://www.littlecms.com/",
        "patterns": [r"^liblcms2(?:-[0-9]+)?\.dll$", r"^liblcms2\.so(?:\..*)?$"],
        "evidence": ["lcms", "lcms2"],
    },
    {
        "id": "xz",
        "name": "XZ Utils/liblzma",
        "license": "public-domain/LGPL/GPL mix as documented by provider",
        "source": "https://tukaani.org/xz/",
        "patterns": [r"^liblzma(?:-[0-9]+)?\.dll$", r"^liblzma\.so(?:\..*)?$"],
        "evidence": ["xz", "lzma"],
    },
    {
        "id": "util-linux",
        "name": "util-linux/e2fsprogs libraries",
        "license": "LGPL/BSD-style components depending on provider",
        "source": "https://github.com/util-linux/util-linux",
        "patterns": [
            r"^lib(?:mount|blkid|uuid)(?:-[0-9]+)?\.dll$",
            r"^lib(?:mount|blkid|uuid)\.so(?:\..*)?$",
        ],
        "evidence": ["util-linux", "e2fsprogs", "libuuid", "uuid", "blkid", "mount"],
    },
    {
        "id": "highway",
        "name": "Google Highway",
        "license": "Apache-2.0",
        "source": "https://github.com/google/highway",
        "patterns": [r"^libhwy\.dll$", r"^libhwy\.so(?:\..*)?$"],
        "evidence": ["hwy", "highway"],
    },
    {
        "id": "mingw-runtime",
        "name": "MinGW/GCC runtime libraries",
        "license": "GPL-compatible runtime-library exception terms depending on component",
        "source": "https://gcc.gnu.org/",
        "patterns": [
            r"^libstdc\+\+-6\.dll$",
            r"^libgcc_s_(?:seh|sjlj|dw2)-1\.dll$",
            r"^libwinpthread-1\.dll$",
        ],
        "evidence": ["gcc", "mingw", "winpthread", "libstdc++"],
    },
]


def mkdir_p(path):
    if path.is_dir():
        return
    parent = path.parent
    if parent != path:
        mkdir_p(parent)
    try:
        path.mkdir()
    except OSError:
        if not path.is_dir():
            raise


def write_utf8(path, content):
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)


def runtime_files(root):
    files = []
    for relative_dir in ("lib", "bin"):
        directory = root / relative_dir
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() and not path.is_symlink():
                continue
            name = path.name
            if name.startswith("av-imgdata-"):
                continue
            if name.endswith(".dll") or ".so" in name:
                files.append(path)
    return files


def compile_patterns():
    return [
        (component, [re.compile(pattern, re.IGNORECASE) for pattern in component["patterns"]])
        for component in COMPONENTS
    ]


def match_component(filename, compiled):
    for component, patterns in compiled:
        if any(pattern.match(filename) for pattern in patterns):
            return component
    return None


def find_evidence(root, terms):
    license_root = root / "share" / "licenses"
    if not license_root.is_dir():
        return []
    normalized_terms = [term.lower() for term in terms]
    evidence = []
    for path in sorted(license_root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        lowered = str(path.relative_to(root)).lower()
        if any(term in lowered for term in normalized_terms):
            evidence.append(str(path.relative_to(root)))
    return evidence


def build_notice(root):
    compiled = compile_patterns()
    unknown = []
    components = {}

    for path in runtime_files(root):
        relative = str(path.relative_to(root))
        component = match_component(path.name, compiled)
        if component is None:
            unknown.append(relative)
            continue
        component_id = str(component["id"])
        entry = components.setdefault(
            component_id,
            {
                "id": component_id,
                "name": component["name"],
                "license": component["license"],
                "source": component["source"],
                "files": [],
                "evidence_files": find_evidence(root, component.get("evidence", [])),
            },
        )
        entry["files"].append(relative)

    notice = {
        "schema": "av-imgdata-third-party-notices-v1",
        "root": str(root),
        "components": sorted(components.values(), key=lambda item: str(item["id"])),
    }
    return notice, unknown


def write_notice(root, notice):
    target_dir = root / "share" / "licenses" / "AV_ImgData" / "third-party"
    mkdir_p(target_dir)
    write_utf8(
        target_dir / "THIRD-PARTY-NOTICES.json",
        json.dumps(notice, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    lines = [
        "AV_ImgData third-party native runtime notice",
        "",
        "This directory is generated by tools/verify-third-party-licenses.py.",
        "Each listed runtime file is either covered by copied license material under share/licenses or by the source/license reference recorded in THIRD-PARTY-NOTICES.json.",
        "",
    ]
    for component in notice["components"]:
        evidence = component.get("evidence_files") or []
        evidence_text = ", ".join(evidence) if evidence else "source/license reference only"
        lines.append(
            "- {name}: {license} ({source}); evidence: {evidence}".format(
                name=component["name"],
                license=component["license"],
                source=component["source"],
                evidence=evidence_text,
            )
        )
    write_utf8(target_dir / "README.txt", "\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Package or worker dist root to scan.")
    parser.add_argument("--write", action="store_true", help="Write THIRD-PARTY-NOTICES.json and README.txt.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print("ERROR: root is not a directory: {0}".format(root), file=sys.stderr)
        return 2

    notice, unknown = build_notice(root)
    if unknown:
        print("ERROR: bundled native runtime files without license mapping:", file=sys.stderr)
        for item in unknown:
            print("  - {0}".format(item), file=sys.stderr)
        print("Add the component to tools/verify-third-party-licenses.py before packaging it.", file=sys.stderr)
        return 1

    if args.write:
        try:
            write_notice(root, notice)
        except OSError as exc:
            print(
                "ERROR: third-party notice files could not be written below {0}: {1}".format(root, exc),
                file=sys.stderr,
            )
            return 1

    print(json.dumps({"root": str(root), "components": len(notice["components"]), "runtime_files": sum(len(item["files"]) for item in notice["components"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
