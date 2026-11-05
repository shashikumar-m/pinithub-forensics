"""
Image Comparison Pipeline — Phase 4.

Orchestrates:
  1. Initial compatibility check
  2. Feature extraction + matching + RANSAC (RegistrationDetector)
  3. Homography quality evaluation
  4. Image warping
  5. Photometric normalization
  6. Difference analysis
  7. Candidate region extraction

Returns structured forensic evidence.
NO final authenticity verdict is produced.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
import cv2

from app.detectors.registration import get_registration_detector
from app.detectors.difference_analysis import analyze_differences, encode_artifact_png
from app.io.preprocessing import preprocess

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"


def _compatibility_check(
    ref_bytes: bytes,
    sus_bytes: bytes,
    warnings: list,
) -> dict:
    """
    Basic preliminary compatibility check.
    Does NOT reject purely on dimension or format differences —
    a valid travelled copy may have any of these.
    """
    checks = {}
    try:
        ref_pre = preprocess(ref_bytes, max_dimension=2048)
        sus_pre = preprocess(sus_bytes, max_dimension=2048)

        checks["ref_decoded"] = True
        checks["sus_decoded"] = True
        checks["ref_dims"] = f"{ref_pre.original_width}×{ref_pre.original_height}"
        checks["sus_dims"] = f"{sus_pre.original_width}×{sus_pre.original_height}"

        # Aspect ratio comparison (informational, not a rejection criterion)
        ref_ar = ref_pre.original_width / max(1, ref_pre.original_height)
        sus_ar = sus_pre.original_width / max(1, sus_pre.original_height)
        ar_diff = abs(ref_ar - sus_ar) / max(ref_ar, 1e-6)
        checks["aspect_ratio_diff"] = round(ar_diff, 3)

        if ar_diff > 0.5:
            warnings.append(
                f"Significant aspect ratio difference ({ar_diff:.2f}); "
                "registration may have limited overlap"
            )

    except Exception as e:
        checks["ref_decoded"] = False
        checks["error"] = str(e)

    return checks


def run_comparison_pipeline(
    reference_bytes: bytes,
    suspect_bytes: bytes,
    params: Optional[dict] = None,
) -> dict:
    """
    Run full comparison pipeline.

    Args:
        reference_bytes: Protected original image bytes.
        suspect_bytes: Suspect copy image bytes.
        params: Optional parameter overrides for registration/diff analysis.

    Returns:
        Structured dict with pipeline results, registration result,
        diff analysis result, and artifacts.
    """
    start = time.perf_counter()
    warnings: list[str] = []
    params = params or {}

    # Step 1: Compatibility check
    compat = _compatibility_check(reference_bytes, suspect_bytes, warnings)
    if not compat.get("ref_decoded") or not compat.get("sus_decoded"):
        return _failed_pipeline("Image decoding failed during compatibility check", warnings)

    # Step 2: Registration
    reg_detector = get_registration_detector()
    try:
        reg_result = reg_detector.register(reference_bytes, suspect_bytes, params.get("registration"))
    except Exception as e:
        return _failed_pipeline(f"Registration failed: {e}", warnings)

    warnings.extend(reg_result.warnings)

    registration_dict = reg_result.to_dict()

    # If registration did not succeed, return without attempting diff analysis
    if reg_result.status != "COMPLETED":
        return {
            "pipeline": "comparison",
            "pipeline_version": PIPELINE_VERSION,
            "status": reg_result.status,
            "registration": registration_dict,
            "difference": None,
            "artifacts": {},
            "candidate_regions": [],
            "compatibility": compat,
            "warnings": warnings,
            "execution_time_ms": int((time.perf_counter() - start) * 1000),
            "note": "No difference analysis performed — registration did not succeed.",
        }

    # Step 3: Difference analysis
    diff_result = None
    artifacts: dict = {}
    candidate_regions: list = []

    if reg_result.homography_matrix:
        try:
            diff_result = analyze_differences(
                reference_bytes,
                suspect_bytes,
                reg_result.homography_matrix,
                params.get("difference"),
            )
            warnings.extend(diff_result.warnings)

            # Encode artifact maps as base64 for the response
            import base64

            if diff_result.abs_diff_map is not None:
                diff_png = encode_artifact_png(diff_result.abs_diff_map)
                artifacts["abs_diff_map"] = {
                    "type": "abs_diff_map",
                    "format": "png",
                    "encoding": "base64",
                    "data": base64.b64encode(diff_png).decode("ascii"),
                    "size_bytes": len(diff_png),
                }

            if diff_result.ssim_map is not None:
                ssim_png = encode_artifact_png(diff_result.ssim_map)
                artifacts["ssim_diff_map"] = {
                    "type": "ssim_diff_map",
                    "format": "png",
                    "encoding": "base64",
                    "data": base64.b64encode(ssim_png).decode("ascii"),
                    "size_bytes": len(ssim_png),
                }

            if diff_result.overlap_mask is not None:
                mask_png = encode_artifact_png(diff_result.overlap_mask, normalize=False)
                artifacts["overlap_mask"] = {
                    "type": "overlap_mask",
                    "format": "png",
                    "encoding": "base64",
                    "data": base64.b64encode(mask_png).decode("ascii"),
                    "size_bytes": len(mask_png),
                }

            candidate_regions = diff_result.candidate_regions

        except Exception as e:
            logger.warning("Difference analysis failed", exc_info=True)
            warnings.append(f"Difference analysis failed: {e}")

    exec_ms = int((time.perf_counter() - start) * 1000)

    diff_summary = None
    if diff_result and diff_result.status == "COMPLETED":
        diff_summary = {
            "status": diff_result.status,
            "mean_abs_diff": round(diff_result.mean_abs_diff, 4),
            "median_abs_diff": round(diff_result.median_abs_diff, 4),
            "p95_abs_diff": round(diff_result.p95_abs_diff, 4),
            "ssim_score": round(diff_result.ssim_score, 4) if diff_result.ssim_score is not None else None,
            "overlap_pixel_count": diff_result.overlap_pixel_count,
            "candidate_region_count": len(candidate_regions),
            "normalization_applied": diff_result.normalization_applied,
            "noise_floor": diff_result.noise_floor,
            "version": diff_result.version,
        }

    return {
        "pipeline": "comparison",
        "pipeline_version": PIPELINE_VERSION,
        "status": "COMPLETED" if diff_result and diff_result.status == "COMPLETED" else "COMPLETED_PARTIAL",
        "registration": registration_dict,
        "difference": diff_summary,
        "artifacts": artifacts,
        "candidate_regions": candidate_regions,
        "compatibility": compat,
        "warnings": warnings,
        "execution_time_ms": exec_ms,
        "note": (
            "These are forensic evidence results. "
            "Registration success ≠ authentic image. "
            "Differences found ≠ malicious edit. "
            "No final verdict is produced."
        ),
    }


def _failed_pipeline(error: str, warnings: list) -> dict:
    return {
        "pipeline": "comparison",
        "pipeline_version": PIPELINE_VERSION,
        "status": "FAILED",
        "registration": None,
        "difference": None,
        "artifacts": {},
        "candidate_regions": [],
        "compatibility": {},
        "warnings": warnings,
        "error": error,
        "execution_time_ms": 0,
    }
