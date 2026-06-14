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

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            app = InsightFaceDetector(model_name="buffalo_l", model_root=Path(tmpdir))._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0][0], "init")
        self.assertIn("allowed_modules", calls[0][1])
        self.assertEqual(calls[1][0], "init")
        self.assertEqual(calls[1][1]["name"], "buffalo_l")
        self.assertIn("root", calls[1][1])
        self.assertEqual(calls[2], ("prepare", {"ctx_id": -1, "det_size": (640, 640), "det_thresh": 0.5}))

    def test_insightface_detector_uses_package_default_when_model_name_is_empty(self):
        calls = []

        class DefaultFaceAnalysis:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def prepare(self, **kwargs):
                calls.append(("prepare", kwargs))

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = DefaultFaceAnalysis

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            InsightFaceDetector(model_root=Path(tmpdir))._load_app()

        self.assertEqual(calls[0][0], "init")
        self.assertNotIn("name", calls[0][1])
        self.assertEqual(calls[0][1]["allowed_modules"], ["detection"])
        self.assertIn("root", calls[0][1])

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

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            app = InsightFaceDetector(model_name="buffalo_l", model_root=Path(tmpdir))._load_app()

        self.assertIsInstance(app, LegacyFaceAnalysis)
        self.assertEqual(calls[0][0], "init")
        self.assertEqual(calls[0][1]["name"], "buffalo_l")
        self.assertEqual(calls[0][1]["allowed_modules"], ["detection"])
        self.assertIn("root", calls[0][1])
        self.assertEqual(calls[1], ("prepare", {"ctx_id": -1, "det_size": (640, 640), "det_thresh": 0.5}))
        self.assertEqual(calls[2], ("prepare", {"ctx_id": -1}))

    def test_insightface_detector_retries_prepare_without_unsupported_det_thresh(self):
        calls = []

        class FaceAnalysisWithoutThreshold:
            def __init__(self, **kwargs):
                pass

            def prepare(self, **kwargs):
                calls.append(kwargs)
                if "det_thresh" in kwargs:
                    raise TypeError("prepare() got an unexpected keyword argument 'det_thresh'")

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = FaceAnalysisWithoutThreshold

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            InsightFaceDetector(model_name="buffalo_l", model_root=Path(tmpdir), det_thresh=0.7)._load_app()

        self.assertEqual(calls, [
            {"ctx_id": -1, "det_size": (640, 640), "det_thresh": 0.7},
            {"ctx_id": -1, "det_size": (640, 640)},
        ])

    def test_insightface_detector_reports_empty_prepare_assertion_with_context(self):
        class BrokenFaceAnalysis:
            def __init__(self, **kwargs):
                pass

            def prepare(self, **kwargs):
                raise AssertionError()

        insightface_module = types.ModuleType("insightface")
        insightface_app_module = types.ModuleType("insightface.app")
        insightface_app_module.FaceAnalysis = BrokenFaceAnalysis

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(sys.modules, {
            "insightface": insightface_module,
            "insightface.app": insightface_app_module,
        }):
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                InsightFaceDetector(model_name="buffalo_l", model_root=Path(tmpdir))._load_app()

        message = str(ctx.exception)
        self.assertIn("insightface detection model could not be prepared", message)
        self.assertIn("model_name=buffalo_l", message)
        self.assertIn("AssertionError", message)

    def test_insightface_available_models_lists_installed_models_from_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            model_store = root / "models"
            (model_store / "buffalo_l").mkdir(parents=True)
            (model_store / "buffalo_l" / "det_10g.onnx").write_bytes(b"test")

            status = InsightFaceDetector.available_models(root)

        self.assertEqual(status["root"], str(root.resolve()))
        self.assertEqual(status["model_store"], str((root / "models").resolve()))
        installed = {item["name"]: item for item in status["models"]}
        self.assertEqual(set(installed), {"buffalo_l"})
        self.assertTrue(installed["buffalo_l"]["installed"])
        self.assertIn("det_10g.onnx", installed["buffalo_l"]["onnx_files"])

    def test_insightface_detector_reports_missing_model_directory_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = InsightFaceDetector(model_name="buffalo_l", model_root=Path(tmpdir))
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                detector._validate_model_files()

        self.assertIn("insightface model buffalo_l not found", str(ctx.exception))

    def test_insightface_detector_reports_missing_onnx_files_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "models" / "buffalo_l").mkdir(parents=True)
            detector = InsightFaceDetector(model_name="buffalo_l", model_root=root)
            with self.assertRaises(FaceDetectorUnavailable) as ctx:
                detector._validate_model_files()

        self.assertIn("no ONNX files found", str(ctx.exception))

    def test_insightface_detector_filters_score_and_minimum_size(self):
        class Image:
            shape = (100, 200, 3)

        class Detected:
            def __init__(self, bbox, score):
                self.bbox = bbox
                self.det_score = score

        class App:
            def get(self, image, max_num=0):
                self.max_num = max_num
                return [
                    Detected([20, 10, 80, 60], 0.9),
                    Detected([1, 1, 5, 5], 0.95),
                    Detected([100, 20, 180, 80], 0.2),
                ]

        cv2_module = types.ModuleType("cv2")
        cv2_module.imread = lambda path: Image()
        detector = InsightFaceDetector(
            det_thresh=0.5,
            max_num=7,
            min_width_ratio=0.1,
            min_height_ratio=0.1,
            min_area_ratio=0.01,
        )
        detector._app = App()

        with patch.dict(sys.modules, {"cv2": cv2_module}):
            faces = detector.detect(Path("/tmp/test.jpg"))

        self.assertEqual(len(faces), 1)
        self.assertEqual(detector._app.max_num, 7)
        self.assertEqual(faces[0]["score"], 0.9)


if __name__ == "__main__":
    unittest.main()
