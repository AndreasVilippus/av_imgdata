from pathlib import Path


def test_checks_lifecycle_is_owned_by_checks_workflow_service():
    backend = Path("src/imgdata.py").read_text(encoding="utf-8")
    workflow = Path("src/services/checks_workflow_service.py").read_text(encoding="utf-8")
    api = Path("src/api/imgdata_api.py").read_text(encoding="utf-8")

    assert "from services.checks_workflow_service import ChecksWorkflowService" in backend
    assert "self.checks_workflow = ChecksWorkflowService(self, ImgDataOperationError)" in backend
    assert "def startChecksReview(" not in backend
    assert "def startChecksScanDiscovery(" not in backend
    assert "def _runChecksScan(" not in backend
    assert "def start_review(" in workflow
    assert "def start_scan(" in workflow
    assert "def _run_scan(" in workflow
    assert "def get_candidate_paths(" in workflow
    assert "def invalidate_candidate_paths_cache(" in workflow
    assert "self._candidate_paths_cache" in workflow
    assert "self._checks_candidate_paths_cache" not in backend
    assert "return self.checks_workflow.get_candidate_paths(" in backend
    assert "self.checks_workflow.invalidate_candidate_paths_cache(user_key, check_type)" in backend
    assert "def build_resume_cursor(" in workflow
    assert "def build_scan_payload(" in workflow
    assert "def count_open_scan_findings(" in workflow
    assert "def trusted_resume_cursor(" in workflow
    assert "def search_next_item(" in workflow
    assert "def write_findings(" in workflow
    assert "def resume_saved_entries(" in workflow
    assert "def append_unique_findings(" in workflow
    assert "def write_persisted_findings_status(" in workflow
    assert "def get_finding_entries(" in workflow
    assert "def refresh_finding_entries(" in workflow
    assert "def refresh_finding_entries_for_image(" in workflow
    assert "def refresh_scan_progress_for_image(" in workflow
    assert "def resolve_checks_review_entry(" in workflow
    assert "def resolve_checks_review_entry_core(" in workflow
    assert "def exclude_checks_entries_by_tokens(" in workflow
    assert "def rebuild_checks_entries_for_image_after_mutation(" in workflow
    assert "return self.checks_workflow.build_resume_cursor(" in backend
    assert "return self.checks_workflow.build_scan_payload(" in backend
    assert "return self.checks_workflow.count_open_scan_findings(" in backend
    assert "return self.checks_workflow.trusted_resume_cursor(" in backend
    assert "return self.checks_workflow.search_next_item(" in backend
    assert "return self.checks_workflow.write_findings(" in backend
    assert "return self.checks_workflow.resume_saved_entries(" in backend
    assert "return self.checks_workflow.append_unique_findings(" in backend
    assert "self.checks_workflow.write_persisted_findings_status(" in backend
    assert "return self.checks_workflow.get_finding_entries(" in backend
    assert "return self.checks_workflow.refresh_finding_entries(" in backend
    assert "return self.checks_workflow.refresh_finding_entries_for_image(" in backend
    assert "return self.checks_workflow.refresh_scan_progress_for_image(" in backend
    assert "return self.checks_workflow.resolve_checks_review_entry(" in backend
    assert "return self.checks_workflow.resolve_checks_review_entry_core(" in backend
    assert "return self.checks_workflow.exclude_checks_entries_by_tokens(" in backend
    assert "return self.checks_workflow.rebuild_checks_entries_for_image_after_mutation(" in backend
    assert "IMGDATA.checks_workflow.start_review(" in api
