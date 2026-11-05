"""
DCT / JPEG Analysis Detector — Phase 3.

For JPEG images:
- Extract DCT coefficient statistics per 8×8 block.
- Compute coefficient histograms.
- Analyze quantization tables.
- Detect blocking artifacts.

For non-JPEG images:
- status = NOT_APPLICABLE

Score semantics:
  DCT score = normalized coefficient energy concentration measure.
  NOT a manipulation probability.

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

DETECTOR_NAME = "dct_analysis"
DETECTOR_VERSION = "1.0.0"
BLOCK_SIZE = 8

DEFAULT_PARAMS = {
    "max_dimension": 1024,
}


class DCTAnalysisDetector(BaseDetector):
    """DCT-domain analysis for JPEG images."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.DCT

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
                        "reason": "DCT analysis is only applicable to JPEG images",
                        "image_format": pre.mode,
                        "is_jpeg": False,
                    },
                    execution_time_ms=elapsed_ms,
                )

            gray = pre.gray
            h, w = gray.shape

            # Pad to multiple of BLOCK_SIZE
            pad_h = (BLOCK_SIZE - h % BLOCK_SIZE) % BLOCK_SIZE
            pad_w = (BLOCK_SIZE - w % BLOCK_SIZE) % BLOCK_SIZE
            padded = np.pad(gray, ((0, pad_h), (0, pad_w)), mode="edge")

            # Compute DCT per 8×8 block
            dct_blocks = []
            for y in range(0, padded.shape[0], BLOCK_SIZE):
                for x in range(0, padded.shape[1], BLOCK_SIZE):
                    block = padded[y:y+BLOCK_SIZE, x:x+BLOCK_SIZE].astype(np.float64)
                    dct_block = cv2.dct(block)
                    dct_blocks.append(dct_block)

            if not dct_blocks:
                return _failed_result("No DCT blocks computed")

            all_dct = np.array(dct_blocks)  # (num_blocks, 8, 8)

            # Per-block DC coefficients
            dc_vals = all_dct[:, 0, 0]

            # AC energy (sum of squared AC coefficients per block)
            ac_energy = np.zeros(len(dct_blocks))
            for i, blk in enumerate(dct_blocks):
                ac = blk.copy()
                ac[0, 0] = 0
                ac_energy[i] = np.sum(ac ** 2)

            # Coefficient histogram (DC values)
            dc_hist, dc_bins = np.histogram(dc_vals, bins=32)

            # Quantization tables from PIL
            pil_img = PILImage.open(io.BytesIO(image_bytes))
            quant_tables = {}
            if hasattr(pil_img, "quantization"):
                for tid, table in pil_img.quantization.items():
                    quant_tables[f"table_{tid}"] = list(table)

            # Blocking artifact measure (difference at 8-pixel boundaries)
            block_diffs = []
            for y in range(BLOCK_SIZE, padded.shape[0] - 1, BLOCK_SIZE):
                diff = np.abs(padded[y, :].astype(np.float64) - padded[y-1, :].astype(np.float64))
                block_diffs.append(float(diff.mean()))
            for x in range(BLOCK_SIZE, padded.shape[1] - 1, BLOCK_SIZE):
                diff = np.abs(padded[:, x].astype(np.float64) - padded[:, x-1].astype(np.float64))
                block_diffs.append(float(diff.mean()))

            mean_block_diff = float(np.mean(block_diffs)) if block_diffs else 0.0

            # Score: normalized energy concentration (how much energy is in DC vs AC)
            total_energy = np.sum(dc_vals ** 2) + np.sum(ac_energy)
            dc_energy_ratio = float(np.sum(dc_vals ** 2) / total_energy) if total_energy > 0 else 0.0

            # Extract quantization table quality estimate
            quality_estimate = None
            if "table_0" in quant_tables and quant_tables["table_0"]:
                dc_val = quant_tables["table_0"][0]
                if dc_val > 0:
                    quality_estimate = min(100, max(1, int(100 - dc_val * 0.7)))

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=dc_energy_ratio,
                confidence=None,  # UNCALIBRATED
                details={
                    "status": "COMPLETED",
                    "score_semantics": "DC energy ratio (0-1, fraction of energy in DC coefficients, NOT a probability)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "num_blocks": len(dct_blocks),
                        "dc_mean": round(float(dc_vals.mean()), 2),
                        "dc_std": round(float(dc_vals.std()), 2),
                        "ac_energy_mean": round(float(ac_energy.mean()), 2),
                        "ac_energy_std": round(float(ac_energy.std()), 2),
                        "dc_energy_ratio": round(dc_energy_ratio, 4),
                        "blocking_artifact_measure": round(mean_block_diff, 4),
                        "dc_histogram": dc_hist.tolist(),
                        "quantization_tables": quant_tables if quant_tables else None,
                        "jpeg_quality_estimate": quality_estimate,
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "original_width": pre.original_width,
                        "original_height": pre.original_height,
                    },
                    "warnings": [],
                    "limitations": [
                        "DCT evidence depends on JPEG quality and encoder",
                        "Different encoders produce different coefficient distributions",
                        "DCT anomalies alone do not prove manipulation",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("DCT analysis failed", exc_info=True)
            return _failed_result(f"DCT error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.DCT,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[DCTAnalysisDetector] = None

def get_dct_analysis_detector() -> DCTAnalysisDetector:
    global _instance
    if _instance is None:
        _instance = DCTAnalysisDetector()
    return _instance
