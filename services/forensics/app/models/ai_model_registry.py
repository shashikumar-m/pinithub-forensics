"""
AI Model Registry — Phase 9A.

Clean abstraction for loading, validating, and querying the AI localization model.

Implements the interface:
  AIModelLoader.load()
  AIModelLoader.is_available()
  AIModelLoader.predict(image_bytes) -> np.ndarray | None
  AIModelLoader.get_metadata() -> dict

Model integrity:
  SHA-256 of the checkpoint file is computed on load.
  The hash is exposed via get_metadata() for reproducibility.

Safety:
  When weights are missing, corrupt, or incompatible:
    status = UNAVAILABLE
    probability = null
  NEVER returns fabricated scores.

Architecture constants are the single source of truth here.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---- Architecture constants ----
ARCHITECTURE = "UNet"
BACKBONE = "efficientnet-b3"
IMG_SIZE = (512, 512)
IN_CHANNELS = 3
CLASSES = 1
PREPROCESSING_VERSION = "v1"
NORMALIZATION = {
    "mean": [0.485, 0.456, 0.406],
    "std":  [0.229, 0.224, 0.225],
}
DEFAULT_THRESHOLD = 0.50
MODEL_ID = "ai_localization_unet_efficientnet_b3"
MODEL_VERSION = "v1.0.0"
TRAINING_DATASET = "ai_forensics_v1"


@dataclass
class AIModelMetadata:
    model_id: str
    model_version: str
    model_hash: Optional[str]          # SHA-256 of .pth file, None if unavailable
    architecture: str
    backbone: str
    input_size: tuple
    normalization: dict
    threshold: float
    preprocessing_version: str
    training_dataset: str
    is_available: bool
    load_error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["input_size"] = list(d["input_size"])
        return d


class AIModelLoader:
    """
    Clean model-loading abstraction for the AI localization detector.

    Usage:
        loader = AIModelLoader(weights_path)
        loader.load()
        if loader.is_available():
            prob_map = loader.predict(image_bytes)
            meta = loader.get_metadata()
    """

    def __init__(self, weights_path: Optional[str] = None):
        self._weights_path = weights_path
        self._model = None
        self._model_hash: Optional[str] = None
        self._load_error: Optional[str] = None
        self._loaded = False

    @classmethod
    def _resolve_relative_weights(cls, rel_path: str) -> Optional[Path]:
        p = Path(rel_path)
        if p.is_file():
            return p.resolve()
        current_file = Path(__file__).resolve()
        for parent in current_file.parents:
            cand = parent / rel_path
            if cand.is_file():
                return cand.resolve()
        return None

    def load(self) -> bool:
        """
        Attempt to load model weights.
        Returns True if weights loaded successfully, False otherwise.
        Never raises — all exceptions are caught and stored as load_error.
        """
        if self._loaded:
            return self._model is not None

        self._loaded = True  # mark as attempted regardless of outcome

        target_path = self._weights_path or os.environ.get("AI_WEIGHTS_PATH")
        if target_path and not Path(target_path).is_absolute() and not Path(target_path).exists():
            resolved = self._resolve_relative_weights(target_path)
            if resolved:
                target_path = str(resolved)

        if not target_path:
            self._load_error = "No weights path configured (set AI_WEIGHTS_PATH env var)"
            logger.warning(self._load_error)
            return False

        if not Path(target_path).exists():
            self._load_error = f"Weights file not found: {target_path}"
            logger.warning(self._load_error)
            return False

        try:
            import torch
            import segmentation_models_pytorch as smp
        except ImportError as e:
            self._load_error = f"Required package missing: {e}"
            logger.error(self._load_error)
            return False

        try:
            # Compute hash BEFORE loading (to detect corruption)
            self._model_hash = _sha256_file(target_path)

            # Build model structure
            model = smp.Unet(
                encoder_name=BACKBONE,
                encoder_weights=None,
                in_channels=IN_CHANNELS,
                classes=CLASSES,
                activation=None,
            )

            # Load weights
            state = torch.load(target_path, map_location="cpu",
                                weights_only=True)
            self._weights_path = target_path

            # Validate it's a state_dict (not a raw tensor, checkpoint wrapper, etc.)
            if not isinstance(state, dict):
                self._load_error = f"Unexpected checkpoint format: {type(state)}"
                logger.error(self._load_error)
                return False

            model.load_state_dict(state, strict=True)
            model.eval()
            self._model = model
            logger.info(f"AI model loaded from {self._weights_path} "
                        f"(SHA-256: {self._model_hash[:16]}...)")
            return True

        except Exception as e:
            self._load_error = f"Model load failed: {type(e).__name__}: {e}"
            self._model = None
            self._model_hash = None
            logger.error(self._load_error, exc_info=True)
            return False

    def is_available(self) -> bool:
        """Returns True only if model is loaded and ready for inference."""
        if not self._loaded:
            self.load()
        return self._model is not None

    def predict(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """
        Run inference on image bytes.
        Returns H×W float32 probability map in [0,1], or None if unavailable.
        The original image bytes are NEVER modified.
        """
        if not self.is_available():
            return None

        try:
            import torch
            from PIL import Image as PILImage

            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            img_resized = img.resize(IMG_SIZE, PILImage.BILINEAR)
            arr = np.array(img_resized, dtype=np.float32) / 255.0
            mean = np.array(NORMALIZATION["mean"], dtype=np.float32)
            std  = np.array(NORMALIZATION["std"],  dtype=np.float32)
            arr = (arr - mean) / std
            tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)

            with torch.no_grad():
                logits = self._model(tensor)          # (1, 1, H, W)
                probs = torch.sigmoid(logits).squeeze().numpy()

            return probs.astype(np.float32)           # (H, W)

        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            return None

    def get_metadata(self) -> AIModelMetadata:
        """Return complete model metadata for reproducibility."""
        return AIModelMetadata(
            model_id=MODEL_ID,
            model_version=MODEL_VERSION,
            model_hash=self._model_hash,
            architecture=ARCHITECTURE,
            backbone=BACKBONE,
            input_size=IMG_SIZE,
            normalization=NORMALIZATION,
            threshold=DEFAULT_THRESHOLD,
            preprocessing_version=PREPROCESSING_VERSION,
            training_dataset=TRAINING_DATASET,
            is_available=self.is_available(),
            load_error=self._load_error,
        )


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- Module-level singleton ----
_loader: Optional[AIModelLoader] = None

def get_ai_model_loader(weights_path: Optional[str] = None) -> AIModelLoader:
    """
    Return a module-level AIModelLoader singleton.
    Reset when weights_path changes (e.g. during testing).
    """
    global _loader
    if _loader is None or (weights_path and weights_path != _loader._weights_path):
        _loader = AIModelLoader(weights_path)
    return _loader

def reset_ai_model_loader() -> None:
    """Reset the singleton — used in tests when changing weights path."""
    global _loader
    _loader = None
