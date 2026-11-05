"""
JPEG Grid / Blocking Analysis Detector — Phase 3.

Analyzes 8×8 block structure and grid artifacts:
- Blocking strength at 8-pixel boundaries
- Local blocking inconsistency
- Grid discontinuities

For non-JPEG images: status = NOT_APPLICABLE

Score semantics:
  Grid score = mean blocking artifact strength (0-1 normalized).
  NOT a manipulation probability.

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

DETECTOR_NAME = "jpeg_grid"
DETECTOR_VERSION = "1.0.0"
BLOCK_SIZE = 8

DEFAULT_PARAMS = {
    "max_dimension": 1024,
}


class JPEGGridDetector(BaseDetector):
    """JPEG 8×8 grid / blocking artifact analyzer."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.DCT  # closest existing category

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
                        "reason": "JPEG grid analysis is only applicable to JPEG images",
                        "is_jpeg": False,
                    },
                    execution_time_ms=elapsed_ms,
                )

            gray = pre.gray.astype(np.float64)
            h, w = gray.shape

            # Compute horizontal and vertical blocking differences
            h_diffs = []
            v_diffs = []

            # At 8-pixel boundaries
            for y in range(BLOCK_SIZE, h - 1, BLOCK_SIZE):
                diff = np.abs(gray[y, :] - gray[y - 1, :])
                h_diffs.append(float(diff.mean()))

            for x in range(BLOCK_SIZE, w - 1, BLOCK_SIZE):
                diff = np.abs(gray[:, x] - gray[:, x - 1])
                v_diffs.append(float(diff.mean()))

            # Non-boundary differences (control: differences at non-multiple-of-8 positions)
            h_diffs_ctrl = []
            v_diffs_ctrl = []

            for y in range(BLOCK_SIZE + 1, h - 1, BLOCK_SIZE):
                diff = np.abs(gray[y, :] - gray[y - 1, :])
                h_diffs_ctrl.append(float(diff.mean()))

            for x in range(BLOCK_SIZE + 1, w - 1, BLOCK_SIZE):
                diff = np.abs(gray[:, x] - gray[:, x - 1])
                v_diffs_ctrl.append(float(diff.mean()))

            mean_h_block = float(np.mean(h_diffs)) if h_diffs else 0.0
            mean_v_block = float(np.mean(v_diffs)) if v_diffs else 0.0
            mean_h_ctrl = float(np.mean(h_diffs_ctrl)) if h_diffs_ctrl else 0.0
            mean_v_ctrl = float(np.mean(v_diffs_ctrl)) if v_diffs_ctrl else 0.0

            # Blocking ratio: boundary diff / non-boundary diff
            h_ratio = mean_h_block / mean_h_ctrl if mean_h_ctrl > 0 else 1.0
            v_ratio = mean_v_block / mean_v_ctrl if mean_v_ctrl > 0 else 1.0

            # Blocking inconsistency: variance of boundary diffs
            h_inconsistency = float(np.std(h_diffs)) if h_diffs else 0.0
            v_inconsistency = float(np.std(v_diffs)) if v_diffs else 0.0

            # Score: normalized blocking strength
            all_diffs = h_diffs + v_diffs
            max_diff = max(all_diffs) if all_diffs else 1.0
            score = float((mean_h_block + mean_v_block) / (2 * max_diff)) if max_diff > 0 else 0.0

            # Build a block-level map showing boundary strength
            block_map = np.zeros((h, w), dtype=np.float64)
            for y in range(BLOCK_SIZE, h - 1, BLOCK_SIZE):
                block_map[y, :] = np.abs(gray[y, :] - gray[y - 1, :])
            for x in range(BLOCK_SIZE, w - 1, BLOCK_SIZE):
                block_map[:, x] = np.maximum(block_map[:, x], np.abs(gray[:, x] - gray[:, x - 1]))

            if block_map.max() > 0:
                block_map_norm = block_map / block_map.max()
            else:
                block_map_norm = block_map

            artifact_bytes = encode_artifact_png(block_map_norm)
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
                    "score_semantics": "normalized blocking strength (0-1, NOT a probability)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "mean_horizontal_blocking": round(mean_h_block, 4),
                        "mean_vertical_blocking": round(mean_v_block, 4),
                        "mean_horizontal_control": round(mean_h_ctrl, 4),
                        "mean_vertical_control": round(mean_v_ctrl, 4),
                        "horizontal_ratio": round(h_ratio, 4),
                        "vertical_ratio": round(v_ratio, 4),
                        "horizontal_inconsistency": round(h_inconsistency, 4),
                        "vertical_inconsistency": round(v_inconsistency, 4),
                        "num_h_boundaries": len(h_diffs),
                        "num_v_boundaries": len(v_diffs),
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "is_jpeg": True,
                    },
                    "artifact": {
                        "type": "jpeg_grid_map",
                        "format": "png",
                        "encoding": "base64",
                        "data": artifact_b64[:80] + "...",
                        "full_size_bytes": len(artifact_bytes),
                    },
                    "warnings": [],
                    "limitations": [
                        "Blocking artifacts are expected in all JPEG images",
                        "Inconsistency between regions is more informative than absolute values",
                        "Grid analysis alone does not prove manipulation",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("JPEG grid detector failed", exc_info=True)
            return _failed_result(f"JPEG grid error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.DCT,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[JPEGGridDetector] = None

def get_jpeg_grid_detector() -> JPEGGridDetector:
    global _instance
    if _instance is None:
        _instance = JPEGGridDetector()
    return _instance
