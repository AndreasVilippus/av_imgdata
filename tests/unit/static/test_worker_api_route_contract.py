from pathlib import Path


def test_worker_api_action_runs_state_work_off_event_loop():
    source = Path("src/api/worker_api.py").read_text(encoding="utf-8")
    route_start = source.index("async def worker_action")
    route_source = source[route_start:]

    assert "async def _run_worker_api_call" in source
    assert "loop.run_in_executor(None, func)" in source
    assert "status_code, payload = await _run_worker_api_call(" in route_source
    assert "lambda: handle_worker_api_request(" in route_source
