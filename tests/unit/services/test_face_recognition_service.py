from types import SimpleNamespace

from services.face_recognition_service import FaceRecognitionService


class _Findings:
    def __init__(self):
        self.values = {}

    def readCheckFindings(self, finding_type):
        return self.values.get(finding_type, {})

    def writeCheckFindings(self, finding_type, payload):
        self.values[finding_type] = payload
        return True

    def readRuntimeState(self, state_type, state_key):
        return self.values.get((state_type, state_key), {})

    def writeRuntimeState(self, state_type, state_key, payload):
        self.values[(state_type, state_key)] = payload
        return True


def _service():
    file_analysis = _Findings()
    backend = SimpleNamespace(
        file_analysis=file_analysis,
        _configuredInsightFaceModelName=lambda: "test_model",
    )
    return FaceRecognitionService(backend), file_analysis


def test_profile_math_builds_normalized_centroid_and_medoid():
    centroid = FaceRecognitionService._centroid([[1.0, 0.0], [0.8, 0.2]])

    assert round(sum(value * value for value in centroid), 6) == 1.0
    assert FaceRecognitionService._medoid_index([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]]) == 1


def test_review_updates_only_persisted_recognition_finding():
    service, findings = _service()
    findings.values[service.FINDING_OUTLIERS] = {
        "entries": [{"outlier_id": "out-1", "selection_state": "review", "review_state": "suspected", "write_state": "internal_only"}]
    }

    result = service.update_review(action=service.ACTION_OUTLIERS, item_id="out-1", decision="excluded")

    assert result["updated"] is True
    entry = findings.values[service.FINDING_OUTLIERS]["entries"][0]
    assert entry["review_state"] == "excluded"
    assert entry["selection_state"] == "selected"


def test_apply_uses_persisted_selected_suggestion_and_existing_assign_orchestration():
    service, findings = _service()
    calls = []
    service.backend.assignMatchedFaceToKnownPerson = lambda **kwargs: calls.append(kwargs) or {"updated": True}
    findings.values[service.FINDING_SUGGESTIONS] = {
        "entries": [{
            "suggestion_id": "rec-1",
            "selection_state": "selected",
            "write_state": "pending",
            "unknown_face_id": 11,
            "best_person_id": 22,
            "best_person_name": "Person",
            "image_id": 33,
            "image_path": "/volume1/photo/a.jpg",
        }]
    }

    result = service.apply_suggestions(user_key="u", cookies={}, base_url="https://dsm")

    assert result["written_count"] == 1
    assert calls[0]["face_id"] == 11
    assert calls[0]["item_id"] == 33
    assert findings.values[service.FINDING_SUGGESTIONS]["entries"][0]["write_state"] == "written"


def test_excluding_outlier_updates_persisted_profile_immediately():
    service, findings = _service()
    options = service.normalize_options({})
    state_key = service._profile_state_key(options)
    findings.values[(service.PROFILE_STATE_TYPE, state_key)] = {
        "profiles": [{
            "person_id": 22,
            "references": [
                {"face_id": 1, "image_id": 10, "image_path": "/a.jpg", "bbox": {}, "embedding": [1.0, 0.0]},
                {"face_id": 2, "image_id": 11, "image_path": "/b.jpg", "bbox": {}, "embedding": [0.0, 1.0]},
            ],
        }]
    }
    findings.values[service.FINDING_OUTLIERS] = {
        "options": options,
        "entries": [{"outlier_id": "out-1", "face_id": 1, "selection_state": "review", "review_state": "suspected", "write_state": "internal_only"}],
    }

    service.update_review(action=service.ACTION_OUTLIERS, item_id="out-1", decision="excluded")

    profile = findings.values[(service.PROFILE_STATE_TYPE, state_key)]["profiles"][0]
    assert [entry["face_id"] for entry in profile["references"]] == [2]
    assert profile["used_count"] == 1
