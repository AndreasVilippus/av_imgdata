import os
import sys
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
import imgdata as imgdata_module
from imgdata import ImgDataService
from services.config_service import ConfigService


class InsightFaceFaceMatchTests(unittest.TestCase):
    def setUp(self):
        self.service = ImgDataService(SessionManager())

    def test_insightface_detection_becomes_unnamed_metadata_face(self):
        face = self.service._insightFaceDetectionToMetadataFace({
            "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
            "center": {"x": 0.2, "y": 0.35},
        })

        self.assertIsNotNone(face)
        self.assertEqual(face.name, "")
        self.assertEqual(face.source, "insightface")
        self.assertEqual(face.source_format, "INSIGHTFACE")
        self.assertAlmostEqual(face.x, 0.2)
        self.assertAlmostEqual(face.y, 0.35)
        self.assertAlmostEqual(face.w, 0.2)
        self.assertAlmostEqual(face.h, 0.3)

    def test_insightface_missing_face_candidate_is_not_discarded_for_missing_name(self):
        face = self.service._insightFaceDetectionToMetadataFace({
            "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
            "center": {"x": 0.2, "y": 0.35},
        })

        target, faces_by_format = self.service._selectMissingPhotosFaceCandidate(
            candidate_faces=[face],
            existing_photos_faces=[],
            require_name=False,
        )

        self.assertIs(target, face)
        self.assertEqual(faces_by_format, {"INSIGHTFACE": 1})

    def test_existing_missing_photos_face_flow_still_requires_name(self):
        face = self.service._insightFaceDetectionToMetadataFace({
            "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
            "center": {"x": 0.2, "y": 0.35},
        })

        target, faces_by_format = self.service._selectMissingPhotosFaceCandidate(
            candidate_faces=[face],
            existing_photos_faces=[],
            require_name=True,
        )

        self.assertIsNone(target)
        self.assertEqual(faces_by_format, {"INSIGHTFACE": 1})

    def test_empty_exception_progress_error_uses_exception_type(self):
        self.assertEqual(self.service._formatExceptionForProgress(AssertionError()), "AssertionError")

    def test_insightface_missing_face_result_preserves_next_transfer_progress(self):
        class FakeDetector:
            @classmethod
            def available_models(cls, model_root=None):
                return {"root": str(model_root or ""), "model_store": "", "models": []}

            def __init__(self, **kwargs):
                pass

            def detect(self, image_path):
                return [{
                    "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
                    "center": {"x": 0.2, "y": 0.35},
                }]

        self.service.pipPackagesStatus = lambda: {"packages": {"INSIGHTFACE": {"installed": True}}}
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: ["/volume1/photo/tests/image.jpg"]
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 123, "name": "image.jpg"}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: []

        with patch.object(imgdata_module, "InsightFaceDetector", FakeDetector):
            result = self.service.searchMissingPhotosFacesWithInsightFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                resume_cursor={
                    "action": "search_missing_faces_insightface",
                    "transferred_count": 10,
                    "auto": False,
                    "save_only": False,
                },
            )

        self.assertTrue(result["searched"])
        self.assertEqual(result["action"], "search_missing_faces_insightface")
        self.assertEqual(result["transferred_count"], 10)
        self.assertEqual(result["resume_cursor"]["transferred_count"], 10)
        self.assertEqual(result["resume_cursor"]["path_index"], 1)
        progress = self.service.getFaceMatchingProgress("user")
        self.assertEqual(progress["transferred_count"], 10)
        self.assertEqual(progress["resume_cursor"]["transferred_count"], 10)

    def test_insightface_missing_face_can_suggest_person_from_recognition_profile(self):
        class FakeEmbedder:
            @classmethod
            def available_models(cls, model_root=None):
                return {"root": str(model_root or ""), "model_store": "", "models": []}

            def __init__(self, **kwargs):
                pass

            def detect_and_embed(self, image_path):
                return [{
                    "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
                    "center": {"x": 0.2, "y": 0.35},
                    "embedding": [1.0, 0.0],
                }]

        self.service.pipPackagesStatus = lambda: {"packages": {"INSIGHTFACE": {"installed": True}}}
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: ["/volume1/photo/tests/image.jpg"]
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 123, "name": "image.jpg"}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: []
        self.service.face_recognition.profiles = lambda _options=None: {
            "profiles": [{
                "person_id": 42,
                "person_name": "Alice",
                "centroid_embedding": [1.0, 0.0],
                "medoid": {"thumbnail": {"cache_key": "thumb", "unit_id": 123}},
            }]
        }

        with patch.object(imgdata_module, "InsightFaceEmbedder", FakeEmbedder):
            result = self.service.searchMissingPhotosFacesWithInsightFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                recognize_persons=True,
            )

        self.assertTrue(result["searched"])
        self.assertTrue(result["recognition_enabled"])
        self.assertEqual(result["matched_person"]["id"], 42)
        self.assertEqual(result["matched_person"]["name"], "Alice")
        self.assertEqual(result["matched_person_id"], 42)
        self.assertEqual(result["source_name"], "Alice")
        self.assertEqual(result["metadata_face"]["name"], "Alice")
        self.assertTrue(result["resume_cursor"]["recognize_persons"])

    def test_insightface_missing_face_can_skip_unrecognized_person(self):
        class FakeEmbedder:
            @classmethod
            def available_models(cls, model_root=None):
                return {"root": str(model_root or ""), "model_store": "", "models": []}

            def __init__(self, **kwargs):
                pass

            def detect_and_embed(self, image_path):
                return [{
                    "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
                    "center": {"x": 0.2, "y": 0.35},
                    "embedding": [0.0, 1.0],
                }]

        self.service.pipPackagesStatus = lambda: {"packages": {"INSIGHTFACE": {"installed": True}}}
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = lambda base_path: ["/volume1/photo/tests/image.jpg"]
        self.service.photos.findFotoTeamItemByPath = lambda **kwargs: {"id": 123, "name": "image.jpg"}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: []
        self.service.face_recognition.profiles = lambda _options=None: {
            "profiles": [{
                "person_id": 42,
                "person_name": "Alice",
                "centroid_embedding": [1.0, 0.0],
                "medoid": {"thumbnail": {"cache_key": "thumb", "unit_id": 123}},
            }]
        }

        with patch.object(imgdata_module, "InsightFaceEmbedder", FakeEmbedder):
            result = self.service.searchMissingPhotosFacesWithInsightFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                recognize_persons=True,
                skip_unknown_persons=True,
            )

        self.assertTrue(result["searched"])
        self.assertIsNone(result["face"])
        self.assertEqual(result["findings_count"], 0)
        self.assertTrue(result["resume_cursor"]["recognize_persons"])
        self.assertTrue(result["resume_cursor"]["skip_unknown_persons"])
        self.assertEqual(len(result["resume_cursor"]["skip_targets"]), 1)

    def test_insightface_next_reuses_cached_file_list_and_resume_path_index(self):
        class FakeDetector:
            @classmethod
            def available_models(cls, model_root=None):
                return {"root": str(model_root or ""), "model_store": "", "models": []}

            def __init__(self, **kwargs):
                pass

            def detect(self, image_path):
                return [{
                    "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
                    "center": {"x": 0.2, "y": 0.35},
                }]

        paths = [
            "/volume1/photo/tests/first.jpg",
            "/volume1/photo/tests/second.jpg",
        ]
        list_calls = {"count": 0}

        def list_image_files(base_path):
            list_calls["count"] += 1
            if list_calls["count"] > 1:
                raise AssertionError("file list should be reused from cache")
            return paths

        self.service.pipPackagesStatus = lambda: {"packages": {"INSIGHTFACE": {"installed": True}}}
        self.service.core.getSharedFolder = lambda **kwargs: "/volume1/photo"
        self.service.files.listImageFiles = list_image_files
        self.service.photos.findFotoTeamItemByPath = lambda image_path, **kwargs: {"id": 1 if image_path.endswith("first.jpg") else 2}
        self.service.photos.list_faceFotoTeamItems = lambda **kwargs: []

        with patch.object(imgdata_module, "InsightFaceDetector", FakeDetector):
            first = self.service.searchMissingPhotosFacesWithInsightFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
            )
            second = self.service.searchMissingPhotosFacesWithInsightFace(
                user_key="user",
                cookies={},
                base_url="https://example.test",
                resume_cursor=first["resume_cursor"],
            )

        self.assertEqual(list_calls["count"], 1)
        self.assertEqual(first["image_path"], paths[0])
        self.assertEqual(first["resume_cursor"]["path_index"], 1)
        self.assertEqual(second["image_path"], paths[1])
        self.assertEqual(second["resume_cursor"]["path_index"], 2)

    def test_record_face_match_transfer_progress_preserves_insightface_resume_count(self):
        metadata_face = self.service._insightFaceDetectionToMetadataFace({
            "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5},
            "center": {"x": 0.2, "y": 0.35},
        }).to_dict()
        target_token = self.service._faceMatchTargetToken(
            image_path="/volume1/photo/tests/image.jpg",
            face=metadata_face,
        )
        self.service._setFaceMatchingProgress(
            "user",
            action="search_missing_faces_insightface",
            transferred_count=10,
            images_read=1444,
            resume_cursor={
                "action": "search_missing_faces_insightface",
                "path_index": 1444,
                "skip_targets": ["old-token"],
                "transferred_count": 10,
                "auto": False,
                "save_only": False,
            },
        )

        update = self.service.recordFaceMatchTransferProgress(
            "user",
            skip_targets=[target_token],
        )

        self.assertEqual(update["transferred_count"], 11)
        self.assertEqual(update["resume_cursor"]["transferred_count"], 11)
        self.assertEqual(update["resume_cursor"]["path_index"], 1444)
        self.assertEqual(update["resume_cursor"]["skip_targets"], ["old-token", target_token])
        progress = self.service.getFaceMatchingProgress("user")
        self.assertEqual(progress["transferred_count"], 11)
        self.assertEqual(progress["resume_cursor"]["transferred_count"], 11)

    def test_insightface_model_archive_installs_into_model_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConfigService(str(Path(tmpdir) / "config.json"))
            self.service.config = config
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w") as archive:
                archive.writestr("custom_model/det_10g.onnx", b"test")

            result = self.service.installInsightFaceModelArchive(
                archive_name="custom_model.zip",
                archive_bytes=archive_bytes.getvalue(),
            )

            model_root = Path(result["root"])
            model_store = model_root / "models"
            self.assertTrue((model_store / "custom_model" / "det_10g.onnx").exists())
            self.assertEqual(result["model_status"]["model_store"], str(model_store))
            models = {item["name"]: item for item in result["model_status"]["models"]}
            self.assertTrue(models["custom_model"]["installed"])

    def test_insightface_model_delete_removes_from_model_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConfigService(str(Path(tmpdir) / "config.json"))
            self.service.config = config
            model_dir = Path(tmpdir) / "insightface_models" / "models" / "custom_model"
            model_dir.mkdir(parents=True)
            (model_dir / "det_10g.onnx").write_bytes(b"test")

            result = self.service.deleteInsightFaceModel(model_name="custom_model")

            self.assertTrue(result["deleted"])
            self.assertFalse(model_dir.exists())


if __name__ == "__main__":
    unittest.main()
