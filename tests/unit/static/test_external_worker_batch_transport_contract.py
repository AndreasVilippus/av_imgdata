from pathlib import Path


def test_external_worker_api_loop_materializes_batch_shared_paths():
    source = Path("worker/src/api_loop.cpp").read_text(encoding="utf-8")

    assert 'type == "face_native_detect_batch"' in source
    assert 'type == "face_native_embed_batch"' in source
    assert 'extract_json_array(*payload, "image_paths")' in source
    assert "safe_relative_path(value" in source
    assert "join_path(config.path_base_dir, relative)" in source
    assert 'replace_json_array(payload, "image_paths"' in source
    assert "shared_path batch requires a non-empty image_paths string array" in source


def test_external_worker_api_loop_does_not_sleep_after_claimed_job():
    source = Path("worker/src/api_loop.cpp").read_text(encoding="utf-8")

    assert 'if (status != "claimed")' in source
    assert "sleep_for(std::chrono::seconds(config.poll_interval_seconds))" in source


def test_external_worker_batch_dispatch_is_separate_from_pipeline():
    service = Path("src/services/external_worker_batch_processor_service.py").read_text(encoding="utf-8")
    integration = Path("src/services/external_worker_gui_integration.py").read_text(encoding="utf-8")

    assert "execute_face_detect_batch" in service
    assert "execute_face_embed_batch" in service
    assert '"face_native_detect_batch"' in service
    assert '"face_native_embed_batch"' in service
    assert "execute_face_embed_batch" in integration
    assert "pipeline" not in service.lower()


def test_warm_runtime_capability_is_not_a_worker_api_job():
    service = Path("src/services/worker_api_service.py").read_text(encoding="utf-8")
    processor_schema = Path("processor_contract/schemas/face-native-job-input.schema.json").read_text(encoding="utf-8")

    assert 'NON_JOB_CAPABILITIES = {"warm_processor_worker"}' in service
    assert '"warm_processor_worker"' not in processor_schema
