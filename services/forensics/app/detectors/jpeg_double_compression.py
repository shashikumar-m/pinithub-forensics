"""
JPEG Double-Compression / Quantization Evidence Detector — Phase 3.

Looks for evidence consistent with JPEG recompression:
- Quantization table analysis (non-standard table entries)
- DCT coefficient histogram gaps (double quantization artifacts)
- Quality estimate vs. observed coefficient distribution

Score semantics:
  Double-compression score = histogram gap indicator (0-1).
  NOT a probability. Records evidence of possible recompression only.

Limitations:
  - Unknown JPEG history makes definitive claims impossible.
  - Social media processing introduces recompression.
  - Screenshots may not show typical patterns.

Version: 1.0.0
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

import numpy as np
import cv2
from PIL import Image as PILImage

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess

logger = logging.getLogger(__name__)

DETECTOR_NAME = "jpeg_double_compression"
DETECTOR_VERSION = "1.0.0"
BLOCK_SIZE = 8

DEFAULT_PARAMS = {
    "max_dimension": 1024,
    "histogram_bins": 64,
}


class JPEGDoubleCompressionDetector(BaseDetector):
    """Evidence detector for possible JPEG recompression."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.JPEG_DOUBLE_COMPRESSION

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        import time
        start = time.perf_counter()

        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        if not image_bytes:
            return _failed_result("No image data provided")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}

        try:
            pre = preprocess(image_bytes, max_dimension=params["max_dimension"])

            if not pre.is_jpeg:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=None,
                    confidence=None,
                    details={
                        "status": "NOT_APPLICABLE",
                        "reason": "Double-compression analysis is only applicable to JPEG images",
                        "is_jpeg": False,
                    },
                    execution_time_ms=elapsed_ms,
                )

            gray = pre.gray
            h, w = gray.shape
            pad_h = (BLOCK_SIZE - h % BLOCK_SIZE) % BLOCK_SIZE
            pad_w = (BLOCK_SIZE - w % BLOCK_SIZE) % BLOCK_SIZE
            padded = np.pad(gray, ((0, pad_h), (0, pad_w)), mode="edge")

            # Collect quantized DCT coefficients (first AC coefficient index (0,1) and (1,0))
            ac_coeffs_01 = []
            ac_coeffs_10 = []
            dc_coeffs = []

            for y in range(0, padded.shape[0], BLOCK_SIZE):
                for x in range(0, padded.shape[1], BLOCK_SIZE):
                    block = padded[y:y+BLOCK_SIZE, x:x+BLOCK_SIZE].astype(np.float64)
                    dct = cv2.dct(block)
                    dc_coeffs.append(dct[0, 0])
                    ac_coeffs_01.append(dct[0, 1])
                    ac_coeffs_10.append(dct[1, 0])

            dc_coeffs = np.array(dc_coeffs)
            ac_01 = np.array(ac_coeffs_01)
            ac_10 = np.array(ac_coeffs_10)

            # Histogram analysis — look for gaps (double quantization signature)
            num_bins = params["histogram_bins"]
            dc_hist, _ = np.histogram(np.round(dc_coeffs), bins=num_bins)
            ac_hist_01, _ = np.histogram(np.round(ac_01), bins=num_bins)
            ac_hist_10, _ = np.histogram(np.round(ac_10), bins=num_bins)

            # Gap analysis: count zero bins between non-zero bins
            def count_histogram_gaps(hist):
                gaps = 0
                in_gap = False
                for v in hist:
                    if v == 0:
                        in_gap = True
                    elif in_gap:
                        gaps += 1
                        in_gap = False
                return gaps

            dc_gaps = count_histogram_gaps(dc_hist)
            ac01_gaps = count_histogram_gaps(ac_hist_01)
            ac10_gaps = count_histogram_gaps(ac_hist_10)
            total_gaps = dc_gaps + ac01_gaps + ac10_gaps
            max_possible_gaps = num_bins * 3

            # Score: normalized gap indicator
            score = float(total_gaps / max_possible_gaps) if max_possible_gaps > 0 else 0.0

            # Quantization tables from PIL
            pil_img = PILImage.open(io.BytesIO(image_bytes))
            quant_tables = {}
            if hasattr(pil_img, "quantization"):
                for tid, table in pil_img.quantization.items():
                    quant_tables[f"table_{tid}"] = {
                        "table_id": tid,
                        "first_values": list(table)[:8],
                    }

            # Quality estimate
            quality_estimate = None
            if hasattr(pil_img, "quantization") and 0 in pil_img.quantization:
                dc_val = pil_img.quantization[0][0]
                if dc_val > 0:
                    quality_estimate = min(100, max(1, int(100 - dc_val * 0.7)))

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=score,
                confidence=None,  # UNCALIBRATED
                details={
                    "status": "COMPLETED",
                    "score_semantics": "histogram gap indicator (0-1, NOT a probability of double compression)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "dc_histogram_gaps": dc_gaps,
                        "ac01_histogram_gaps": ac01_gaps,
                        "ac10_histogram_gaps": ac10_gaps,
                        "total_gaps": total_gaps,
                        "dc_coeff_mean": round(float(dc_coeffs.mean()), 2),
                        "dc_coeff_std": round(float(dc_coeffs.std()), 2),
                        "ac01_coeff_mean": round(float(ac_01.mean()), 4),
                        "ac01_coeff_std": round(float(ac_01.std()), 4),
                        "quantization_tables": quant_tables if quant_tables else None,
                        "jpeg_quality_estimate": quality_estimate,
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "is_jpeg": True,
                    },
                    "warnings": [],
                    "limitations": [
                        "Unknown JPEG history makes definitive claims impossible",
                        "Social media processing introduces recompression",
                        "Screenshots may not show typical patterns",
                        "This records EVIDENCE of possible recompression, not proof",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("Double-compression detector failed", exc_info=True)
            return _failed_result(f"Double-compression error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.JPEG_DOUBLE_COMPRESSION,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[JPEGDoubleCompressionDetector] = None

def get_jpeg_double_compression_detector() -> JPEGDoubleCompressionDetector:
    global _instance
    if _instance is None:
        _instance = JPEGDoubleCompressionDetector()
    return _instance
