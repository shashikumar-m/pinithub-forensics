"""
Difference Analysis — Phase 4.

After successful registration, computes pixel-level differences between
the reference original and the aligned suspect image.

Implements:
  A. Absolute pixel difference
  B. SSIM-based difference
  C. Local difference statistics
  D. Noise-floor-aware suppression
  E. Candidate changed region extraction

Critical:
  - Differences are computed ONLY inside the valid overlap region.
  - Not every pixel difference is an edit.
  - JPEG compression, resize, brightness changes produce natural differences.

Version: 1.0.0
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import cv2
from PIL import Image as PILImage

from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DIFF_ANALYSIS_VERSION = "1.0.0"

DEFAULT_DIFF_PARAMS = {
    "noise_floor": 8.0,           # suppress differences below this (0-255 scale)
    "region_min_pixels": 100,     # minimum region size to report
    "region_threshold": 25.0,     # mean diff above this to flag as candidate
    "normalization": "luminance",  # "luminance", "none"
    "ssim_window_size": 11,
    "max_dimension": 1024,
}


@dataclass
class DiffAnalysisResult:
    """Result of difference analysis between aligned images."""
    status: str
    mean_abs_diff: float = 0.0
    median_abs_diff: float = 0.0
    p95_abs_diff: float = 0.0
    ssim_score: Optional[float] = None
    overlap_pixel_count: int = 0
    abs_diff_map: Optional[np.ndarray] = None    # H×W float32
    ssim_map: Optional[np.ndarray] = None         # H×W float32
    overlap_mask: Optional[np.ndarray] = None     # H×W uint8 (255 = valid)
    aligned_suspect: Optional[np.ndarray] = None  # H×W×3 uint8
    candidate_regions: list = field(default_factory=list)
    normalization_applied: str = "none"
    noise_floor: float = 0.0
    version: str = DIFF_ANALYSIS_VERSION
    warnings: list = field(default_factory=list)
    error: Optional[str] = None


def analyze_differences(
    reference_bytes: bytes,
    suspect_bytes: bytes,
    homography_matrix: list,
    params: Optional[dict] = None,
) -> DiffAnalysisResult:
    """
    Compute visual differences between reference and aligned suspect.

    Args:
        reference_bytes: Protected original image bytes.
        suspect_bytes: Suspect image bytes.
        homography_matrix: 3×3 homography from registration (reference → suspect space).
        params: Configuration overrides.
    """
    p = {**DEFAULT_DIFF_PARAMS, **(params or {})}
    warnings: list[str] = []

    try:
        ref_pre = preprocess(reference_bytes, max_dimension=p["max_dimension"])
        sus_pre = preprocess(suspect_bytes, max_dimension=p["max_dimension"])
    except Exception as e:
        return DiffAnalysisResult(status="FAILED", error=f"Preprocessing failed: {e}")

    H = np.array(homography_matrix, dtype=np.float64)
    ref_rgb = ref_pre.rgb
    sus_rgb = sus_pre.rgb
    h, w = ref_rgb.shape[:2]

    # Warp suspect into reference coordinate system
    try:
        aligned_suspect = cv2.warpPerspective(sus_rgb, H, (w, h))
    except Exception as e:
        return DiffAnalysisResult(status="FAILED", error=f"Warp failed: {e}")

    # Build overlap mask — only compare where the aligned suspect has valid pixels
    sus_mask = np.ones((sus_pre.height, sus_pre.width), dtype=np.uint8) * 255
    overlap_mask = cv2.warpPerspective(sus_mask, H, (w, h))
    overlap_mask = (overlap_mask > 128).astype(np.uint8) * 255

    overlap_pixels = int(np.count_nonzero(overlap_mask))

    if overlap_pixels < 100:
        return DiffAnalysisResult(
            status="INCONCLUSIVE",
            warnings=["Insufficient overlap for difference analysis"],
            overlap_mask=overlap_mask,
        )

    # Photometric normalization
    norm_method = p.get("normalization", "none")
    if norm_method == "luminance":
        ref_rgb, aligned_suspect = _luminance_normalize(ref_rgb, aligned_suspect, overlap_mask)
        warnings.append("Luminance normalization applied — brightness differences suppressed")
    elif norm_method != "none":
        warnings.append(f"Unknown normalization '{norm_method}', skipping")
        norm_method = "none"

    # Absolute difference (only in overlap region)
    abs_diff_full = np.abs(
        ref_rgb.astype(np.float32) - aligned_suspect.astype(np.float32)
    ).mean(axis=2)  # H×W

    # Mask to overlap only
    abs_diff = abs_diff_full.copy()
    abs_diff[overlap_mask == 0] = 0

    # Noise floor suppression — documented, configurable
    noise_floor = float(p["noise_floor"])
    abs_diff_suppressed = np.where(abs_diff > noise_floor, abs_diff, 0.0)

    # Statistics (from valid overlap pixels only)
    valid_vals = abs_diff[overlap_mask > 0]
    mean_diff = float(valid_vals.mean()) if len(valid_vals) > 0 else 0.0
    median_diff = float(np.median(valid_vals)) if len(valid_vals) > 0 else 0.0
    p95_diff = float(np.percentile(valid_vals, 95)) if len(valid_vals) > 0 else 0.0

    # SSIM
    ssim_score = None
    ssim_map = None
    try:
        ssim_score, ssim_map = _compute_ssim(ref_rgb, aligned_suspect, overlap_mask, p)
    except Exception as e:
        warnings.append(f"SSIM computation failed: {e}")

    # Candidate changed regions
    candidate_regions = _extract_candidate_regions(
        abs_diff_suppressed, overlap_mask, p, ref_rgb.shape
    )

    return DiffAnalysisResult(
        status="COMPLETED",
        mean_abs_diff=mean_diff,
        median_abs_diff=median_diff,
        p95_abs_diff=p95_diff,
        ssim_score=ssim_score,
        overlap_pixel_count=overlap_pixels,
        abs_diff_map=abs_diff_suppressed.astype(np.float32),
        ssim_map=ssim_map,
        overlap_mask=overlap_mask,
        aligned_suspect=aligned_suspect,
        candidate_regions=candidate_regions,
        normalization_applied=norm_method,
        noise_floor=noise_floor,
        warnings=warnings,
    )


def _luminance_normalize(
    ref: np.ndarray,
    sus: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Robust luminance normalization in the overlap region."""
    valid = mask > 0
    ref_lum = ref[valid].astype(np.float64)
    sus_lum = sus[valid].astype(np.float64)

    ref_mean = ref_lum.mean()
    sus_mean = sus_lum.mean()
    ref_std = ref_lum.std() + 1e-6
    sus_std = sus_lum.std() + 1e-6

    # Affine intensity matching
    sus_norm = (sus.astype(np.float64) - sus_mean) / sus_std * ref_std + ref_mean
    sus_norm = np.clip(sus_norm, 0, 255).astype(np.uint8)
    return ref, sus_norm


def _compute_ssim(
    ref: np.ndarray,
    sus: np.ndarray,
    mask: np.ndarray,
    p: dict,
) -> tuple[float, np.ndarray]:
    """Compute local SSIM between ref and aligned suspect."""
    from scipy.ndimage import uniform_filter

    # Convert to grayscale
    ref_g = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY).astype(np.float64)
    sus_g = cv2.cvtColor(sus, cv2.COLOR_RGB2GRAY).astype(np.float64)

    win = p.get("ssim_window_size", 11)
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu1 = uniform_filter(ref_g, win)
    mu2 = uniform_filter(sus_g, win)
    sigma1sq = uniform_filter(ref_g ** 2, win) - mu1 ** 2
    sigma2sq = uniform_filter(sus_g ** 2, win) - mu2 ** 2
    sigma12 = uniform_filter(ref_g * sus_g, win) - mu1 * mu2

    ssim_map = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1 ** 2 + mu2 ** 2 + C1) * (sigma1sq + sigma2sq + C2)
    )

    valid = mask > 0
    score = float(ssim_map[valid].mean()) if valid.any() else 0.0
    ssim_diff = (1.0 - ssim_map) / 2.0  # 0 = identical, 1 = completely different
    return score, ssim_diff.astype(np.float32)


def _extract_candidate_regions(
    diff_map: np.ndarray,
    overlap_mask: np.ndarray,
    p: dict,
    image_shape: tuple,
) -> list:
    """Extract candidate changed regions from the suppressed difference map."""
    threshold = p["region_threshold"]
    min_pixels = p["region_min_pixels"]
    h, w = diff_map.shape[:2]
    orig_h, orig_w = image_shape[:2]

    # Binary thresholded map
    binary = ((diff_map > threshold) & (overlap_mask > 0)).astype(np.uint8) * 255

    if not binary.any():
        return []

    # Morphological close to group nearby pixels
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for cnt in contours:
        area = int(cv2.contourArea(cnt))
        if area < min_pixels:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)

        # Map back to original image coordinates (if resized during analysis)
        scale_x = orig_w / w
        scale_y = orig_h / h
        ox = int(x * scale_x)
        oy = int(y * scale_y)
        obw = int(bw * scale_x)
        obh = int(bh * scale_y)

        region_diff = diff_map[y:y+bh, x:x+bw]
        mean_score = float(region_diff.mean())

        total_ref_pixels = orig_h * orig_w
        area_pct = (obw * obh) / total_ref_pixels * 100 if total_ref_pixels > 0 else 0.0

        regions.append({
            "bbox": {"x": ox, "y": oy, "width": obw, "height": obh},
            "pixel_area": area,
            "area_percent": round(area_pct, 4),
            "mean_diff_score": round(mean_score, 4),
            "source_evidence": "absolute_pixel_difference",
        })

    # Sort by area descending
    regions.sort(key=lambda r: r["pixel_area"], reverse=True)
    return regions[:20]  # cap at 20 regions
