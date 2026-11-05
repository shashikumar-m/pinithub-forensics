"""
Resampling / Interpolation Detection Detector — Phase 3.

Looks for periodic artifacts associated with resampling/interpolation:
- Uses the radon-transform / variance-based approach on the residual
- Detects periodic patterns in the PRNU-like residual

Score semantics:
  Resampling score = periodicity strength (0-1).
  NOT a probability of manipulation. A resized image is not necessarily edited.

Limitations:
  - Natural image content can contain periodic structures.
  - Small resizes may not produce detectable artifacts.
  - High-quality interpolation is harder to detect.

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

DETECTOR_NAME = "resampling"
DETECTOR_VERSION = "1.0.0"

DEFAULT_PARAMS = {
    "max_dimension": 512,
    "filter_size": 3,
    "num_angles": 16,
}


class ResamplingDetector(BaseDetector):
    """Resampling/interpolation artifact detector."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.KEYPOINT_MATCH  # closest existing category

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        import time
        start = time.perf_counter()

        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        if not image_bytes:
            return _failed_result("No image data provided")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        max_dim = params["max_dimension"]
        filter_size = params["filter_size"]
        num_angles = params["num_angles"]

        warnings: list[str] = []

        try:
            pre = preprocess(image_bytes, max_dimension=max_dim)
            gray = pre.gray.astype(np.float64)

            # Compute high-pass residual (row/col differences)
            residual = gray - cv2.medianBlur(gray.astype(np.uint8), filter_size).astype(np.float64)

            h, w = residual.shape

            # Row variance profile — look for periodicity
            row_vars = np.var(residual, axis=1)
            col_vars = np.var(residual, axis=0)

            # Autocorrelation of row/col variance to detect periodicity
            def autocorr_periodicity(signal):
                if len(signal) < 4:
                    return 0.0, 0
                signal = signal - signal.mean()
                ac = np.correlate(signal, signal, mode="full")
                ac = ac[len(ac)//2:]  # right half
                if ac[0] == 0:
                    return 0.0, 0
                ac_norm = ac / ac[0]
                # Find peaks (skip lag 0)
                peaks = []
                for i in range(2, len(ac_norm) - 1):
                    if ac_norm[i] > ac_norm[i-1] and ac_norm[i] > ac_norm[i+1] and ac_norm[i] > 0.1:
                        peaks.append((i, ac_norm[i]))
                if not peaks:
                    return 0.0, 0
                best_peak = max(peaks, key=lambda p: p[1])
                return float(best_peak[1]), int(best_peak[0])

            row_periodicity, row_period = autocorr_periodicity(row_vars)
            col_periodicity, col_period = autocorr_periodicity(col_vars)

            # Combined periodicity strength
            score = float(max(row_periodicity, col_periodicity))

            # Generate a simple evidence map (variance map)
            block_size = 16
            var_map = np.zeros((h, w), dtype=np.float64)
            for y in range(0, h, block_size):
                for x in range(0, w, block_size):
                    y2, x2 = min(y + block_size, h), min(x + block_size, w)
                    var_map[y:y2, x:x2] = np.var(residual[y:y2, x:x2])

            if var_map.max() > 0:
                var_map_norm = var_map / var_map.max()
            else:
                var_map_norm = var_map

            artifact_bytes = encode_artifact_png(var_map_norm)
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
                    "score_semantics": "periodicity strength (0-1, NOT a probability of manipulation)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "row_periodicity": round(row_periodicity, 4),
                        "row_period": row_period,
                        "col_periodicity": round(col_periodicity, 4),
                        "col_period": col_period,
                        "residual_mean": round(float(residual.mean()), 4),
                        "residual_std": round(float(residual.std()), 4),
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "original_width": pre.original_width,
                        "original_height": pre.original_height,
                    },
                    "artifact": {
                        "type": "resampling_variance_map",
                        "format": "png",
                        "encoding": "base64",
                        "data": artifact_b64[:80] + "...",
                        "full_size_bytes": len(artifact_bytes),
                    },
                    "warnings": warnings,
                    "limitations": [
                        "Natural image content can contain periodic structures",
                        "Small resizes may not produce detectable artifacts",
                        "High-quality interpolation is harder to detect",
                        "A resized image is not necessarily an edited image",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("Resampling detector failed", exc_info=True)
            return _failed_result(f"Resampling error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.KEYPOINT_MATCH,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[ResamplingDetector] = None

def get_resampling_detector() -> ResamplingDetector:
    global _instance
    if _instance is None:
        _instance = ResamplingDetector()
    return _instance
