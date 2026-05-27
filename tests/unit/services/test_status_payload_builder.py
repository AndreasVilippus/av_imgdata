from services.status_payload_builder import StatusPayloadBuilder


def test_status_payload_filters_zero_counters_unless_explicitly_visible():
    builder = StatusPayloadBuilder()

    payload = builder.payload(
        operation="checks",
        action="dimension_issues",
        mode="scan",
        phase="running",
        counters=[
            builder.counter("hidden", value=0),
            builder.counter("visible", value=0, show_when_zero=True),
            builder.counter("nonzero", value=3),
        ],
    )

    assert [counter["key"] for counter in payload["counters"]] == ["visible", "nonzero"]
    assert payload["schema_version"] == 1


def test_checks_save_only_status_keeps_findings_counter_when_zero():
    payload = StatusPayloadBuilder().checks_payload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="finished",
        save_only=True,
        files_scanned=12,
        total_files=12,
        findings_count=0,
    )

    assert payload["operation"] == "checks"
    assert payload["action"] == "name_conflicts"
    assert payload["mode"] == "scan"
    assert payload["save_only"] is True
    assert payload["progress"]["kind"] == "files"
    assert payload["counters"] == [{
        "key": "findings",
        "value": 0,
        "label_key": "checks:counter_stored_findings",
        "fallback_label": "In Fundliste",
        "show_when_zero": True,
    }]


def test_checks_save_only_status_reports_stored_and_auto_resolved_counts():
    payload = StatusPayloadBuilder().checks_payload(
        check_type="name_conflicts",
        source_mode="scan",
        phase="running",
        save_only=True,
        files_scanned=12,
        total_files=30,
        findings_count=5,
        resolved_count=3,
        ignored_count=2,
        transferred_count=1,
    )

    assert [counter["key"] for counter in payload["counters"]] == ["findings", "resolved"]
    assert payload["counters"][0]["label_key"] == "checks:counter_stored_findings"
    assert payload["counters"][0]["value"] == 5
    assert payload["counters"][1]["label_key"] == "checks:counter_auto_resolved"
    assert payload["counters"][1]["value"] == 3


def test_face_match_findings_status_only_exposes_action_counters():
    payload = StatusPayloadBuilder().face_match_payload(
        action="search_photo_face_in_file",
        source_mode="findings",
        phase="running",
        current=2,
        total=8,
        findings_count=99,
        transferred_count=1,
        skipped_count=0,
        errors_count=2,
        created_count=3,
    )

    assert payload["operation"] == "face_match"
    assert payload["mode"] == "findings"
    assert payload["progress"]["kind"] == "entries"
    assert [counter["key"] for counter in payload["counters"]] == ["transferred", "errors"]


def test_status_phase_derivation_keeps_blocked_and_stopped_distinct():
    builder = StatusPayloadBuilder()

    assert builder.derive_phase(status="blocked", running=False) == "blocked"
    assert builder.derive_phase(stop_requested=True, running=True) == "stopping"
    assert builder.derive_phase(stop_requested=True, running=False) == "stopped"
