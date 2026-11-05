"""
Classical Forensic Detector Pipeline — Phase 3.

Runs all classical detectors in sequence and collects results.
Each detector failure is isolated — one failure does not stop others.

Pipeline:
  Protected image → Preprocessing → [ELA, Noise, DCT, DoubleComp,
  Resampling, JPEGGrid, CopyMove] → Detector outputs → Evidence artifacts

NO score fusion or final verdict — detectors produce independent evidence.
"""
from __future__ import annotations

import logging
from typing import Any

from app.detectors.ela import get_ela_detector
from app.detectors.noise_residual import get_noise_residual_detector
from app.detectors.dct_analysis import get_dct_analysis_detector
from app.detectors.jpeg_double_compression import get_jpeg_double_compression_detector
from app.detectors.resampling import get_resampling_detector
from app.detectors.jpeg_grid import get_jpeg_grid_detector
from app.detectors.copy_move import get_copy_move_detector

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"

DETECTORS = [
    ("ela", get_ela_detector),
    ("noise_residual", get_noise_residual_detector),
    ("dct_analysis", get_dct_analysis_detector),
    ("jpeg_double_compression", get_jpeg_double_compression_detector),
    ("resampling", get_resampling_detector),
    ("jpeg_grid", get_jpeg_grid_detector),
    ("copy_move", get_copy_move_detector),
]


def run_classical_pipeline(image_bytes: bytes, **kwargs: Any) -> dict:
    """
    Run all classical detectors on the given image bytes.

    Returns a dict with:
      - pipeline_version
      - results: list of DetectorResult.to_dict() per detector
      - completed: count of completed detectors
      - failed: count of failed detectors
      - not_applicable: count of NOT_APPLICABLE detectors
    """
    results = []
    completed = 0
    failed = 0
    not_applicable = 0

    for name, get_detector in DETECTORS:
        try:
            detector = get_detector()
            result = detector.timed_run("", image_bytes=image_bytes, **kwargs)
            rdict = result.to_dict()
            results.append(rdict)

            status = rdict.get("details", {}).get("status", "UNKNOWN")
            if status == "COMPLETED":
                completed += 1
            elif status == "NOT_APPLICABLE":
                not_applicable += 1
            elif status == "FAILED":
                failed += 1

        except Exception as e:
            logger.error(f"Detector {name} crashed: {e}", exc_info=True)
            results.append({
                "detector": name,
                "version": "unknown",
                "category": "unknown",
                "score": None,
                "confidence": None,
                "map_path": None,
                "details": {"status": "FAILED", "error": str(e)},
                "execution_time_ms": None,
            })
            failed += 1

    return {
        "pipeline": "classical_forensics",
        "pipeline_version": PIPELINE_VERSION,
        "results": results,
        "summary": {
            "total": len(results),
            "completed": completed,
            "failed": failed,
            "not_applicable": not_applicable,
        },
        "note": "These are independent forensic signals. No fusion or final verdict is produced.",
    }
