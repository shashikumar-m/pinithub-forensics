"""
Noise Residual Analysis Detector — Phase 3.

Algorithm:
1. Load and preprocess the image.
2. Apply a denoising filter (median or Gaussian).
3. Compute residual = original - denoised.
4. Calculate local variance / MAD statistics.
5. Generate a residual inconsistency map.

Score semantics:
  Noise score = mean local residual variance (normalized 0-1).
  This measures local noise inconsistency, NOT manipulation probability.

Limitations:
  - Natural texture, shadows, edges affect residuals.
  - ISO noise and JPEG compression alter noise patterns.
  - Not all local noise differences indicate manipulation.

Version: 1.0.0
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import cv2

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "noise_residual"
DETECTOR_VERSION = "1.0.0"

DEFAULT_PARAMS = {
    "filter_type": "median",     # "median" or "gaussian"
    "filter_size": 5,            # kernel size
    "block_size": 32,            # local statistics block size
    "max_dimension": 1024,
}


class NoiseResidualDetector(BaseDetector):
    """Noise residual analysis — local noise inconsistency signal."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.NOISE_RESIDUAL

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        import time
        start = time.perf_counter()

        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        if not image_bytes:
            return _failed_result("No image data provided")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        filter_type = params["filter_type"]
        filter_size = params["filter_size"]
        block_size = params["block_size"]
        max_dim = params["max_dimension"]

        warnings: list[str] = []

        try:
            pre = preprocess(image_bytes, max_dimension=max_dim)
            gray = pre.gray

            # Apply denoising filter
            if filter_type == "median":
                denoised = cv2.medianBlur(gray, filter_size)
            elif filter_type == "gaussian":
                denoised = cv2.GaussianBlur(gray, (filter_size, filter_size), 0)
            else:
                denoised = cv2.medianBlur(gray, 5)
                warnings.append(f"Unknown filter '{filter_type}', using median")

            # Compute residual
            residual = gray.astype(np.float64) - denoised.astype(np.float64)

            # Local statistics using block-wise variance
            h, w = residual.shape
            bs = block_size
            var_map = np.zeros((h, w), dtype=np.float64)

            for y in range(0, h, bs):
                for x in range(0, w, bs):
                    y2 = min(y + bs, h)
                    x2 = min(x + bs, w)
                    block = residual[y:y2, x:x2]
                    local_var = np.var(block)
                    var_map[y:y2, x:x2] = local_var

            # Global statistics
            mean_var = float(var_map.mean())
            median_var = float(np.median(var_map))
            max_var = float(var_map.max())
            std_var = float(np.std(var_map))

            # MAD (Median Absolute Deviation)
            mad = float(np.median(np.abs(var_map - median_var)))

            # Normalize for score
            if max_var > 0:
                normalized_var = var_map / max_var
            else:
                normalized_var = var_map

            score = float(normalized_var.mean())

            # Generate artifact
            artifact_bytes = encode_artifact_png(normalized_var)
            import base64
            artifact_b64 = base64.b64encode(artifact_bytes).decode("ascii")

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=score,
                confidence=None,  # UNCALIBRATED
                details={
                    "status": "COMPLETED",
                    "score_semantics": "mean local residual variance (normalized 0-1, NOT a probability)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "mean_variance": round(mean_var, 6),
                        "median_variance": round(median_var, 6),
                        "max_variance": round(max_var, 6),
                        "std_variance": round(std_var, 6),
                        "mad": round(mad, 6),
                        "mean_residual": round(float(residual.mean()), 4),
                        "std_residual": round(float(residual.std()), 4),
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "original_width": pre.original_width,
                        "original_height": pre.original_height,
                    },
                    "artifact": {
                        "type": "noise_residual_map",
                        "format": "png",
                        "encoding": "base64",
                        "data": artifact_b64[:80] + "...",
                        "full_size_bytes": len(artifact_bytes),
                    },
                    "warnings": warnings,
                    "limitations": [
                        "Natural texture, shadows, edges affect residuals",
                        "ISO noise and JPEG compression alter noise patterns",
                        "Not all local noise differences indicate manipulation",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("Noise residual detector failed", exc_info=True)
            return _failed_result(f"Noise error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.NOISE_RESIDUAL,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[NoiseResidualDetector] = None

def get_noise_residual_detector() -> NoiseResidualDetector:
    global _instance
    if _instance is None:
        _instance = NoiseResidualDetector()
    return _instance
