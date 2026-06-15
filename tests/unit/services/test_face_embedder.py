from pathlib import Path
from unittest.mock import patch

from services.face_embedder import InsightFaceEmbedder


class _Face:
    bbox = [10, 20, 50, 80]
    det_score = 0.9
    normed_embedding = [0.25, 0.75]


class _App:
    def get(self, _image, max_num=0):
        return [_Face()]


def test_embedder_returns_normalized_bbox_and_embedding():
    embedder = InsightFaceEmbedder(model_name="test")
    embedder._app = _App()
    image = type("Image", (), {"shape": (100, 200, 3)})()

    with patch.dict("sys.modules", {"cv2": type("Cv2", (), {"imread": staticmethod(lambda _path: image)})}):
        result = embedder.detect_and_embed(Path("/tmp/image.jpg"))

    assert result == [{
        "bbox": {"x1": 0.05, "y1": 0.2, "x2": 0.25, "y2": 0.8},
        "score": 0.9,
        "embedding": [0.25, 0.75],
    }]


def test_embed_matched_face_requires_minimum_iou():
    embedder = InsightFaceEmbedder(model_name="test")
    candidate = {
        "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4},
        "embedding": [1.0],
    }
    with patch.object(embedder, "detect_and_embed", return_value=[candidate]):
        matched = embedder.embed_matched_face(
            Path("/tmp/image.jpg"),
            {"x1": 0.12, "y1": 0.12, "x2": 0.38, "y2": 0.38},
            min_iou=0.5,
        )
        missed = embedder.embed_matched_face(
            Path("/tmp/image.jpg"),
            {"x1": 0.8, "y1": 0.8, "x2": 0.9, "y2": 0.9},
            min_iou=0.5,
        )

    assert matched and matched["iou"] >= 0.5
    assert missed is None
