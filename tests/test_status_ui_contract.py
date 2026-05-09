from pathlib import Path


def _method_body(source: str, method_name: str) -> str:
    for marker in (f"\t\t{method_name}(", f"\t\tasync {method_name}("):
        start = source.find(marker)
        if start >= 0:
            break
    else:
        raise AssertionError(f"Method not found: {method_name}")

    end = source.find("\n\t\t},", start)
    assert end > start, f"Could not find end of method {method_name}"
    return source[start:end]


def test_checks_ui_prefers_backend_status_counters():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    body = _method_body(source, "getRelevantChecksStatusCounters")

    assert "status.counters" in body
    assert "Array.isArray" in body
    assert "show_when_zero" in body
    assert "Number(counter.value) > 0" in body
    assert "return []" in body



def test_checks_ui_does_not_add_legacy_counters_when_status_counters_exist():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    body = _method_body(source, "getRelevantChecksStatusCounters")

    assert "status.counters" in body
    assert "status.schema_version === 1" in body
    assert "return []" in body
    assert "resolved_count" not in body
    assert "ignored_count" not in body
    assert "skipped_count" not in body
    assert "findings_count" not in body


def test_checks_ui_prefers_backend_status_progress():
    source = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "getChecksStatusProgress(" in source
    body = _method_body(source, "getChecksStatusProgress")

    assert "status.progress" in body
    assert "status.schema_version === 1" in body
    assert "return {}" in body
    assert "source_mode" not in body
    assert "files_scanned" not in body
    assert "total_files" not in body

def test_checks_view_uses_status_progress_helpers_for_progress_card():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert "vm.getChecksStatusProgress()" in view
    assert ':count="vm.getChecksStatusProgress().total"' in view
    assert ':current="vm.getChecksStatusProgress().current"' in view
    assert ':total="vm.getChecksStatusProgress().total"' in view


def test_checks_standalone_status_message_not_shown_when_progress_card_has_status_text():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert ':status-text="vm.getChecksProgressStatusText()"' in view
    assert "shouldShowChecksStandaloneStatusMessage" in view



def test_face_match_ui_prefers_backend_status_counters():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "getFaceMatchStatusCounters(" in source
    body = _method_body(source, "getFaceMatchStatusCounters")

    assert "status.counters" in body
    assert "status.schema_version === 1" in body
    assert "Array.isArray" in body
    assert "show_when_zero" in body
    assert "Number(counter.value) > 0" in body
    assert "return []" in body
    assert "transferred_count" not in body
    assert "findings_count" not in body

def test_face_match_status_headline_uses_backend_status_counters():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "withFaceMatchStatusCounts(" in source
    body = _method_body(source, "withFaceMatchStatusCounts")

    assert "this.getFaceMatchStatusCounters" in body
    assert "status.counters" in source



def test_face_match_ui_prefers_backend_status_progress():
    source = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    assert "getFaceMatchStatusProgress(" in source
    body = _method_body(source, "getFaceMatchStatusProgress")

    assert "status.progress" in body
    assert "status.schema_version === 1" in body
    assert "return {}" in body
    assert "persons_read" not in body
    assert "images_read" not in body
    assert "transferred_count" not in body

def test_ui_counter_format_uses_backend_label_keys_and_fallback_labels():
    checks = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    face_match = Path("ui/src/mixins/faceMatchMixin.js").read_text(encoding="utf-8")

    combined = checks + "\n" + face_match

    assert "fallback_label" in combined
    assert "label_key" in combined
    assert "$avt" in combined
