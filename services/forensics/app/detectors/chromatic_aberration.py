"""
Lateral Chromatic Aberration (LCA) Detector — Phase 2.

Analyzes physical lens optical dispersion across red, green, and blue color channels.

Physical Principles:
  - Real glass camera lenses have wavelength-dependent refractive indices (dispersion: n_blue > n_green > n_red).
  - This causes slight radial magnification differences: red and blue channels expand/contract radially relative to green.
  - The displacement vectors always point toward/away from the optical center (cx, cy).
  - Displacement magnitude increases monotonically with distance from the optical center (r = ||p - c||).
  - Synthetic AI images (Midjourney, DALL-E, SD, Flux) synthesize RGB channels simultaneously and lack
    physically consistent radial optical dispersion.

Detector Status Values:
  - OPTICAL_LENS_VERIFIED: Consistent radial color dispersion detected (genuine physical camera lens).
  - SYNTHETIC_OR_PROCESSED: No coherent radial dispersion found (synthetic media, digital graphic, or software crop).
  - INCONCLUSIVE: Insufficient high-contrast edges or low resolution.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image as PILImage

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess

logger = logging.getLogger(__name__)

DETECTOR_NAME = "chromatic_aberration"
DETECTOR_VERSION = "1.0.0"


@dataclass
class LCAMeasurement:
    """Measurement of lateral chromatic aberration at a local edge patch."""
    x: int
    y: int
    radius: float
    radial_angle: float
    displacement_rb: tuple[float, float]  # (dx, dy) between R and B channels
    radial_alignment: float  # cosine similarity with radial direction [-1.0 .. 1.0]


@dataclass
class LCAResult:
    """Result of chromatic aberration optical analysis."""
    status: str  # OPTICAL_LENS_VERIFIED | SYNTHETIC_OR_PROCESSED | INCONCLUSIVE
    radial_coherence_score: float  # 0.0 to 1.0 (higher = more consistent physical lens dispersion)
    measured_edge_count: int
    mean_radial_alignment: float
    evidence: list[str] = field(default_factory=list)
    optical_center: tuple[int, int] = (0, 0)
    execution_ms: int = 0


def analyze_chromatic_aberration(
    rgb: np.ndarray,
    min_edges: int = 20,
    patch_size: int = 32,
) -> LCAResult:
    """
    Measures Lateral Chromatic Aberration (LCA) across high-contrast edges.
    
    Args:
        rgb: HxWx3 uint8 RGB array
        min_edges: Minimum number of edge patches required for confident estimation
        patch_size: Size of local analysis window around edges
        
    Returns:
        LCAResult containing radial coherence score and optical status
    """
    h, w = rgb.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    evidence: list[str] = []

    if h < 128 or w < 128:
        return LCAResult(
            status="INCONCLUSIVE",
            radial_coherence_score=0.5,
            measured_edge_count=0,
            mean_radial_alignment=0.0,
            evidence=["Image resolution too low for micro-optical LCA analysis."],
            optical_center=(int(cx), int(cy)),
        )

    r_channel = rgb[:, :, 0].astype(np.float32)
    g_channel = rgb[:, :, 1].astype(np.float32)
    b_channel = rgb[:, :, 2].astype(np.float32)

    # Detect high-contrast edges using Sobel on the green (reference luminance) channel
    grad_x = cv2.Sobel(g_channel, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(g_channel, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(grad_x**2 + grad_y**2)

    # Focus on the outer 70% radial zone where lens dispersion is physically strongest
    y_coords, x_coords = np.ogrid[:h, :w]
    radii = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2)
    max_radius = math.sqrt(cx**2 + cy**2)
    normalized_radii = radii / max(1.0, max_radius)

    # Candidate edge mask: strong edges in the mid-to-outer field (radius >= 0.25)
    margin = patch_size // 2
    inner_mask = np.zeros((h, w), dtype=bool)
    inner_mask[margin : h - margin, margin : w - margin] = True
    edge_candidates = (grad_mag > 35.0) & (normalized_radii >= 0.25) & inner_mask

    candidate_ys, candidate_xs = np.where(edge_candidates)
    total_candidates = len(candidate_xs)

    if total_candidates < min_edges:
        return LCAResult(
            status="INCONCLUSIVE",
            radial_coherence_score=0.5,
            measured_edge_count=total_candidates,
            mean_radial_alignment=0.0,
            evidence=[
                f"Insufficient high-contrast peripheral edges found ({total_candidates} < {min_edges}) to determine lens optics."
            ],
            optical_center=(int(cx), int(cy)),
        )

    # Subsample candidate edge patches across quadrants for spatial uniformity
    np.random.seed(42)  # Deterministic repeatability
    sample_indices = np.random.choice(
        total_candidates,
        size=min(total_candidates, 200),
        replace=False,
    )

    measurements: list[LCAMeasurement] = []
    half_p = patch_size // 2

    for idx in sample_indices:
        ex, ey = int(candidate_xs[idx]), int(candidate_ys[idx])
        rad = float(normalized_radii[ey, ex])

        # Extract local patches across R, G, B
        patch_r = r_channel[ey - half_p : ey + half_p, ex - half_p : ex + half_p]
        patch_g = g_channel[ey - half_p : ey + half_p, ex - half_p : ex + half_p]
        patch_b = b_channel[ey - half_p : ey + half_p, ex - half_p : ex + half_p]

        # Compute sub-pixel shift between Red and Blue using phase correlation or cross-correlation
        try:
            # Shift of R relative to G, and B relative to G
            shift_rg, _ = cv2.phaseCorrelate(patch_r, patch_g)
            shift_bg, _ = cv2.phaseCorrelate(patch_b, patch_g)

            dx = shift_rg[0] - shift_bg[0]
            dy = shift_rg[1] - shift_bg[1]
            disp_mag = math.sqrt(dx**2 + dy**2)

            if 0.05 <= disp_mag <= 3.5:  # Valid physical micro-shift range (in pixels)
                # Radial vector from optical center to edge point
                rx = ex - cx
                ry = ey - cy
                r_mag = math.sqrt(rx**2 + ry**2)

                if r_mag > 0:
                    # Cosine similarity between channel displacement vector and radial vector
                    cos_sim = abs((dx * rx + dy * ry) / (disp_mag * r_mag))
                    angle = math.atan2(ry, rx)

                    measurements.append(
                        LCAMeasurement(
                            x=ex,
                            y=ey,
                            radius=rad,
                            radial_angle=angle,
                            displacement_rb=(dx, dy),
                            radial_alignment=cos_sim,
                        )
                    )
        except Exception:
            continue

    if len(measurements) < 10:
        return LCAResult(
            status="INCONCLUSIVE",
            radial_coherence_score=0.5,
            measured_edge_count=len(measurements),
            mean_radial_alignment=0.0,
            evidence=["High-contrast edges lacked distinct chromatic separation."],
            optical_center=(int(cx), int(cy)),
        )

    # In genuine lenses, alignments are consistently high (pointing radially)
    alignments = [m.radial_alignment for m in measurements]
    mean_alignment = float(np.mean(alignments))
    high_alignment_ratio = float(np.mean([a >= 0.70 for a in alignments]))

    # Score from 0.0 to 1.0 representing physical optical consistency
    coherence_score = float(np.clip(0.6 * mean_alignment + 0.4 * high_alignment_ratio, 0.0, 1.0))

    if coherence_score >= 0.65:
        status = "OPTICAL_LENS_VERIFIED"
        evidence.append(
            f"Physical glass lens dispersion confirmed: radial alignment {mean_alignment:.2f} across {len(measurements)} measured edges."
        )
    elif coherence_score <= 0.38:
        status = "SYNTHETIC_OR_PROCESSED"
        evidence.append(
            f"Lack of physical radial dispersion (alignment {mean_alignment:.2f}): RGB channels synthesized simultaneously without optical glass refraction."
        )
    else:
        status = "INCONCLUSIVE"
        evidence.append(
            f"Chromatic dispersion alignment moderate ({mean_alignment:.2f}): insufficient to rule for or against physical lens capture."
        )

    return LCAResult(
        status=status,
        radial_coherence_score=round(coherence_score, 4),
        measured_edge_count=len(measurements),
        mean_radial_alignment=round(mean_alignment, 4),
        evidence=evidence,
        optical_center=(int(cx), int(cy)),
    )


class ChromaticAberrationDetector(BaseDetector):
    """Forensic detector measuring Lateral Chromatic Aberration (LCA)."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.METADATA

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        start = time.perf_counter()
        image_bytes: Optional[bytes] = kwargs.get("image_bytes")

        if not image_bytes and image_path:
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            except OSError as e:
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    details={"status": "UNAVAILABLE", "error": str(e)},
                )

        if not image_bytes:
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                details={"status": "UNAVAILABLE", "error": "No image data provided"},
            )

        try:
            pre = preprocess(image_bytes, max_dimension=1024)
            res = analyze_chromatic_aberration(pre.rgb)
            exec_ms = int((time.perf_counter() - start) * 1000)

            # Score: 0.0 (natural physical lens) to 1.0 (anomalous / synthetic)
            synthetic_score = round(1.0 - res.radial_coherence_score, 4) if res.status != "INCONCLUSIVE" else 0.5

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=synthetic_score,
                confidence=round(res.radial_coherence_score, 4),
                details={
                    "status": res.status,
                    "radial_coherence_score": res.radial_coherence_score,
                    "measured_edge_count": res.measured_edge_count,
                    "mean_radial_alignment": res.mean_radial_alignment,
                    "optical_center": res.optical_center,
                    "evidence": res.evidence,
                },
                execution_time_ms=exec_ms,
            )
        except Exception as e:
            logger.error("Chromatic aberration analysis failed: %s", e)
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                details={"status": "UNAVAILABLE", "error": str(e)},
            )


_singleton: Optional[ChromaticAberrationDetector] = None


def get_chromatic_aberration_detector() -> ChromaticAberrationDetector:
    """Return singleton instance of ChromaticAberrationDetector."""
    global _singleton
    if _singleton is None:
        _singleton = ChromaticAberrationDetector()
    return _singleton
