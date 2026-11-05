"""
AI Forensics Segmentation Model — Phase 6 / Phase 9A.

Delegates to AIModelLoader from ai_model_registry.py.
This module is kept for backward compatibility.
"""
from __future__ import annotations

from typing import Optional
import numpy as np

from app.models.ai_model_registry import (
    AIModelLoader, get_ai_model_loader, reset_ai_model_loader,
    MODEL_VERSION, PREPROCESSING_VERSION, DEFAULT_THRESHOLD, IMG_SIZE, BACKBONE,
    MODEL_ID as MODEL_NAME, AIModelMetadata as ModelMetadata,
)

import os
from pathlib import Path

_model_instance: Optional[AIModelLoader] = None


class AISegmentationModel:
    """
    Backward-compatible wrapper around AIModelLoader.
    Existing code that calls get_ai_segmentation_model().predict() continues to work.
    """

    def __init__(self, weights_path: Optional[str] = None):
        self._weights_path = weights_path
        self._loader = AIModelLoader(weights_path)

    def _load(self) -> bool:
        return self._loader.load()

    @property
    def is_loaded(self) -> bool:
        return self._loader.is_available()

    def predict(self, image_bytes: bytes) -> Optional[np.ndarray]:
        return self._loader.predict(image_bytes)

    @property
    def metadata(self) -> ModelMetadata:
        return self._loader.get_metadata()

    # For hash access (tests)
    @property
    def _weights_sha256(self) -> Optional[str]:
        return self._loader._model_hash


def get_ai_segmentation_model(weights_path: Optional[str] = None) -> AISegmentationModel:
    global _model_instance
    if _model_instance is None or (weights_path and weights_path != _model_instance._weights_path):
        if weights_path is None:
            weights_path = os.environ.get("AI_WEIGHTS_PATH")
        _model_instance = AISegmentationModel(weights_path)
    return _model_instance


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
