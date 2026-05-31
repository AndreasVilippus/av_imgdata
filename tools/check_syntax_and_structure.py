#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PY_DIRS = [ROOT / "src", ROOT / "tests"]
JS_DIRS = [ROOT / "ui" / "src"]
CONFIG_ROOT_NAMES = {
    "config",
    "cfg",
    "root",
    "settings",
    "package_config",
    "runtime_config",
    "merged_config",
    "current_config",
}


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


def _load_config_service_default() -> dict[str, Any]:
    path = ROOT / "src" / "services" / "config_service.py"
    spec = importlib.util.spec_from_file_location("av_imgdata_config_service_check", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load ConfigService from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConfigService.defaultConfig()


def _collect_key_paths(value: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if not isinstance(value, dict):
        return set()
    paths: set[tuple[str, ...]] = set()
    for key, child in value.items():
        key_path = (*prefix, str(key))
        paths.add(key_path)
        paths.update(_collect_key_paths(child, key_path))
    return paths


def _is_valid_config_path(default_config: dict[str, Any], path: tuple[str, ...]) -> bool:
    node: Any = default_config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


def check_default_config_completeness() -> int:
    errors = 0
    shipped_path = ROOT / "var" / "config.json"

    try:
        service_default = _load_config_service_default()
    except Exception as exc:
        fail(f"src/services/config_service.py: could not read ConfigService.defaultConfig(): {exc}")
        return 1

    try:
        shipped_default = json.loads(shipped_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"var/config.json: could not parse shipped default config: {exc}")
        return 1

    if not isinstance(service_default, dict):
        fail("ConfigService.defaultConfig() must return a dict")
        errors += 1
    if not isinstance(shipped_default, dict):
        fail("var/config.json must contain a JSON object")
        errors += 1
    if errors:
        return errors

    service_paths = _collect_key_paths(service_default)
    shipped_paths = _collect_key_paths(shipped_default)

    missing_in_shipped = sorted(service_paths - shipped_paths)
    extra_in_shipped = sorted(shipped_paths - service_paths)

    for path in missing_in_shipped:
        errors += 1
        fail(f"var/config.json: missing default config key: {'.'.join(path)}")
    for path in extra_in_shipped:
        errors += 1
        fail(f"var/config.json: key is not defined by ConfigService.defaultConfig(): {'.'.join(path)}")

    if errors:
        return errors

    normalized_shipped = module_default_projection(service_default, shipped_default)
    if normalized_shipped != shipped_default:
        errors += 1
        fail("var/config.json: shipped default config is not stable under default-key projection")

    return errors


def module_default_projection(default: Any, current: Any) -> Any:
    if isinstance(default, dict):
        current_dict = current if isinstance(current, dict) else {}
        return {
            key: module_default_projection(value, current_dict.get(key))
            for key, value in default.items()
        }
    return current if current is not None else default


def _string_constant(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _subscript_string_key(node: ast.Subscript) -> str | None:
    return _string_constant(node.slice)


def _call_string_arg(node: ast.Call, index: int = 0) -> str | None:
    if len(node.args) <= index:
        return None
    return _string_constant(node.args[index])


def _read_config_prefix(expr: ast.AST, prefixes: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    if isinstance(expr, ast.Name):
        return prefixes.get(expr.id)
    if isinstance(expr, ast.Subscript):
        base = _read_config_prefix(expr.value, prefixes)
        key = _subscript_string_key(expr)
        if base is not None and key:
            return (*base, key)
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "get":
        base = _read_config_prefix(expr.func.value, prefixes)
        key = _call_string_arg(expr)
        if base is not None and key:
            return (*base, key)
    return None


class ConfigAccessVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, default_config: dict[str, Any]):
        self.rel_path = rel_path
        self.default_config = default_config
        self.errors = 0
        self._prefix_stack: list[dict[str, tuple[str, ...]]] = []

    @property
    def prefixes(self) -> dict[str, tuple[str, ...]]:
        return self._prefix_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "migrateLegacyChecksIgnoreLists":
            return
        self._prefix_stack.append({})
        for arg in node.args.args:
            if arg.arg in CONFIG_ROOT_NAMES:
                self.prefixes[arg.arg] = ()
        self.generic_visit(node)
        self._prefix_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Module(self, node: ast.Module) -> None:
        self._prefix_stack.append({})
        self.generic_visit(node)
        self._prefix_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        prefix = self._assigned_config_prefix(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if prefix is not None:
                    self.prefixes[target.id] = prefix
                elif target.id in self.prefixes:
                    self.prefixes.pop(target.id, None)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            prefix = self._assigned_config_prefix(node.value) if node.value is not None else None
            if prefix is not None:
                self.prefixes[node.target.id] = prefix
            elif node.target.id in self.prefixes:
                self.prefixes.pop(node.target.id, None)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = _subscript_string_key(node)
        base = _read_config_prefix(node.value, self.prefixes)
        if key and base is not None:
            self._check_path((*base, key), node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            key = _call_string_arg(node)
            base = _read_config_prefix(node.func.value, self.prefixes)
            if key and base is not None:
                self._check_path((*base, key), node.lineno)
        self.generic_visit(node)

    def _assigned_config_prefix(self, value: ast.AST | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        prefix = _read_config_prefix(value, self.prefixes)
        if prefix is not None:
            return prefix
        if isinstance(value, ast.Call):
            func = value.func
            if isinstance(func, ast.Attribute) and func.attr in {
                "readConfig",
                "readMergedConfig",
                "defaultConfig",
                "normalizeConfig",
            }:
                return ()
        return None

    def _check_path(self, path: tuple[str, ...], lineno: int) -> None:
        if _is_valid_config_path(self.default_config, path):
            return
        self.errors += 1
        fail(f"{self.rel_path}:{lineno}: config key is not defined by defaultConfig(): {'.'.join(path)}")


def check_config_accesses_against_defaults() -> int:
    try:
        default_config = _load_config_service_default()
    except Exception as exc:
        fail(f"src/services/config_service.py: could not read ConfigService.defaultConfig(): {exc}")
        return 1

    errors = 0
    for base in [ROOT / "src"]:
        for path in base.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                continue
            visitor = ConfigAccessVisitor(str(path.relative_to(ROOT)), default_config)
            visitor.visit(tree)
            errors += visitor.errors
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

    suspicious_defs = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if re.match(r"^def [A-Za-z_]", line):
            suspicious_defs.append((lineno, line.strip()))

    allowed_top_level = {
        "def _attach_checks_status_for_response",
    }
    for lineno, text in suspicious_defs:
        if not any(text.startswith(prefix) for prefix in allowed_top_level):
            errors += 1
            fail(f"src/imgdata.py:{lineno}: top-level def found, possible lost class indentation: {text}")

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
    dsm_api_client_path = ROOT / "ui" / "src" / "services" / "dsm-api-client.js"

    cgi_source = cgi_path.read_text(encoding="utf-8")
    api_source = api_path.read_text(encoding="utf-8")
    session_source = session_manager_path.read_text(encoding="utf-8")
    dsm_api_client_source = dsm_api_client_path.read_text(encoding="utf-8")

    expected_cookies = {"_SSID", "id"}

    for cookie_name in expected_cookies:
        if f"{cookie_name}: readCookie('{cookie_name}')" not in dsm_api_client_source:
            errors += 1
            fail(f"ui/src/services/dsm-api-client.js: DSM cookie {cookie_name} is not collected for backend requests")
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


def check_ui_config_define_targets() -> int:
    config_define_path = ROOT / "ui" / "config.define"
    app_config_path = ROOT / "ui" / "app.config"
    info_path = ROOT / "INFO.sh"
    errors = 0

    try:
        config_define = json.loads(config_define_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"ui/config.define: could not parse JSON: {exc}")
        return 1

    if not isinstance(config_define, dict) or not config_define:
        fail("ui/config.define: expected non-empty JSON object")
        return 1

    for target, value in config_define.items():
        target_name = str(target or "").strip()
        if not target_name.endswith(".js"):
            errors += 1
            fail(
                "ui/config.define: generated DSM script target must end with .js "
                f"to be served as JavaScript: {target_name}"
            )
        if not isinstance(value, dict) or not value.get("JSfiles"):
            errors += 1
            fail(f"ui/config.define: target is missing JSfiles: {target_name}")

    try:
        app_config = json.loads(app_config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"ui/app.config: could not parse JSON: {exc}")
        return errors + 1

    if not isinstance(app_config, dict) or not app_config:
        fail("ui/app.config: expected non-empty JSON object")
        return errors + 1

    info_source = info_path.read_text(encoding="utf-8")
    dsmapp_match = re.search(r'^dsmappname="([^"]+)"', info_source, re.M)
    if dsmapp_match:
        dsmappname = dsmapp_match.group(1)
        if dsmappname not in app_config:
            errors += 1
            fail("INFO.sh: dsmappname should match a DSM app id from ui/app.config")

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
    result = subprocess.run(
        ["npm", "--prefix", "ui", "run", "build"],
        cwd=ROOT,
        text=True,
    )
    return 0 if result.returncode == 0 else 1


def main() -> int:
    errors = 0
    errors += check_python_ast()
    errors += check_default_config_completeness()
    errors += check_config_accesses_against_defaults()
    errors += check_imgdata_class_boundaries()
    errors += check_session_cookie_alignment()
    errors += check_cgi_curl_argument_safety()
    errors += check_ui_config_define_targets()
    errors += check_vue_computed_parameter_functions()

    if errors:
        print(f"\nStatic checks failed: {errors}")
        return 1

    print("Static Python/Vue structure checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
