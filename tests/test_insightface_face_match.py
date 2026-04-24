import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from api.session_manager import SessionManager
from imgdata import ImgDataService


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


if __name__ == "__main__":
    unittest.main()
