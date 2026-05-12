from pathlib import Path


def test_checks_start_route_attaches_status_to_result():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    start = source.find('async def checks_start')
    assert start >= 0
    end = source.find('@router.post("/checks_item")', start)
    assert end > start
    route = source[start:end]

    assert "_attach_checks_status_for_response" in route
    assert "source_mode" in route
    assert "check_type" in route


def test_checks_item_route_attaches_status_to_response_data():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    start = source.find('async def checks_item')
    assert start >= 0
    end = source.find('@router.post("/checks_progress")', start)
    assert end > start
    route = source[start:end]

    assert "_attach_checks_status_for_response" in route
    assert '"source_mode": "findings"' in route
    assert '"check_type": review_type' in route
    assert '"resolved_count": int(resolved.get("auto_applied_count") or 0)' in route


def test_checks_stop_route_attaches_status_to_result():
    source = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")
    start = source.find('async def checks_stop')
    assert start >= 0
    end = source.find('@router.post("/cleanup_start")', start)
    assert end > start
    route = source[start:end]

    assert "IMGDATA.requestStopChecks" in route
    assert "_attach_checks_status_for_response" in route
    assert "source_mode" in route
