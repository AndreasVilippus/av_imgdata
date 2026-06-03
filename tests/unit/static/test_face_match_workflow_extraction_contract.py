from pathlib import Path


def test_face_match_lifecycle_is_owned_by_face_match_workflow_service():
    backend = Path("src/imgdata.py").read_text(encoding="utf-8")
    workflow = Path("src/services/face_match_workflow_service.py").read_text(encoding="utf-8")

    assert "from services.face_match_workflow_service import FaceMatchWorkflowService" in backend
    assert "self.face_match_workflow = FaceMatchWorkflowService(self)" in backend
    assert "self._face_matching_candidate_paths_cache" not in backend
    assert "def start_discovery(" in workflow
    assert "def _run_face_matching(" in workflow
    assert "def get_candidate_paths(" in workflow
    assert "def invalidate_candidate_paths_cache(" in workflow
    assert "def request_stop(" in workflow
    assert "def should_stop(" in workflow
    assert "def get_findings(" in workflow
    assert "def resume_saved_entries(" in workflow
    assert "def append_unique_finding(" in workflow
    assert "def write_persisted_findings_status(" in workflow
    assert "def write_findings(" in workflow
    assert "def should_flush_findings(" in workflow
    assert "def persist_findings_entries(" in workflow
    assert "def get_finding_entries(" in workflow
    assert "def get_finding_entries_locked(" in workflow
    assert "def remove_metadata_entry(" in workflow
    assert "def remove_metadata_entry_unlocked(" in workflow
    assert "def remove_entry(" in workflow
    assert "def remove_entry_unlocked(" in workflow
    assert "self._candidate_paths_cache" in workflow
    assert "target=self._run_face_matching" in workflow
    assert "return self.face_match_workflow.start_discovery(" in backend
    assert "self.face_match_workflow._run_face_matching(" in backend
    assert "return self.face_match_workflow.get_candidate_paths(" in backend
    assert "return self.face_match_workflow.request_stop(user_key)" in backend
    assert "return self.face_match_workflow.should_stop(user_key)" in backend
    assert "return self.face_match_workflow.get_findings()" in backend
    assert "return self.face_match_workflow.resume_saved_entries(" in backend
    assert "return self.face_match_workflow.append_unique_finding(entries, entry)" in backend
    assert "self.face_match_workflow.write_persisted_findings_status(" in backend
    assert "self.face_match_workflow.write_findings(" in backend
    assert "return self.face_match_workflow.should_flush_findings(" in backend
    assert "self.face_match_workflow.persist_findings_entries(" in backend
    assert "return self.face_match_workflow.get_finding_entries(" in backend
    assert "return self.face_match_workflow.get_finding_entries_locked(" in backend
    assert "return self.face_match_workflow.remove_metadata_entry(" in backend
    assert "return self.face_match_workflow.remove_metadata_entry_unlocked(" in backend
    assert "return self.face_match_workflow.remove_entry(" in backend
    assert "return self.face_match_workflow.remove_entry_unlocked(" in backend
