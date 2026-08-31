import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.face_recognition_service import FaceRecognitionService
from services.status_payload_builder import StatusPayloadBuilder


PROJECT_DIR = Path(__file__).resolve().parents[3]
MATRIX_PATH = PROJECT_DIR / "tests" / "fixtures" / "status_process_matrix.json"


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _processes():
    return _matrix()["processes"]


def _process_ids():
    return {process["id"] for process in _processes()}


def _process_by_id():
    return {process["id"]: process for process in _processes()}


def _chains():
    return _matrix()["process_chains"]


def _scenarios():
    return _matrix()["usage_scenarios"]


def _api_routes():
    routes = set()
    for path in (PROJECT_DIR / "src" / "api").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        routes.update(re.findall(r'@router\.(?:post|get)\("([^"]+)"', text))
    return routes


def _ui_api_routes():
    routes = set()
    for path in (PROJECT_DIR / "ui" / "src").rglob("*"):
        if path.suffix not in {".js", ".vue"}:
            continue
        text = path.read_text(encoding="utf-8")
        routes.update(f"/{match}" for match in re.findall(r"index\.cgi/api/([a-z_]+)", text))
    return routes


def _chain_routes(chain):
    routes = set()
    for key, value in chain.items():
        if key.endswith("_route") and isinstance(value, str):
            routes.add(value)
        elif key.endswith("_routes") and isinstance(value, list):
            routes.update(route for route in value if isinstance(route, str))
    return routes


def _actions(operation):
    return {process["action"] for process in _processes() if process["operation"] == operation}


def _option_values(path):
    text = (PROJECT_DIR / path).read_text(encoding="utf-8")
    return set(re.findall(r'<option\s+value="([^"]+)"', text))


def _counter_keys(status):
    return [counter.get("key") for counter in status.get("counters", [])]


def _function_source(source, function_name):
    pattern = rf"^(?:async\s+)?def {re.escape(function_name)}\("
    match = re.search(pattern, source, re.M)
    assert match, function_name
    next_match = re.search(r"^(?:async\s+)?def [a-zA-Z0-9_]+\(", source[match.end():], re.M)
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start():end]


def test_status_process_matrix_is_machine_readable_and_unique():
    matrix = _matrix()

    assert matrix["schema_version"] == 1
    assert matrix["status_schema_version"] == 1
    assert isinstance(matrix["processes"], list)
    assert matrix["processes"]
    assert isinstance(matrix["process_chains"], list)
    assert matrix["process_chains"]
    ids = [process["id"] for process in matrix["processes"]]
    assert len(ids) == len(set(ids))
    chain_ids = [chain["id"] for chain in matrix["process_chains"]]
    assert len(chain_ids) == len(set(chain_ids))
    scenario_ids = [scenario["id"] for scenario in matrix["usage_scenarios"]]
    assert len(scenario_ids) == len(set(scenario_ids))


def test_status_process_matrix_declares_core_concepts():
    concepts = _matrix()["status_concepts"]

    assert set(concepts) == {
        "identity",
        "run_lifecycle",
        "review_lifecycle",
        "basic_review_workflow",
        "resume",
        "storage",
        "stop_blocking_reconnect",
        "delegated_reconnect_options",
        "slow_auxiliary_endpoints",
    }
    assert concepts["identity"]["required_fields"] == _matrix()["global_rules"]["identity_fields"]
    assert set(concepts["run_lifecycle"]["non_terminal_phases"]).issubset(_matrix()["core_phases"])
    assert {"review_required", "needs_profiles"}.issubset(concepts["run_lifecycle"]["terminal_phases"])
    assert {
        "search",
        "find",
        "show_finding",
        "show_oriented_face_box",
        "select_suggested_target",
        "select_alternate_target",
        "create_target",
        "save",
        "save_as",
        "continue_search",
    }.issubset(concepts["basic_review_workflow"]["required_capabilities"])
    assert {"resume_existing", "resume_from_progress"}.issubset(concepts["resume"]["flags"])
    assert {
        "resume_start_person_index",
        "resume_after_image_id",
        "resume_after_face_id",
        "resume_progress_counts",
        "scan_next_path_index",
        "skip_face_ids",
        "skip_targets",
    }.issubset(concepts["resume"]["cursor_fields"])


def test_status_process_matrix_covers_backend_and_ui_process_actions():
    builder = StatusPayloadBuilder()
    checks_options = _option_values("ui/src/views/ChecksView.vue")

    assert set(builder.CHECK_TYPES).issubset(_actions("checks"))
    assert FaceRecognitionService.ACTIONS.issubset(_actions("cleanup"))
    assert "load_photo_face_match_findings" in _actions("face_match")
    assert _option_values("ui/src/views/CleanupView.vue").issubset(_actions("cleanup"))
    assert _option_values("ui/src/views/FaceMatchView.vue").issubset(_actions("face_match") | _actions("cleanup"))
    assert (checks_options - {"scan", "findings"}).issubset(_actions("checks") | _actions("cleanup"))


def test_status_process_chains_reference_existing_routes_and_processes():
    process_ids = _process_ids()
    api_routes = _api_routes()

    for chain in _chains():
        assert chain["processes"]
        assert set(chain["processes"]).issubset(process_ids)
        assert chain["modes"]
        assert _chain_routes(chain)
        assert _chain_routes(chain).issubset(api_routes)


def test_ui_api_routes_have_backend_handlers():
    assert _ui_api_routes().issubset(_api_routes())


def test_status_process_chains_cover_every_process_mode():
    covered = set()
    for chain in _chains():
        for process_id in chain["processes"]:
            for mode in chain["modes"]:
                covered.add((process_id, mode))

    expected = {
        (process["id"], mode)
        for process in _processes()
        for mode in process["modes"]
    }
    assert expected.issubset(covered)


def test_status_process_chains_model_long_running_control_routes():
    for chain in _chains():
        if "scan" not in chain["modes"]:
            continue
        assert "entry_route" in chain
        assert "progress_route" in chain
        assert "stop_route" in chain


def test_status_process_chains_model_review_and_resume_paths():
    for process in _processes():
        for mode, spec in process["modes"].items():
            if not spec.get("reviewable"):
                continue
            matching_chains = [
                chain for chain in _chains()
                if process["id"] in chain["processes"] and mode in chain["modes"]
            ]
            assert matching_chains
            assert any(
                "review_route" in chain or "select_route" in chain or "item_route" in chain
                for chain in matching_chains
            )
            if spec.get("resume_required_after_review"):
                assert any(chain.get("resume_trigger") for chain in matching_chains)


def test_status_process_chains_cover_review_mutation_routes():
    expected_mutation_routes = {
        "/checks_ignore_entry",
        "/checks_delete_metadata_face",
        "/checks_replace_metadata_face_name",
        "/checks_replace_metadata_face_position",
        "/checks_assign_face_person",
        "/face_assign_match",
        "/face_create_match",
        "/face_skip_match",
        "/face_apply_metadata_match",
        "/face_assign_metadata_match",
        "/face_create_metadata_match",
        "/face_delete_metadata_match",
        "/face_person_suggest",
        "/cleanup_face_frames_select",
        "/cleanup_face_frames_apply",
        "/recognition_review",
        "/recognition_suggestions_apply",
    }
    represented = set()
    for chain in _chains():
        represented.update(route for route in chain.get("mutation_routes", []))
        if chain.get("review_route"):
            represented.add(chain["review_route"])
        if chain.get("select_route"):
            represented.add(chain["select_route"])
        if chain.get("apply_route"):
            represented.add(chain["apply_route"])

    assert expected_mutation_routes.issubset(represented)


def test_usage_scenarios_cover_real_process_flows():
    required_scenarios = {
        "file_analysis_initial_scan",
        "checks_save_only_then_review_findings",
        "checks_interactive_review_resume_after_mutation",
        "face_match_interactive_mutation_resume",
        "face_match_save_only_then_load_findings",
        "cleanup_normalize_names",
        "face_frame_immediate_review_resume",
        "recognition_build_profiles",
        "recognition_unknown_immediate_apply_resume",
        "recognition_unknown_save_as_alternate_person_resume",
        "recognition_unknown_create_missing_person_resume",
        "recognition_unknown_current_person_images_complete_but_persons_remaining",
        "recognition_assignment_from_checks_apply_resume",
        "recognition_outlier_exclude_resume",
        "all_scan_chains_stop_request",
        "cross_operation_parallel_start_blocked",
        "cross_operation_stopped_then_other_operation_starts",
        "backend_reopen_resumable_stopped_or_uncontinued_process_offers_restart_or_resume",
        "operation_reconnect_stale_progress_filter",
        "delegated_running_process_reconnect_adopts_owner_action_and_options",
        "running_process_findings_empty_or_timeout_preserves_progress",
        "checks_incremental_changed_since_scan",
        "checks_auto_apply_suggested_names_and_duplicates",
        "face_match_auto_assign_known_during_scan",
        "face_match_stored_findings_auto_apply_known",
        "recognition_unknown_save_only_then_findings_review",
        "recognition_assignment_save_only_then_findings_review",
        "recognition_outlier_save_only_then_findings_review",
        "recognition_safe_only_auto_apply",
        "recognition_needs_profiles_before_suggestions",
        "insightface_optional_component_missing",
        "insightface_models_missing_or_unlicensed",
        "insightface_status_probe_slow_does_not_block_reconnect_or_progress",
        "external_worker_prefetch_enabled",
        "face_frame_save_only_then_findings_apply",
        "empty_result_terminal_state",
        "mutation_error_reconcile_findings",
    }
    chain_ids = {chain["id"] for chain in _chains()}
    process_ids = _process_ids()
    scenario_ids = {scenario["id"] for scenario in _scenarios()}

    assert required_scenarios.issubset(scenario_ids)
    for scenario in _scenarios():
        assert set(scenario["chains"]).issubset(chain_ids)
        assert set(scenario["processes"]).issubset(process_ids)
        assert scenario["modes"]
        assert scenario["steps"]
        chain_modes = {
            mode
            for chain in _chains()
            if chain["id"] in scenario["chains"]
            for mode in chain["modes"]
        }
        assert set(scenario["modes"]).issubset(chain_modes)


def test_usage_scenarios_cover_operational_reality_classes():
    scenario_text = "\n".join(
        f"{scenario['id']} {' '.join(scenario['steps'])}"
        for scenario in _scenarios()
    )

    for required_term in (
        "save_only",
        "findings",
        "immediate",
        "resume",
        "stop",
        "blocked",
        "terminal_stopped",
        "start_different_operation",
        "restart_or_resume",
        "reconnect",
        "delegated",
        "running_options_loaded",
        "stale",
        "auto",
        "changed_since_days",
        "optional_component",
        "timeout",
        "progress_poll_remains",
        "model_missing",
        "external_worker",
        "empty",
        "mutation_fails",
        "show_finding",
        "save_as",
        "continue_search",
    ):
        assert required_term in scenario_text


def test_usage_scenarios_cover_every_scan_chain_stop_path():
    stop_scenario = next(scenario for scenario in _scenarios() if scenario["id"] == "all_scan_chains_stop_request")
    scan_chains = {chain["id"] for chain in _chains() if "scan" in chain["modes"]}

    assert scan_chains.issubset(set(stop_scenario["chains"]))
    assert "stop_route" in stop_scenario["steps"]


def test_usage_scenarios_cover_stopped_then_other_operation_without_altlasten():
    scenario = next(
        scenario for scenario in _scenarios()
        if scenario["id"] == "cross_operation_stopped_then_other_operation_starts"
    )
    process_by_id = _process_by_id()
    represented_operations = {
        process_by_id[process_id]["operation"]
        for process_id in scenario["processes"]
    }
    steps = set(scenario["steps"])

    assert {"file_analysis", "checks", "face_match", "cleanup"}.issubset(represented_operations)
    assert {
        "terminal_stopped",
        "start_different_operation",
        "old_progress_marked_terminal_or_stale",
        "new_operation_id_created",
        "new_active_identity_not_overwritten",
        "old_stop_requested_not_inherited",
    }.issubset(steps)


def test_usage_scenarios_cover_backend_reopen_restart_or_resume_choice():
    scenario = next(
        scenario for scenario in _scenarios()
        if scenario["id"] == "backend_reopen_resumable_stopped_or_uncontinued_process_offers_restart_or_resume"
    )
    steps = set(scenario["steps"])
    resumable_chains = {
        chain["id"]
        for chain in _chains()
        if "scan" in chain["modes"]
        and any(parameter in chain.get("parameters", []) for parameter in ("resume_from_progress", "resume_existing", "scan_next_path_index", "skip_face_ids", "skip_targets"))
    }

    assert resumable_chains.issubset(set(scenario["chains"]))
    assert {
        "backend_reopen",
        "load_persisted_stopped_or_uncontinued_progress",
        "resume_available_or_resume_cursor_present",
        "owning_view_shows_restart_choice",
        "owning_view_shows_resume_choice",
        "restart_clears_resume_cursor_and_skip_state",
        "resume_uses_resume_cursor_or_resume_existing",
        "new_operation_id_created",
        "old_stop_requested_not_inherited",
    }.issubset(steps)


def test_usage_scenarios_cover_component_failure_for_insightface_processes():
    failure_scenarios = [
        scenario for scenario in _scenarios()
        if scenario["id"] in {"insightface_optional_component_missing", "insightface_models_missing_or_unlicensed"}
    ]
    represented_processes = {
        process_id
        for scenario in failure_scenarios
        for process_id in scenario["processes"]
    }
    expected = {
        "face_match.search_missing_faces_insightface",
        "cleanup.standardize_face_frames",
        "cleanup.recognition_build_profiles",
        "cleanup.recognition_analyze_unknown_faces",
        "cleanup.recognition_check_person_assignments",
    }

    assert expected.issubset(represented_processes)


def test_usage_scenarios_cover_delegated_reconnect_options_and_auxiliary_timeouts():
    scenarios = {scenario["id"]: scenario for scenario in _scenarios()}

    delegated = scenarios["delegated_running_process_reconnect_adopts_owner_action_and_options"]
    assert {
        "face_match.recognition_unknown_delegate",
        "checks.recognition_assignment_delegate",
        "cleanup.recognition_unknown",
        "cleanup.recognition_assignment",
    }.issubset(set(delegated["chains"]))
    assert {
        "browser_reconnect",
        "poll_cleanup_progress_returns_delegated_running_action",
        "owning_view_updates_selected_action",
        "running_options_loaded_into_settings",
        "foreign_default_progress_does_not_hide_running_identity",
    }.issubset(set(delegated["steps"]))

    findings_timeout = scenarios["running_process_findings_empty_or_timeout_preserves_progress"]
    assert {
        "recognition_findings_returns_empty_or_times_out",
        "progress_poll_remains_source_of_truth",
        "ui_keeps_running_state",
        "manual_review_controls_wait_for_review_entry",
    }.issubset(set(findings_timeout["steps"]))

    status_timeout = scenarios["insightface_status_probe_slow_does_not_block_reconnect_or_progress"]
    assert {
        "poll_insightface_status_slow_or_timeout",
        "progress_poll_remains_available",
        "ui_keeps_running_state",
        "worker_enqueue_or_component_failure_sets_explicit_terminal_phase",
    }.issubset(set(status_timeout["steps"]))


def test_usage_scenarios_cover_save_only_then_findings_for_reviewable_processes():
    save_only_findings_processes = {
        process_id
        for scenario in _scenarios()
        if "save_only" in " ".join(scenario["steps"]) and "findings" in scenario["modes"]
        for process_id in scenario["processes"]
    }
    expected = {
        process["id"]
        for process in _processes()
        for spec in process["modes"].values()
        if spec.get("reviewable")
    }

    assert expected.issubset(save_only_findings_processes)


def test_usage_scenarios_include_resume_cursors_for_review_restarts():
    scenarios = {scenario["id"]: scenario for scenario in _scenarios()}

    assert "resume_from_progress" in " ".join(scenarios["checks_interactive_review_resume_after_mutation"]["steps"])
    assert "skip_cursor" in " ".join(scenarios["face_match_interactive_mutation_resume"]["steps"])
    assert "scan_next_path_index" in " ".join(scenarios["face_frame_immediate_review_resume"]["steps"])
    assert "image_cursor" in " ".join(scenarios["recognition_unknown_immediate_apply_resume"]["steps"])
    assert "image_cursor" in " ".join(scenarios["recognition_assignment_from_checks_apply_resume"]["steps"])
    assert "face_cursor" in " ".join(scenarios["recognition_outlier_exclude_resume"]["steps"])


def test_recognition_unknown_matrix_covers_basic_review_workflow():
    chain = next(chain for chain in _chains() if chain["id"] == "face_match.recognition_unknown_delegate")
    assert chain["status_route"] == "/face_matching_findings_status"
    assert chain["findings_route"] == "/recognition_findings"
    assert chain["review_route"] == "/recognition_review"
    assert chain["apply_route"] == "/recognition_suggestions_apply"
    assert "/face_person_suggest" in chain["mutation_routes"]
    assert "/face_create_match" in chain["mutation_routes"]
    assert {"override_person_id", "override_person_name", "create_missing_person"}.issubset(set(chain["parameters"]))

    required_steps = {
        "show_finding",
        "show_oriented_face_box",
        "select_suggested_target",
        "select_alternate_target",
        "create_target",
        "save",
        "save_as",
        "refresh_findings_status",
        "refresh_cleanup_progress",
        "continue_search",
    }
    for process_id in ("face_match.recognition_analyze_unknown_faces", "cleanup.recognition_analyze_unknown_faces"):
        process = next(process for process in _processes() if process["id"] == process_id)
        workflow = set(process["modes"]["scan"].get("review_workflow", []))
        assert required_steps.issubset(workflow)

    scenarios = {scenario["id"]: scenario for scenario in _scenarios()}
    save_as_steps = set(scenarios["recognition_unknown_save_as_alternate_person_resume"]["steps"])
    assert {
        "face_person_suggest",
        "select_alternate_target",
        "save_as",
        "recognition_suggestions_apply_with_override_person",
        "refresh_cleanup_progress",
        "continue_search",
        "resume_existing_with_image_cursor",
    }.issubset(save_as_steps)
    create_steps = set(scenarios["recognition_unknown_create_missing_person_resume"]["steps"])
    assert {
        "show_oriented_face_box",
        "enter_new_target_name",
        "create_target",
        "recognition_suggestions_apply_with_create_missing_person",
        "refresh_cleanup_progress",
        "continue_search",
        "resume_existing_with_image_cursor",
    }.issubset(create_steps)


def test_recognition_unknown_status_route_reads_recognition_findings_source():
    chain = next(chain for chain in _chains() if chain["id"] == "face_match.recognition_unknown_delegate")
    assert chain["status_route"] == "/face_matching_findings_status"

    api_source = (PROJECT_DIR / "src" / "api" / "imgdata_api.py").read_text(encoding="utf-8")
    method = _function_source(api_source, "face_matching_findings_status")
    assert 'requested_action == "recognition_analyze_unknown_faces"' in method
    assert "IMGDATA.face_recognition.findings" in method
    assert "count=0" not in method
    assert '"count": 0' not in method


def test_status_process_matrix_delegates_point_to_existing_processes():
    ids = _process_ids()

    for process in _processes():
        delegate = process.get("delegates_to")
        if delegate:
            assert delegate in ids


def test_status_process_matrix_delegated_processes_declare_reconnect_status_boundaries():
    api_routes = _api_routes()
    chain_by_process = {
        process_id: chain
        for chain in _chains()
        for process_id in chain["processes"]
        if "progress_route" in chain
    }

    for process in _processes():
        if not process.get("delegates_to"):
            continue

        source_route = process.get("delegate_reconnect_source_route")
        foreign_status_routes = process.get("foreign_status_routes")

        assert source_route == "/cleanup_progress"
        assert isinstance(foreign_status_routes, list)
        assert foreign_status_routes
        assert source_route in api_routes
        assert set(foreign_status_routes).issubset(api_routes)
        assert source_route not in foreign_status_routes

        owner_chain = chain_by_process[process["delegates_to"]]
        assert owner_chain["progress_route"] == source_route


def test_status_process_matrix_scenarios_cover_delegated_foreign_status_neutralization():
    delegated_processes = {
        process["id"]
        for process in _processes()
        if process.get("delegates_to") and process.get("foreign_status_routes")
    }
    covered_processes = {
        process_id
        for scenario in _scenarios()
        if "foreign_status_route_neutralized" in scenario["steps"]
        for process_id in scenario["processes"]
    }

    assert delegated_processes.issubset(covered_processes)


def test_status_process_matrix_phases_are_explicit_and_terminal_complete():
    core_phases = set(_matrix()["core_phases"])

    for process in _processes():
        for mode, spec in process["modes"].items():
            assert mode in {"scan", "findings", "snapshot"}
            phases = set(spec.get("running_phases", [])) | set(spec.get("terminal_phases", []))
            assert phases
            assert {"failed", "blocked"} & phases or mode == "snapshot"
            if mode in {"scan", "findings"}:
                assert "stopped" in phases or "stopping" in phases
            for phase in phases:
                assert phase in core_phases or re.fullmatch(r"[a-z][a-z0-9_]*", phase)


def test_status_process_matrix_reviewable_processes_define_review_and_resume_contracts():
    reviewable = []

    for process in _processes():
        for mode, spec in process["modes"].items():
            if not spec.get("reviewable"):
                continue
            reviewable.append((process["id"], mode, spec))
            assert "review_required" in spec.get("terminal_phases", [])
            assert spec.get("progress_kind") in {"entries", "faces", "files", "images", "persons"}
            if mode == "scan":
                assert spec.get("resume_required_after_review") is True
                assert spec.get("resume_strategy") in {"cursor", "path_index_cursor"}
                assert spec.get("resume_cursor_coverage") is None
                if process["operation"] == "cleanup" and process["action"].startswith("recognition_"):
                    assert set(spec.get("resume_cursor_fields", [])) >= {"resume_start_person_index", "resume_person_id", "resume_progress_counts"}
            workflow = set(spec.get("review_workflow", []))
            assert {"show_finding", "save"}.issubset(workflow)
            if mode == "scan":
                assert {"refresh_cleanup_progress", "continue_search"}.issubset(workflow)
            if mode == "findings":
                assert "refresh_findings_status" in workflow

    assert reviewable


def test_status_process_matrix_assignment_review_workflows_cover_save_as_target_selection():
    assignment_process_ids = {
        "checks.recognition_check_person_assignments",
        "face_match.recognition_analyze_unknown_faces",
        "cleanup.recognition_analyze_unknown_faces",
        "cleanup.recognition_check_person_assignments",
    }
    assignment_chain_ids = {
        "checks.findings_review",
        "checks.recognition_assignment_delegate",
        "face_match.scan",
        "face_match.findings_load",
        "face_match.recognition_unknown_delegate",
        "cleanup.recognition_unknown",
        "cleanup.recognition_assignment",
    }

    for process in _processes():
        if process["id"] not in assignment_process_ids:
            continue
        for mode, spec in process["modes"].items():
            if not spec.get("reviewable"):
                continue
            workflow = set(spec.get("review_workflow", []))
            assert {"select_suggested_target", "select_alternate_target", "save_as"}.issubset(workflow)

    for chain in _chains():
        if chain["id"] not in assignment_chain_ids:
            continue
        routes = _chain_routes(chain)
        if "/recognition_suggestions_apply" in routes or "/checks_assign_face_person" in routes or "/face_assign_match" in routes:
            assert "/face_person_suggest" in routes


def test_status_process_matrix_all_declared_review_workflows_cover_basic_actions():
    workflows = []
    for process in _processes():
        for mode, spec in process["modes"].items():
            workflow = set(spec.get("review_workflow", []))
            if not workflow:
                continue
            workflows.append((process["id"], mode, workflow))
            assert {"show_finding", "save"}.issubset(workflow)
            assert "refresh_findings_status" in workflow
            if "select_alternate_target" in workflow:
                assert {"select_suggested_target", "save_as"}.issubset(workflow)
            if mode == "scan" and spec.get("resume_required_after_review"):
                assert {"refresh_cleanup_progress", "continue_search"}.issubset(workflow)

    assert workflows


def test_status_process_matrix_defines_supported_parameter_domains():
    domains = _matrix()["parameter_domains"]

    assert set(domains) == {"checks", "face_match", "cleanup"}
    assert domains["checks"]["selected_action"] == ["scan", "findings"]
    assert domains["cleanup"]["operation_mode"] == ["immediate", "save_only", "findings"]
    assert domains["cleanup"]["selection_mode"] == ["review_all", "safe_only", "exclude_confirmed"]
    assert domains["cleanup"]["resume_existing"] == [False, True]
    assert domains["cleanup"]["recognition_batch_size"] == [1, 8, 64]
    assert domains["face_match"]["preview_mode"] == ["photo", "face"]


def test_status_process_matrix_tracks_known_coverage_gaps():
    coverage = _matrix()["coverage"]

    assert coverage["status_payload_contracts"] == "covered"
    assert coverage["ui_action_coverage"] == "covered"
    assert coverage["parameter_cross_product_execution"] == "covered_by_representative_boundaries"
    assert coverage["review_resume_contracts"] == "covered"
    assert "known_gaps" not in coverage


def test_status_process_matrix_does_not_allow_weak_resume_strategies():
    for process in _processes():
        for mode, spec in process["modes"].items():
            assert spec.get("resume_cursor_coverage") is None
            assert spec.get("resume_strategy") not in {"resolved_id_filter", "entry_person_image_cursor"}


def test_unknown_face_recognition_uses_faces_as_primary_progress_unit():
    process_ids = {
        "face_match.recognition_analyze_unknown_faces",
        "cleanup.recognition_analyze_unknown_faces",
    }

    for process in _processes():
        if process["id"] not in process_ids:
            continue
        spec = process["modes"]["scan"]
        assert spec["progress_kind"] == "faces"
        assert set(spec.get("alternate_progress_kinds", [])) == {"images"}
        assert {"faces", "faces_remaining", "persons", "persons_remaining"}.issubset(set(spec.get("counters", [])))


def test_recognition_parameter_domains_match_normalization_contract():
    domains = _matrix()["parameter_domains"]["cleanup"]

    for operation_mode in domains["operation_mode"]:
        assert FaceRecognitionService.normalize_options({"operation_mode": operation_mode})["operation_mode"] == operation_mode
    for selection_mode in domains["selection_mode"]:
        assert FaceRecognitionService.normalize_options({"selection_mode": selection_mode})["selection_mode"] == selection_mode
    for resume_existing in domains["resume_existing"]:
        assert FaceRecognitionService.normalize_options({"resume_existing": resume_existing})["resume_existing"] is resume_existing
    for batch_size in domains["recognition_batch_size"]:
        assert FaceRecognitionService.normalize_options({"recognition_batch_size": batch_size})["recognition_batch_size"] == batch_size


def test_process_chain_parameters_are_declared_contract_terms():
    domains = _matrix()["parameter_domains"]
    known_parameters = {
        "action",
        "auto",
        "advance_current_result",
        "check_type",
        "external_worker_prefetch_batches",
        "findings_action",
        "force",
        "operation_mode",
        "recognize_persons",
        "recognition_batch_size",
        "refresh",
        "person_id",
        "person_name",
        "resume_existing",
        "resume_from_progress",
        "scan_next_path_index",
        "skip_face_ids",
        "skip_targets",
        "source_action",
        "source_mode",
            "targets",
            "override_person_id",
            "override_person_name",
            "create_missing_person",
        }
    for operation_domains in domains.values():
        known_parameters.update(operation_domains)

    for chain in _chains():
        assert set(chain.get("parameters", [])).issubset(known_parameters)


def test_status_builder_outputs_match_matrix_for_canonical_modes():
    builder = StatusPayloadBuilder()

    for process in _processes():
        operation = process["operation"]
        action = process["action"]
        if process.get("delegates_to"):
            continue
        for mode, spec in process["modes"].items():
            if operation == "checks":
                status = builder.checks_payload(
                    check_type=action,
                    source_mode=mode if mode != "snapshot" else "findings",
                    phase=(spec.get("running_phases") or spec.get("terminal_phases"))[0],
                    save_only=True,
                    files_scanned=3,
                    total_files=10,
                    findings_count=2,
                    resolved_count=1,
                    ignored_count=1,
                    skipped_count=1,
                    errors_count=1,
                    entries_current=2,
                    entries_total=5,
                )
            elif operation == "face_match":
                status = builder.face_match_payload(
                    action=action,
                    source_mode=mode if mode != "snapshot" else "scan",
                    phase=(spec.get("running_phases") or spec.get("terminal_phases"))[0],
                    save_only=True,
                    progress_kind=spec["progress_kind"],
                    current=3,
                    total=10,
                    findings_count=2,
                    transferred_count=1,
                    skipped_count=1,
                    errors_count=1,
                )
            elif operation == "file_analysis":
                status = builder.file_analysis_payload(
                    action=action,
                    mode=mode,
                    phase=(spec.get("running_phases") or spec.get("terminal_phases"))[0],
                    files_analyzed=3,
                    files_matched_total=10 if spec["progress_kind"] != "none" else 0,
                    files_seen_total=12,
                    faces_total=4,
                )
            else:
                if action.startswith("recognition_"):
                    continue
                status = builder.cleanup_payload(
                    action=action,
                    mode=mode,
                    phase=(spec.get("running_phases") or spec.get("terminal_phases"))[0],
                    persons_scanned=3 if spec["progress_kind"] == "persons" else 0,
                    persons_total=10 if spec["progress_kind"] == "persons" else 0,
                    files_scanned=3 if spec["progress_kind"] == "files" else 0,
                    total_files=10 if spec["progress_kind"] == "files" else 0,
                    entries_current=3 if spec["progress_kind"] == "entries" else 0,
                    entries_total=10 if spec["progress_kind"] == "entries" else 0,
                    persons_updated=1,
                    files_updated=1,
                    metadata_faces_updated=1,
                    errors_count=1,
                )

            assert status["schema_version"] == _matrix()["status_schema_version"]
            assert status["operation"] == operation
            assert status["action"] == (StatusPayloadBuilder.normalize_checks_type(action) if operation == "checks" else action)
            assert status["mode"] == (mode if mode != "snapshot" else status["mode"])
            allowed_kinds = {spec["progress_kind"], *spec.get("alternate_progress_kinds", [])}
            assert status["progress"]["kind"] in allowed_kinds
            expected_counters = spec.get("counters")
            if isinstance(expected_counters, dict):
                expected_counters = set(expected_counters.get("save_only", []) + expected_counters.get("interactive", []))
            else:
                expected_counters = set(expected_counters or [])
            assert set(_counter_keys(status)).issubset(expected_counters)


def test_recognition_resume_cursor_fields_are_matrix_backed():
    expected = {
        "cleanup.recognition_check_reference_outliers": {
            "resume_start_person_index",
            "resume_after_face_id",
            "resume_person_id",
            "resume_progress_counts",
        },
        "cleanup.recognition_analyze_unknown_faces": {
            "resume_start_person_index",
            "resume_after_image_id",
            "resume_person_id",
            "resume_progress_counts",
        },
        "cleanup.recognition_check_person_assignments": {
            "resume_start_person_index",
            "resume_after_image_id",
            "resume_person_id",
            "resume_progress_counts",
        },
    }

    for process_id, fields in expected.items():
        process = next(process for process in _processes() if process["id"] == process_id)
        assert set(process["modes"]["scan"].get("resume_cursor_fields", [])) == fields


def test_recognition_resume_cursor_fields_are_implemented_in_service():
    service_source = (PROJECT_DIR / "src" / "services" / "face_recognition_service.py").read_text(encoding="utf-8")
    recognition_processes = [
        process for process in _processes()
        if process["operation"] == "cleanup"
        and process["action"].startswith("recognition_")
        and process["modes"].get("scan", {}).get("reviewable")
    ]

    for process in recognition_processes:
        for field in process["modes"]["scan"].get("resume_cursor_fields", []):
            assert field in service_source
