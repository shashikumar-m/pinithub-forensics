"""
Error Level Analysis (ELA) Detector — Phase 3.

Algorithm:
1. Load the image.
2. Re-save it at a controlled JPEG quality.
3. Compare the original decoded pixels with the recompressed pixels.
4. Calculate pixel-level error.
5. Normalize the error map.

Score semantics:
  ELA score = mean normalized recompression error (0-1).
  This is NOT a probability of manipulation. It is a relative error statistic.

Limitations:
  - ELA is sensitive to JPEG quality of the original.
  - Low-quality originals produce less signal.
  - Natural high-frequency content can produce high ELA.
  - ELA alone is not sufficient to determine manipulation.

Version: 1.0.0
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

import numpy as np
from PIL import Image as PILImage

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "ela"
DETECTOR_VERSION = "1.0.0"

# Default parameters — configurable, not scattered magic numbers
DEFAULT_PARAMS = {
    "jpeg_quality": 85,
    "max_dimension": 1024,
}


class ELADetector(BaseDetector):
    """Error Level Analysis — recompression error forensic signal."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.ELA

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        import time
        start = time.perf_counter()

        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        if not image_bytes:
            return _failed_result("No image data provided")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        jpeg_quality = params["jpeg_quality"]
        max_dim = params["max_dimension"]

        warnings: list[str] = []

        try:
            # Preprocess — load original at controlled resolution
            pre = preprocess(image_bytes, max_dimension=max_dim)
            orig_rgb = pre.rgb

            # Re-save the decoded image at the target JPEG quality
            pil_orig = PILImage.fromarray(orig_rgb)
            recompress_buf = io.BytesIO()
            pil_orig.save(recompress_buf, format="JPEG", quality=jpeg_quality)
            recompress_buf.seek(0)
            recompressed_pil = PILImage.open(recompress_buf)
            recompressed_rgb = np.array(recompressed_pil, dtype=np.float64)

            # Calculate pixel-level absolute error
            error = np.abs(orig_rgb.astype(np.float64) - recompressed_rgb)

            # Per-pixel mean across channels
            error_map = error.mean(axis=2)  # H×W

            # Statistics
            mean_error = float(error_map.mean())
            median_error = float(np.median(error_map))
            max_error = float(error_map.max())
            p95 = float(np.percentile(error_map, 95))
            p99 = float(np.percentile(error_map, 99))

            # Normalize to 0-1 for score
            if max_error > 0:
                normalized_map = error_map / max_error
            else:
                normalized_map = error_map

            score = float(normalized_map.mean())

            # Generate artifact (ELA heatmap)
            artifact_bytes = encode_artifact_png(normalized_map)
            # In production, this would be stored in object storage
            # For now we encode as base64 in the result
            import base64
            artifact_b64 = base64.b64encode(artifact_bytes).decode("ascii")

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=score,
                confidence=None,  # UNCALIBRATED — no fabricated reliability
                map_path=None,  # Would be a storage path in production
                details={
                    "status": "COMPLETED",
                    "score_semantics": "mean normalized recompression error (0-1, NOT a probability)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "jpeg_quality_used": jpeg_quality,
                        "mean_error": round(mean_error, 4),
                        "median_error": round(median_error, 4),
                        "max_error": round(max_error, 4),
                        "p95_error": round(p95, 4),
                        "p99_error": round(p99, 4),
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "original_width": pre.original_width,
                        "original_height": pre.original_height,
                        "is_jpeg": pre.is_jpeg,
                    },
                    "artifact": {
                        "type": "ela_heatmap",
                        "format": "png",
                        "encoding": "base64",
                        "data": artifact_b64[:80] + "...",  # truncated for response
                        "full_size_bytes": len(artifact_bytes),
                    },
                    "warnings": warnings,
                    "limitations": [
                        "ELA is sensitive to original JPEG quality",
                        "Natural high-frequency content can produce high ELA",
                        "ELA alone cannot determine manipulation",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("ELA detector failed", exc_info=True)
            return _failed_result(f"ELA error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.ELA,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[ELADetector] = None

def get_ela_detector() -> ELADetector:
    global _instance
    if _instance is None:
        _instance = ELADetector()
    return _instance
