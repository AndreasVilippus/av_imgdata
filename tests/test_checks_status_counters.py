from pathlib import Path


def test_checks_status_counter_ui_is_wired():
    view = Path('ui/src/views/ChecksView.vue').read_text(encoding='utf-8')
    mixin = Path('ui/src/mixins/checksMixin.js').read_text(encoding='utf-8')
    assert 'getRelevantChecksStatusCounters' in view
    assert 'face-match-status-counters' in view
    assert 'getRelevantChecksStatusCounters()' in mixin
    assert 'checks:counter_findings' in mixin
    assert 'progress.findings_count' in mixin


def test_checks_progress_backend_enricher_is_wired():
    api = Path('src/api/imgdata_api.py').read_text(encoding='utf-8')
    assert 'def _enrich_checks_progress_counters' in api
    assert '_enrich_checks_progress_counters(' in api
    assert 'getChecksFindingsStatus' in api


def test_checks_status_counter_translations_exist():
    enu = Path('ui/texts/enu/strings').read_text(encoding='utf-8')
    ger = Path('ui/texts/ger/strings').read_text(encoding='utf-8')
    assert 'counter_findings="Findings"' in enu
    assert 'counter_findings="Funde"' in ger
