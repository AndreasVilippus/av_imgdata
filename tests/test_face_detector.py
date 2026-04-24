import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("src"))

from services.face_detector import FaceDetectorUnavailable, InsightFaceDetector, OpenCvHaarFaceDetector, default_haar_cascade_path


class FaceDetectorTests(unittest.TestCase):
    def test_default_haar_cascade_model_is_bundled(self):
        model_path = default_haar_cascade_path()

        self.assertTrue(model_path.exists())
        self.assertGreater(model_path.stat().st_size, 100_000)

    def test_optional_face_detection_requirements_are_separate_from_insightface(self):
        requirements_path = Path("src/requirements-optional-face-detection.txt")

        self.assertTrue(requirements_path.exists())
        self.assertIn("opencv-python-headless", requirements_path.read_text(encoding="utf-8"))

    def test_haar_detector_finds_face_on_test_image(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.skipTest("opencv-python-headless is not installed")

        faces = OpenCvHaarFaceDetector().detect(Path("tests/images/test_raw.jpg"), min_neighbors=3)

        self.assertGreaterEqual(len(faces), 1)
        first = faces[0]
        self.assertGreater(first["w"], 20)
        self.assertGreater(first["h"], 20)
        self.assertGreaterEqual(first["bbox"]["x1"], 0.0)
        self.assertGreaterEqual(first["bbox"]["y1"], 0.0)
        self.assertLessEqual(first["bbox"]["x2"], 1.0)
        self.assertLessEqual(first["bbox"]["y2"], 1.0)

    def test_insightface_detector_supports_legacy_face_analysis_constructor(self):
        calls = []

        class LegacyFaceAnalysis:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))
                if "allowed_modules" in kwargs:
                    raise TypeError("__init__() got an unexpected keyword argument 'allowed_modules'")

            def prepare(self, **kwargs):
                calls.append(("prepare", kwargs))

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = LegacyFaceAnalysis

        with patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            app = InsightFaceDetector()._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0][0], "init")
        self.assertIn("allowed_modules", calls[0][1])
        self.assertEqual(calls[1], ("init", {"name": "buffalo_l"}))
        self.assertEqual(calls[2], ("prepare", {"ctx_id": -1, "det_size": (640, 640)}))

    def test_insightface_detector_supports_legacy_prepare_signature(self):
        calls = []

        class LegacyFaceAnalysis:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def prepare(self, **kwargs):
                calls.append(("prepare", kwargs))
                if "det_size" in kwargs:
                    raise TypeError("prepare() got an unexpected keyword argument 'det_size'")

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = LegacyFaceAnalysis

        with patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            app = InsightFaceDetector()._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0], ("init", {"name": "buffalo_l", "allowed_modules": ["detection"]}))
        self.assertEqual(calls[1], ("prepare", {"ctx_id": -1, "det_size": (640, 640)}))
        self.assertEqual(calls[2], ("prepare", {"ctx_id": -1}))

    def test_insightface_detector_reports_empty_prepare_assertion_with_context(self):
        class BrokenFaceAnalysis:
            def __init__(self, **kwargs):
                pass

            def prepare(self, **kwargs):
                raise AssertionError()

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = BrokenFaceAnalysis

        with patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                InsightFaceDetector()._load_app()

        message = str(ctx.exception)
        self.assertIn("insightface detection model could not be prepared", message)
        self.assertIn("model_name=buffalo_l", message)
        self.assertIn("AssertionError", message)


if __name__ == "__main__":
    unittest.main()
