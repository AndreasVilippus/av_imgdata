#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path.cwd()
MIXIN = ROOT / "ui" / "src" / "mixins" / "checksMixin.js"
TEST = ROOT / "tests" / "test_checks_scan_start_progress_state.py"

TEST_CONTENT = "from pathlib import Path\n\n\ndef test_checks_scan_running_does_not_depend_on_selected_action():\n    mixin = Path(\"ui/src/mixins/checksMixin.js\").read_text(encoding=\"utf-8\")\n    start = mixin.find(\"isChecksScanRunning()\")\n    assert start >= 0\n    end = mixin.find(\"\\n\\t\\t},\", start)\n    assert end > start\n    method = mixin[start:end]\n\n    assert \"!!progress.running\" in method\n    assert \"String(progress.source_mode || '').trim().toLowerCase() === 'scan'\" in method\n    assert \"selectedChecksAction === 'scan'\" not in method\n\n\ndef test_checks_start_response_is_applied_to_progress_immediately():\n    mixin = Path(\"ui/src/mixins/checksMixin.js\").read_text(encoding=\"utf-8\")\n    start = mixin.find(\"startChecksReview(\")\n    assert start >= 0\n    end = mixin.find(\"\\n\\t\\t},\", start)\n    assert end > start\n    method = mixin[start:end]\n\n    assert \"applyChecksStartProgress(root)\" in method\n\n\ndef test_apply_checks_start_progress_sets_progress_and_polling_for_preparing_state():\n    mixin = Path(\"ui/src/mixins/checksMixin.js\").read_text(encoding=\"utf-8\")\n\n    assert \"applyChecksStartProgress(progress)\" in mixin\n    assert \"this.checksProgress = {\" in mixin\n    assert \"this.startChecksProgressPolling()\" in mixin\n    assert \"progress.running\" in mixin\n    assert \"total_files\" in mixin or \"total_files\" in Path(\"ui/src/views/ChecksView.vue\").read_text(encoding=\"utf-8\")\n"


def require(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")


def find_method_bounds(text: str, method_name: str):
    patterns = [
        f"\t\tasync {method_name}(",
        f"\t\t{method_name}(",
    ]
    for pattern in patterns:
        start = text.find(pattern)
        if start >= 0:
            break
    else:
        return -1, -1
    end = text.find("\n\t\t},", start)
    if end < 0:
        raise SystemExit(f"Could not find end of method {method_name}")
    return start, end + len("\n\t\t},")


def replace_method(text: str, method_name: str, replacement: str) -> str:
    start, end = find_method_bounds(text, method_name)
    if start < 0:
        raise SystemExit(f"Could not find method {method_name}")
    return text[:start] + replacement.rstrip("\n") + text[end:]


def insert_before_method(text: str, before_method: str, insertion: str) -> str:
    if insertion.strip() in text:
        return text
    start, _ = find_method_bounds(text, before_method)
    if start < 0:
        raise SystemExit(f"Could not find insertion marker method {before_method}")
    return text[:start] + insertion + text[start:]


def patch_is_scan_running(text: str) -> str:
    replacement = """\t\tisChecksScanRunning() {
\t\t\tconst progress = this.checksProgress && typeof this.checksProgress === 'object'
\t\t\t\t? this.checksProgress
\t\t\t\t: {};
\t\t\treturn !!progress.running
\t\t\t\t&& String(progress.source_mode || '').trim().toLowerCase() === 'scan'
\t\t\t\t&& String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase();
\t\t},"""
    return replace_method(text, "isChecksScanRunning", replacement)


def add_apply_start_progress(text: str) -> str:
    if "applyChecksStartProgress(progress)" in text:
        return text
    method = """\t\tapplyChecksStartProgress(progress) {
\t\t\tif (!progress || typeof progress !== 'object') {
\t\t\t\treturn;
\t\t\t}
\t\t\tconst sourceMode = String(progress.source_mode || '').trim().toLowerCase();
\t\t\tconst checkType = String(progress.check_type || '').trim().toLowerCase();
\t\t\tif (sourceMode !== 'scan' || checkType !== String(this.selectedChecksType || '').trim().toLowerCase()) {
\t\t\t\treturn;
\t\t\t}
\t\t\tthis.checksProgress = {
\t\t\t\t...(this.checksProgress && typeof this.checksProgress === 'object' ? this.checksProgress : {}),
\t\t\t\t...progress,
\t\t\t};
\t\t\tif (progress.running) {
\t\t\t\tthis.checksLoading = false;
\t\t\t\tthis.startChecksProgressPolling();
\t\t\t}
\t\t},
"""
    return insert_before_method(text, "startChecksReview", method)


def patch_start_checks_review(text: str) -> str:
    start, end = find_method_bounds(text, "startChecksReview")
    if start < 0:
        raise SystemExit("Could not find startChecksReview")
    method = text[start:end]

    if "applyChecksStartProgress(root)" in method:
        return text

    # Insert after common root extraction from checks_start response.
    markers = [
        "const root = this.getResponseData(data);\n",
        "const root = this.getResponseData(response);\n",
        "const root = this.getResponseData(result);\n",
    ]
    for marker in markers:
        idx = method.find(marker)
        if idx >= 0:
            insert_at = idx + len(marker)
            method = method[:insert_at] + "\t\t\tthis.applyChecksStartProgress(root);\n" + method[insert_at:]
            return text[:start] + method + text[end:]

    # Fallback: insert after checks_start API call result assignment.
    pattern = re.compile(r"(const\\s+\\w+\\s*=\\s*await\\s+this\\.callChecksApi\\([^;]*checks_start[^;]*\\);\\n)", re.DOTALL)
    match = pattern.search(method)
    if match:
        var_match = re.search(r"const\\s+(\\w+)\\s*=", match.group(1))
        var_name = var_match.group(1) if var_match else "data"
        insertion = (
            match.group(1)
            + f"\t\t\tconst root = this.getResponseData({var_name});\n"
            + "\t\t\tthis.applyChecksStartProgress(root);\n"
        )
        method = method[:match.start()] + insertion + method[match.end():]
        return text[:start] + method + text[end:]

    raise SystemExit("Could not find where to apply checks_start progress in startChecksReview")


def write_test() -> None:
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_CONTENT, encoding="utf-8")


def main() -> None:
    require(MIXIN)
    text = MIXIN.read_text(encoding="utf-8")
    text = patch_is_scan_running(text)
    text = add_apply_start_progress(text)
    text = patch_start_checks_review(text)
    MIXIN.write_text(text, encoding="utf-8")
    write_test()
    print("Applied checks scan start progress UI patch.")
    print("Next:")
    print("  PYTHONPATH=src python3 -m pytest tests/test_checks_scan_start_progress_state.py tests/test_checks_findings_stop_action.py")
    print("  npm --prefix ui run build")


if __name__ == "__main__":
    main()
