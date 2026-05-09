from pathlib import Path


def test_checks_status_message_is_hidden_when_progress_card_shows_status():
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert ':status-text="vm.getChecksProgressStatusText()"' in view
    assert 'v-if="vm.shouldShowChecksStandaloneStatusMessage && vm.getChecksProgressStatusText()"' in view


def test_checks_standalone_status_message_visibility_helper_exists():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")

    assert "shouldShowChecksStandaloneStatusMessage()" in mixin
    assert "this.shouldShowChecksScanProgressCard" in mixin
    assert "this.shouldShowChecksListProgressCard" in mixin


def test_checks_progress_card_visibility_helpers_match_view_conditions():
    mixin = Path("ui/src/mixins/checksMixin.js").read_text(encoding="utf-8")
    view = Path("ui/src/views/ChecksView.vue").read_text(encoding="utf-8")

    assert "shouldShowChecksScanProgressCard()" in mixin
    assert "shouldShowChecksListProgressCard()" in mixin
    assert 'v-if="vm.shouldShowChecksScanProgressCard"' in view
    assert 'v-if="vm.shouldShowChecksListProgressCard"' in view
