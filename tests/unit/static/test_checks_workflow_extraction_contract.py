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
    assert "IMGDATA.checks_workflow.start_review(" in api
