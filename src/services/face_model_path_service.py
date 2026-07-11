#!/usr/bin/env python3
"""Single source of truth for InsightFace model paths."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from services.face_detector import InsightFaceDetector
from services.native_face_processor_service import NativeFaceProcessorService


class FaceModelPathService:
    """Resolve the model root/store/name used by local and external workers.

    The configured native processor values have precedence.  When MODEL_ROOT is
    empty, DSM installations use the package data directory's existing
    ``insightface_models`` root, which is also the fallback supplied to the local
    native processor.
    """

    DEFAULT_MODEL_NAME = "buffalo_l"

    def __init__(
        self,
        config_service: Any,
        *,
        package_var: Optional[Path] = None,
        native_processor: Optional[NativeFaceProcessorService] = None,
    ):
        self.config_service = config_service
        self.package_var = (
            Path(package_var)
            if package_var is not None
            else Path(os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
        ).resolve()
        self.native_processor = native_processor or NativeFaceProcessorService(config_service)

    def default_model_root(self) -> Path:
        return (self.package_var / "insightface_models").resolve()

    def model_root(self) -> Path:
        return self.native_processor.model_root(self.default_model_root())

    def model_store(self) -> Path:
        return InsightFaceDetector.model_store_dir(self.model_root())

    def model_name(self) -> str:
        return self.native_processor.model_name(self.DEFAULT_MODEL_NAME) or self.DEFAULT_MODEL_NAME

    def model_dir(self, model_name: str = "") -> Path:
        return (self.model_store() / (str(model_name or "").strip() or self.model_name())).resolve()

    def resolve(self, model_name: str = "") -> Dict[str, Any]:
        name = str(model_name or "").strip() or self.model_name()
        root = self.model_root()
        store = InsightFaceDetector.model_store_dir(root)
        return {
            "model_root": root,
            "model_store": store,
            "model_name": name,
            "model_dir": (store / name).resolve(),
        }
