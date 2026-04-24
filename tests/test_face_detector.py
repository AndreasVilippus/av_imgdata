import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile

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

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "buffalo_l").mkdir()
            (root / "buffalo_l" / "det_10g.onnx").write_bytes(b"test")

            with patch.dict(sys.modules, {
                "insightface": insightface_module,
                "insightface.app": insightface_app_module,
            }):
                app = InsightFaceDetector(model_root=root)._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0][0], "init")
        self.assertIn("allowed_modules", calls[0][1])
        self.assertEqual(calls[1][0], "init")
        self.assertEqual(calls[1][1]["name"], "buffalo_l")
        self.assertIn("root", calls[1][1])
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

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "buffalo_l").mkdir()
            (root / "buffalo_l" / "det_10g.onnx").write_bytes(b"test")

            with patch.dict(sys.modules, {
                "insightface": insightface_module,
                "insightface.app": insightface_app_module,
            }):
                app = InsightFaceDetector(model_root=root)._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0][0], "init")
        self.assertEqual(calls[0][1]["name"], "buffalo_l")
        self.assertEqual(calls[0][1]["allowed_modules"], ["detection"])
        self.assertIn("root", calls[0][1])
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

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "buffalo_l").mkdir()
            (root / "buffalo_l" / "det_10g.onnx").write_bytes(b"test")

            with patch.dict(sys.modules, {
                "insightface": insightface_module,
                "insightface.app": insightface_app_module,
            }):
                with self.assertRaises(FaceDetectorUnavailable) as ctx:
                    InsightFaceDetector(model_root=root)._load_app()

        message = str(ctx.exception)
        self.assertIn("insightface detection model could not be prepared", message)
        self.assertIn("model_name=buffalo_l", message)
        self.assertIn("AssertionError", message)

    def test_insightface_available_models_lists_installed_and_known_models(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "buffalo_l").mkdir()
            (root / "buffalo_l" / "det_10g.onnx").write_bytes(b"test")

            status = InsightFaceDetector.available_models(root)

        self.assertEqual(status["root"], str(root.resolve()))
        installed = {item["name"]: item for item in status["models"]}
        self.assertTrue(installed["buffalo_l"]["installed"])
        self.assertIn("det_10g.onnx", installed["buffalo_l"]["onnx_files"])
        self.assertFalse(installed["buffalo_m"]["installed"])

    def test_insightface_detector_reports_missing_model_directory_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = InsightFaceDetector(model_root=Path(tmpdir))
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                detector._validate_model_files()

        self.assertIn("insightface model buffalo_l not found", str(ctx.exception))

    def test_insightface_detector_reports_missing_onnx_files_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "buffalo_l").mkdir()
            detector = InsightFaceDetector(model_root=root)
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                detector._validate_model_files()

        self.assertIn("no ONNX files found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
