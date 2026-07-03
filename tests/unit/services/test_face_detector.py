import os
import sys
import unittest
from pathlib import Path
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

    def test_insightface_detector_constructor_rejects_python_integration(self):
        with self.assertRaises(FaceDetectorUnavailable) as ctx:
            InsightFaceDetector(model_name="buffalo_l")

        self.assertIn("Python InsightFace integration has been removed", str(ctx.exception))

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

    def test_insightface_available_models_ignores_model_directories_without_onnx(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "models" / "empty").mkdir(parents=True)

            status = InsightFaceDetector.available_models(root)

        self.assertEqual(status["models"], [])


if __name__ == "__main__":
    unittest.main()
