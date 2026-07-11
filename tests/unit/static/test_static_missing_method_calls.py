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
    "_clock",
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


def _base_class_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return ""


def _class_base_names(class_node: ast.ClassDef) -> list[str]:
    return [name for name in (_base_class_name(base) for base in class_node.bases) if name]


def _class_method_index(trees: list[ast.AST]) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    methods: dict[str, set[str]] = {}
    bases: dict[str, list[str]] = {}
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods[node.name] = _class_method_definitions(node)
            bases[node.name] = _class_base_names(node)
    return methods, bases


def _class_method_definitions_with_bases(
    class_name: str,
    methods: dict[str, set[str]],
    bases: dict[str, list[str]],
    seen: set[str] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    if class_name in seen:
        return set()
    seen.add(class_name)

    definitions = set(methods.get(class_name, set()))
    for base_name in bases.get(class_name, []):
        definitions.update(_class_method_definitions_with_bases(base_name, methods, bases, seen))
    return definitions


def _class_self_method_calls(class_node: ast.ClassDef) -> set[str]:
    collector = _SelfCallCollector()
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collector.visit(item)
    return collector.calls


def test_backend_self_method_definition_helper_resolves_inherited_methods():
    tree = ast.parse(
        """
class Base:
    def inherited(self):
        pass

class Child(Base):
    def local(self):
        self.inherited()
        self.local()
"""
    )
    methods, bases = _class_method_index([tree])

    assert _class_method_definitions_with_bases("Child", methods, bases) == {"inherited", "local"}


def test_backend_self_method_calls_have_class_definitions():
    backend_files = sorted(Path("src").rglob("*.py"))
    assert backend_files, "No backend Python files found under src"

    failures: list[str] = []
    parsed_files: list[tuple[Path, ast.AST]] = []
    for path in backend_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path}: syntax error: {exc}")
            continue
        parsed_files.append((path, tree))

    methods, bases = _class_method_index([tree for _, tree in parsed_files])

    for path, tree in parsed_files:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            definitions = _class_method_definitions_with_bases(node.name, methods, bases)
            calls = _class_self_method_calls(node)
            missing = sorted(calls - definitions - BACKEND_ALLOWED_MISSING_SELF_METHODS)
            if missing:
                failures.append(
                    f"{path}:{node.name}: missing self-method definitions: {', '.join(missing)}"
                )

    assert not failures, "\n".join(failures)
