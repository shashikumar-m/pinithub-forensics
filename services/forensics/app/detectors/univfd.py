"""
Universal Fake Detection (UnivFD) detector module.
Implements the CVPR 2023 paper:
"Towards Universal Fake Image Detectors that Generalize Across Generative Models"
(Ojha et al., UC Davis / Wisconsin AI Vision).

Uses a frozen pre-trained CLIP-ViT visual feature extractor coupled with a trained linear probe.
Captures universal semantic and high-level unnatural artifacts across unseen diffusion and GAN models.
"""
import io
import logging
import os
import time
from typing import Any, Optional

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torchvision import transforms

from app.detectors.base import BaseDetector, DetectorResult, DetectorCategory

logger = logging.getLogger(__name__)

DETECTOR_NAME = "univfd"
DETECTOR_VERSION = "1.0.0"

# Standard CLIP Vision Transform parameters
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
CLIP_SIZE = (224, 224)

# Global singleton cache for model and probe
_CLIP_BACKBONE: Optional[Any] = None
_UNIVFD_PROBE: Optional[nn.Linear] = None
_LOAD_FAILED = False


def _get_default_weights_path() -> str:
    """Finds univfd_fc_weights.pth relative to project root or forensics service."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(current_dir, "..", "..", "..", "models", "univfd_fc_weights.pth"),
        os.path.join(current_dir, "..", "..", "models", "univfd_fc_weights.pth"),
        os.path.join(os.getcwd(), "models", "univfd_fc_weights.pth"),
    ]
    for c in candidates:
        norm = os.path.normpath(c)
        if os.path.exists(norm):
            return norm
    return os.path.normpath(candidates[0])


def _load_univfd_components() -> tuple[Optional[Any], Optional[nn.Linear]]:
    """Loads and caches the frozen CLIP ViT backbone and trained linear probe."""
    global _CLIP_BACKBONE, _UNIVFD_PROBE, _LOAD_FAILED
    if _LOAD_FAILED:
        return None, None
    if _CLIP_BACKBONE is not None and _UNIVFD_PROBE is not None:
        return _CLIP_BACKBONE, _UNIVFD_PROBE

    try:
        import timm

        weights_path = os.environ.get("UNIVFD_WEIGHTS_PATH") or _get_default_weights_path()
        if not os.path.exists(weights_path):
            logger.warning("UnivFD linear probe weights not found at %s", weights_path)
            return None, None

        logger.info("Initializing UnivFD CLIP-ViT backbone...")
        backbone = timm.create_model("vit_base_patch16_clip_224.openai", pretrained=True, num_classes=0)
        backbone.eval()

        probe = nn.Linear(768, 1)
        state_dict = torch.load(weights_path, map_location="cpu")
        probe.load_state_dict(state_dict)
        probe.eval()

        _CLIP_BACKBONE = backbone
        _UNIVFD_PROBE = probe
        logger.info("UnivFD components successfully initialized from %s", weights_path)
        return _CLIP_BACKBONE, _UNIVFD_PROBE

    except Exception as e:
        logger.error("Failed to load UnivFD model: %s", e)
        _LOAD_FAILED = True
        return None, None


class UnivFDDetector(BaseDetector):
    """
    Universal Fake Detector using CLIP-ViT visual embeddings and linear probing.
    Detects universal synthetic artifacts across unseen image generators.
    """

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.AI_GENERATED

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        start = time.perf_counter()
        image_bytes: Optional[bytes] = kwargs.get("image_bytes")

        if not image_bytes and image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            except OSError as e:
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=None,
                    details={"status": "UNAVAILABLE", "error": f"Could not read image: {e}"},
                    execution_time_ms=int((time.perf_counter() - start) * 1000),
                )

        if not image_bytes:
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=None,
                details={"status": "UNAVAILABLE", "error": "No image data provided"},
                execution_time_ms=int((time.perf_counter() - start) * 1000),
            )

        backbone, probe = _load_univfd_components()
        if backbone is None or probe is None:
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=None,
                details={
                    "status": "UNAVAILABLE",
                    "error": "UnivFD CLIP backbone or linear probe weights not loaded.",
                },
                execution_time_ms=int((time.perf_counter() - start) * 1000),
            )

        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            transform = transforms.Compose([
                transforms.Resize(CLIP_SIZE, interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.ToTensor(),
                transforms.Normalize(mean=CLIP_MEAN, std=CLIP_STD),
            ])
            tensor = transform(pil_img).unsqueeze(0)

            with torch.no_grad():
                feat = backbone(tensor)
                logit = probe(feat)
                raw_prob = float(torch.sigmoid(logit).item())

            status = "AI_GENERATED" if raw_prob >= 0.50 else "AUTHENTIC"
            evidence: list[str] = [
                f"Universal generator feature space probability: {raw_prob:.4f}",
                f"Backbone: OpenAI CLIP ViT-B/16 (768-dim semantic projection)",
                "Model: UnivFD (CVPR 2023 Universal Fake Detection)",
            ]

            if raw_prob >= 0.80:
                evidence.append("Strong multi-modal semantic divergence consistent with synthetic diffusion/GAN generation.")
            elif raw_prob <= 0.20:
                evidence.append("Visual semantic tokens align with authentic natural photographic distributions.")

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=round(raw_prob, 4),
                confidence=0.85,
                details={
                    "status": status,
                    "score": round(raw_prob, 4),
                    "logit": round(float(logit.item()), 4),
                    "feature_dim": 768,
                    "evidence": evidence,
                },
                execution_time_ms=int((time.perf_counter() - start) * 1000),
            )

        except Exception as e:
            logger.error("UnivFD inference failed: %s", e)
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=None,
                details={"status": "ERROR", "error": str(e)},
                execution_time_ms=int((time.perf_counter() - start) * 1000),
            )


def get_univfd_detector() -> UnivFDDetector:
    return UnivFDDetector()

