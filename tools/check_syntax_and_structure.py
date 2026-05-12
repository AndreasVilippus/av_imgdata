#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PY_DIRS = [ROOT / "src", ROOT / "tests"]
JS_DIRS = [ROOT / "ui" / "src"]


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def check_python_ast() -> int:
    errors = 0
    for base in PY_DIRS:
        for path in base.rglob("*.py"):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                errors += 1
                fail(f"Python syntax: {path}:{exc.lineno}:{exc.offset}: {exc.msg}")
    return errors


def check_imgdata_class_boundaries() -> int:
    path = ROOT / "src" / "imgdata.py"
    if not path.exists():
        return 0

    source = path.read_text(encoding="utf-8")
    errors = 0

    class_match = re.search(r"^class ImgDataService:\n", source, re.M)
    if not class_match:
        fail("src/imgdata.py: class ImgDataService not found")
        return 1

    # In imgdata.py sollten Service-Methoden mit vier Leerzeichen eingerückt sein.
    suspicious_defs = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if re.match(r"^def [A-Za-z_]", line):
            suspicious_defs.append((lineno, line.strip()))

    allowed_top_level = {
        "def _attach_checks_status_for_response",  # nur falls in API-Datei, nicht hier
    }
    for lineno, text in suspicious_defs:
        if not any(text.startswith(prefix) for prefix in allowed_top_level):
            errors += 1
            fail(f"src/imgdata.py:{lineno}: top-level def found, possible lost class indentation: {text}")

    # Doppelte direkt aufeinanderfolgende Initialisierungen wie result_entry = None.
    lines = source.splitlines()
    for index in range(len(lines) - 1):
        if lines[index].strip() and lines[index].strip() == lines[index + 1].strip():
            if re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*(None|{}|\[\]|0|False|True)$", lines[index].strip()):
                errors += 1
                fail(
                    f"src/imgdata.py:{index + 1}: duplicated adjacent assignment: "
                    f"{lines[index].strip()}"
                )

    return errors


def check_session_cookie_alignment() -> int:
    errors = 0
    cgi_path = ROOT / "ui" / "index.cgi"
    api_path = ROOT / "src" / "api" / "imgdata_api.py"
    session_manager_path = ROOT / "src" / "api" / "session_manager.py"
    app_path = ROOT / "ui" / "src" / "App.vue"

    cgi_source = cgi_path.read_text(encoding="utf-8")
    api_source = api_path.read_text(encoding="utf-8")
    session_source = session_manager_path.read_text(encoding="utf-8")
    app_source = app_path.read_text(encoding="utf-8")

    expected_cookies = {"_SSID", "id"}

    for cookie_name in expected_cookies:
        if f"{cookie_name}: this.readCookie('{cookie_name}')" not in app_source:
            errors += 1
            fail(f"ui/src/App.vue: DSM cookie {cookie_name} is not collected for backend requests")
        if f'"{cookie_name}" not in cookies' not in api_source and f'cookies.get("{cookie_name}")' not in session_source:
            errors += 1
            fail(f"backend session handling: DSM cookie {cookie_name} is not accepted")
        if f"; {cookie_name}=" not in cgi_source:
            errors += 1
            fail(f"ui/index.cgi: DSM cookie {cookie_name} is not accepted by CGI gate")

    if "if \"id\" not in cookies and \"_SSID\" not in cookies" not in api_source:
        errors += 1
        fail("src/api/imgdata_api.py: expected id/_SSID session-cookie gate not found")
    if "raw_key = cookies.get(\"id\") or cookies.get(\"_SSID\")" not in session_source:
        errors += 1
        fail("src/api/session_manager.py: expected id/_SSID user-key precedence not found")
    if "has_dsm_session_cookie" not in cgi_source:
        errors += 1
        fail("ui/index.cgi: central DSM session cookie check not found")

    return errors


def check_cgi_curl_argument_safety() -> int:
    path = ROOT / "ui" / "index.cgi"
    source = path.read_text(encoding="utf-8")
    errors = 0

    forbidden_patterns = [
        r"\$\{HTTP_COOKIE:\+-H\s+\"Cookie:",
        r"\$\{CONTENT_TYPE:\+-H\s+\"Content-Type:",
        r"\$\{HTTP_ORIGIN:\+-H\s+\"Origin:",
        r"\$\{HTTP_REFERER:\+-H\s+\"Referer:",
        r"\$\{HTTP_X_SYNO_TOKEN:\+-H\s+\"X-SYNO-TOKEN:",
        r"\$\{body_file:\+--data-binary",
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, source):
            errors += 1
            fail(
                "ui/index.cgi: unsafe curl argument construction found; "
                "build curl arguments with set -- instead"
            )

    required_fragments = {
        'set -- -s -D "$hdr_file" -o "$out_file" -X "$method"':
            "expected set -- based curl argument initialization not found",
        'set -- "$@" -H "Cookie: $HTTP_COOKIE"':
            "expected quoted Cookie header forwarding not found",
        'set -- "$@" -H "Content-Type: $CONTENT_TYPE"':
            "expected quoted Content-Type header forwarding not found",
        'set -- "$@" -H "Origin: $HTTP_ORIGIN"':
            "expected quoted Origin header forwarding not found",
        'set -- "$@" -H "Referer: $HTTP_REFERER"':
            "expected quoted Referer header forwarding not found",
        'set -- "$@" -H "X-SYNO-TOKEN: $HTTP_X_SYNO_TOKEN"':
            "expected quoted X-SYNO-TOKEN header forwarding not found",
        'set -- "$@" --data-binary "@$body_file"':
            "expected quoted request-body forwarding not found",
        '"$curl_cmd" "$@" "$target"':
            "expected quoted curl invocation not found",
    }

    for fragment, message in required_fragments.items():
        if fragment not in source:
            errors += 1
            fail(f"ui/index.cgi: {message}")

    return errors


def check_vue_computed_parameter_functions() -> int:
    errors = 0

    for base in JS_DIRS:
        for path in base.rglob("*.js"):
            source = path.read_text(encoding="utf-8")

            computed_match = re.search(r"\n\tcomputed:\s*\{(?P<body>.*?)\n\twatch:\s*\{", source, re.S)
            if not computed_match:
                continue

            body = computed_match.group("body")
            for match in re.finditer(r"\n\t\t([A-Za-z_$][\w$]*)\s*\(([^)]*[^\s)])\)\s*\{", body):
                name = match.group(1)
                params = match.group(2).strip()
                if params:
                    errors += 1
                    line = source[:computed_match.start("body") + match.start()].count("\n") + 1
                    fail(
                        f"{path.relative_to(ROOT)}:{line}: computed property has parameters; "
                        f"move to methods: {name}({params})"
                    )

    return errors


def check_js_parse_with_build() -> int:
    # Webpack/Babel fängt JS/Vue-Syntaxfehler zuverlässig ab.
    result = subprocess.run(
        ["npm", "--prefix", "ui", "run", "build"],
        cwd=ROOT,
        text=True,
    )
    return 0 if result.returncode == 0 else 1


def main() -> int:
    errors = 0
    errors += check_python_ast()
    errors += check_imgdata_class_boundaries()
    errors += check_session_cookie_alignment()
    errors += check_cgi_curl_argument_safety()
    errors += check_vue_computed_parameter_functions()

    if errors:
        print(f"\nStatic checks failed: {errors}")
        return 1

    print("Static Python/Vue structure checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
