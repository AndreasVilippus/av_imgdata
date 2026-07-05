import ast
import re
from pathlib import Path


UI_ALLOWED_MISSING_THIS_METHODS = {
    "$avt",
    "$nextTick",
    "callDsmApi",
    "callFileAnalysisApi",
    "confirmFaceMatchNameMapping",
    "fetchExiftoolStatus",
    "fetchCleanupProgress",
    "fetchRecognitionFindings",
    "fetchInsightFaceStatus",
    "getErrorMessage",
    "getBackendImagePreviewUrl",
    "getFaceMatchFormatLabel",
    "getFaceMatchSourceLabel",
    "getPhotoThumbnailUrl",
    "getResponseData",
    "getResponseDataObject",
    "getSynoToken",
    "isBrowserImageCompatiblePath",
    "normalizeConfig",
    "normalizeFaceMatchName",
    "resolveLocalIconUrl",
    "startCleanupRun",
    "startCleanupProgressPolling",
    "startNamedPolling",
    "stopCleanupRun",
    "stopNamedPolling",
}

BACKEND_ALLOWED_MISSING_SELF_METHODS = {
    "_now_func",
}


def _strip_js_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"(^|[^:])//.*", r"\1", source)
    return source


def _ui_method_definitions(source: str) -> set[str]:
    # Matches Vue options methods/computed/watch entries like:
    #   foo() {
    #   async foo() {
    #   foo: function (...) {
    # This intentionally focuses on method names available as this.foo(...).
    patterns = [
        r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
        r"^\s*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s+)?function\s*\(",
    ]
    defs: set[str] = set()
    for pattern in patterns:
        defs.update(re.findall(pattern, source, flags=re.MULTILINE))
    return defs


def _ui_this_method_calls(source: str) -> set[str]:
    return set(re.findall(r"\bthis\.([A-Za-z_$][\w$]*)\s*\(", source))


def test_ui_this_method_calls_have_local_definitions():
    ui_files = sorted(Path("ui/src").rglob("*.js"))
    assert ui_files, "No UI JS files found under ui/src"

    failures: list[str] = []
    for path in ui_files:
        source = _strip_js_comments(path.read_text(encoding="utf-8"))
        definitions = _ui_method_definitions(source)
        calls = _ui_this_method_calls(source)

        missing = sorted(calls - definitions - UI_ALLOWED_MISSING_THIS_METHODS)
        if missing:
            failures.append(f"{path}: missing local this-method definitions: {', '.join(missing)}")

    assert not failures, "\n".join(failures)


class _SelfCallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self":
            self.calls.add(func.attr)
        self.generic_visit(node)


def _class_method_definitions(class_node: ast.ClassDef) -> set[str]:
    return {
        item.name
        for item in class_node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _class_self_method_calls(class_node: ast.ClassDef) -> set[str]:
    collector = _SelfCallCollector()
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collector.visit(item)
    return collector.calls


def test_backend_self_method_calls_have_class_definitions():
    backend_files = sorted(Path("src").rglob("*.py"))
    assert backend_files, "No backend Python files found under src"

    failures: list[str] = []
    for path in backend_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path}: syntax error: {exc}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            definitions = _class_method_definitions(node)
            calls = _class_self_method_calls(node)
            missing = sorted(calls - definitions - BACKEND_ALLOWED_MISSING_SELF_METHODS)
            if missing:
                failures.append(
                    f"{path}:{node.name}: missing self-method definitions: {', '.join(missing)}"
                )

    assert not failures, "\n".join(failures)
