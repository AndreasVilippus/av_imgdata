from pathlib import Path


def test_save_only_flush_reconstructs_and_persists_running_progress():
    source = Path("src/services/checks_workflow_service.py").read_text(encoding="utf-8")
    start = source.find("def flush_saved_checks_findings")
    assert start >= 0
    end = source.find("return True", start)
    assert end > start
    helper = source[start:end]

    assert 'progress_key = backend._checksStateKey(user_key, check_type)' in helper
    assert 'backend.runtime_state.read_persisted("checks_progress", progress_key)' in helper
    assert 'progress["running"] = status not in {"finished", "stopped", "failed"}' in helper
    assert 'backend.runtime_state.persist("checks_progress", progress_key, dict(progress))' in helper


def test_checks_heartbeat_sets_running_true_and_persists():
    source = Path("src/imgdata.py").read_text(encoding="utf-8")
    start = source.find("def _updateChecksProgressHeartbeat")
    assert start >= 0
    end = source.find("\n    def ", start + 1)
    assert end > start
    method = source[start:end]

    assert 'progress["running"] = True' in method
    assert 'progress["finished"] = False' in method
    assert 'self.runtime_state.persist("checks_progress", key, dict(progress))' in method
