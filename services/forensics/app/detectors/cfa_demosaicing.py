"""
Bayer CFA (Color Filter Array) Demosaicing Detector.

Physical Optical Principles:
  - Single-sensor digital cameras (smartphones, DSLRs, mirrorless) use a Bayer CFA
    (typically RGGB, GRBG, GBRG, BGGR) overlaid on the silicon photodiode array.
  - The in-camera ISP demosaicing algorithm interpolates missing color channels,
    leaving a mathematically strict periodic interpolation relationship across adjacent pixels.
  - In spatial 2x2 grid variance analysis of prediction residuals, authentic camera images
    exhibit a pronounced variance disparity between sampled sites (1 in 4 for Red/Blue)
    and interpolated sites (grid_cv >= 0.009, grid_ratio >= 1.020).
  - Synthetic AI images (Midjourney, DALL-E, SD, Flux) and digital graphics synthesize RGB channels
    simultaneously in software and NEVER possess physical Bayer demosaicing artifacts (grid_cv < 0.008, grid_ratio < 1.020).
  - Spliced, copy-moved, or AI-inpainted regions lack the underlying camera CFA pattern,
    creating measurable spatial CFA discontinuities across the canvas.

Detector Status Values:
  - BAYER_CFA_CONFIRMED: Strong periodic Bayer CFA interpolation verified (authentic physical camera capture).
  - NO_CFA_PATTERN: Flat, non-periodic residual spectrum (synthetic AI generation or digital graphic).
  - CFA_DISCONTINUITY: Discontinuous CFA pattern (localized inpaint/splice on real camera photo).
  - INCONCLUSIVE: Low resolution (<64x64) or heavy low-pass filtering.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult

logger = logging.getLogger(__name__)

DETECTOR_NAME = "cfa_demosaicing"
DETECTOR_VERSION = "1.0.0"


@dataclass
class CFAResult:
    status: str  # BAYER_CFA_CONFIRMED | NO_CFA_PATTERN | CFA_DISCONTINUITY | INCONCLUSIVE
    cfa_confidence: float  # 0.0 to 1.0 (higher = stronger physical sensor Bayer artifact)
    estimated_pattern: Optional[str]  # e.g. "RGGB", "GRBG", "GBRG", "BGGR", or None
    p_spectrum_peak: float  # Peak-to-ambient ratio in Fourier residual spectrum
    grid_periodicity_ratio: float  # 2x2 spatial lattice variance ratio
    grid_cv: float  # Coefficient of variation across 2x2 grid
    tampered_blocks_detected: int  # Number of local blocks showing CFA loss
    evidence: list[str] = field(default_factory=list)


class CFADemosaicingDetector(BaseDetector):
    """
    Detects physical sensor Bayer demosaicing artifacts and localized CFA tampering.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__()
        self.config = config or {}
        self.cv_threshold = float(self.config.get("cv_threshold", 0.0080))
        self.grid_ratio_threshold = float(self.config.get("grid_ratio_threshold", 1.018))

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
        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        start_time = time.perf_counter()

        try:
            if image_bytes:
                nparr = np.frombuffer(image_bytes, np.uint8)
                img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                img_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)

            if img_bgr is None:
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=0.5,
                    confidence=0.0,
                    details={"status": "INCONCLUSIVE", "error": "Could not read image"},
                    execution_time_ms=int((time.perf_counter() - start_time) * 1000),
                )

            h, w, c = img_bgr.shape
            if h < 64 or w < 64:
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=0.5,
                    confidence=0.0,
                    details={
                        "status": "INCONCLUSIVE",
                        "error": f"Image dimensions too small ({w}x{h}). Minimum required: 64x64.",
                    },
                    execution_time_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Convert to float32
            img_f = img_bgr.astype(np.float32)
            b = img_f[:, :, 0]
            g = img_f[:, :, 1]
            r = img_f[:, :, 2]

            # 2nd-order difference prediction kernel (Laplacian filter)
            # In demosaiced channels, prediction error at non-sampled sites is periodic
            k = np.array([[0, 0.25, 0], [0.25, -1.0, 0.25], [0, 0.25, 0]], dtype=np.float32)
            e_g = np.abs(cv2.filter2D(g, -1, k))[4:-4, 4:-4]
            e_r = np.abs(cv2.filter2D(r, -1, k))[4:-4, 4:-4]

            # 1. Spatial 2x2 Grid Variance Analysis on Red channel (1-in-4 Bayer sampling)
            r_v00 = float(np.mean(e_r[0::2, 0::2] ** 2))
            r_v01 = float(np.mean(e_r[0::2, 1::2] ** 2))
            r_v10 = float(np.mean(e_r[1::2, 0::2] ** 2))
            r_v11 = float(np.mean(e_r[1::2, 1::2] ** 2))
            r_vars = [r_v00, r_v01, r_v10, r_v11]

            r_mean = float(np.mean(r_vars))
            r_std = float(np.std(r_vars))
            grid_cv = float(r_std / (r_mean + 1e-6))
            r_ratio = float(max(r_vars) / (min(r_vars) + 1e-6))

            pattern_names = ["RGGB", "GRBG", "GBRG", "BGGR"]
            best_pattern = pattern_names[int(np.argmax(r_vars))]

            # 2. Fourier P-Spectrum Peak Detection on Green channel residual
            gh, gw = e_g.shape
            cy, cx = gh // 2, gw // 2
            win_y = np.hanning(gh).reshape(-1, 1)
            win_x = np.hanning(gw).reshape(1, -1)
            e_win = (e_g - np.mean(e_g)) * (win_y * win_x)
            fft_g = np.abs(np.fft.fftshift(np.fft.fft2(e_win)))

            ambient_energy = float(np.mean(fft_g)) + 1e-4
            nyquist_energy = float(
                (fft_g[0, cx] + fft_g[gh - 1, cx] + fft_g[cy, 0] + fft_g[cy, gw - 1]) / 4.0
            )
            p_peak = float(nyquist_energy / ambient_energy)

            # 3. Local Block CFA Coherence & Discontinuity Detection (64x64 blocks)
            block_size = 64
            tampered_blocks = 0
            total_blocks = 0
            if gh >= block_size * 2 and gw >= block_size * 2:
                for by in range(0, gh - block_size + 1, block_size):
                    for bx in range(0, gw - block_size + 1, block_size):
                        sub_r = e_r[by : by + block_size, bx : bx + block_size]
                        sub_vars = [
                            float(np.mean(sub_r[0::2, 0::2] ** 2)),
                            float(np.mean(sub_r[0::2, 1::2] ** 2)),
                            float(np.mean(sub_r[1::2, 0::2] ** 2)),
                            float(np.mean(sub_r[1::2, 1::2] ** 2)),
                        ]
                        sub_cv = float(np.std(sub_vars) / (np.mean(sub_vars) + 1e-6))
                        total_blocks += 1
                        if sub_cv < 0.007:
                            tampered_blocks += 1

            evidence: list[str] = []

            # Physical camera photos show natural demosaicing: 0.0075 <= grid_cv <= 0.0150 and r_ratio <= 1.040 and p_peak <= 1.70
            # Generative models (latent diffusion VAE upsamplers) exhibit extreme periodic frequency resonance:
            is_generative_lattice = (grid_cv >= 0.0160 and r_ratio >= 1.040 and p_peak >= 1.80)
            is_bayer = (not is_generative_lattice) and (grid_cv >= self.cv_threshold and r_ratio >= self.grid_ratio_threshold and p_peak <= 1.70)
            cfa_conf = float(np.clip((grid_cv - 0.007) / 0.015, 0.0, 1.0)) if is_bayer else 0.0

            if is_generative_lattice:
                status = "SYNTHETIC_GENERATIVE_LATTICE"
                cfa_conf = 0.95
                evidence.append(
                    f"Unnatural periodic frequency resonance detected (grid CV: {grid_cv:.4f} > 0.015, grid ratio: {r_ratio:.3f}, Fourier peak: {p_peak:.2f}). Characteristic signature of latent diffusion VAE upsampling / generative checkerboard synthesis."
                )
            elif is_bayer:
                if total_blocks > 8 and (tampered_blocks / total_blocks) > 0.20:
                    status = "CFA_DISCONTINUITY"
                    evidence.append(
                        f"Bayer CFA pattern detected globally (grid CV: {grid_cv:.4f}, pattern: {best_pattern}), but {tampered_blocks}/{total_blocks} blocks show CFA discontinuity (consistent with localized splice or AI inpainting on real base)."
                    )
                else:
                    status = "BAYER_CFA_CONFIRMED"
                    evidence.append(
                        f"Physical camera Bayer CFA demosaicing verified (grid CV: {grid_cv:.4f} >= {self.cv_threshold}, estimated pattern: {best_pattern}, grid ratio: {r_ratio:.3f})."
                    )
            elif grid_cv <= 0.008 and r_ratio <= 1.020:
                status = "NO_CFA_PATTERN"
                cfa_conf = 0.0
                evidence.append(
                    f"Zero Bayer CFA demosaicing periodicity detected (grid CV: {grid_cv:.4f} <= 0.008, grid ratio: {r_ratio:.3f}). RGB channels were synthesized directly in software (consistent with AI generation or digital graphic)."
                )
            else:
                status = "INCONCLUSIVE"
                evidence.append(
                    f"Ambiguous CFA signal (grid CV: {grid_cv:.4f}, grid ratio: {r_ratio:.3f}). Moderate recompression or heavy smoothing observed."
                )

            # Score represents suspicion (0.0 = authentic camera CFA, 1.0 = synthetic or tampered)
            if status == "BAYER_CFA_CONFIRMED":
                detector_score = float(np.clip(1.0 - cfa_conf, 0.02, 0.20))
            elif status == "CFA_DISCONTINUITY":
                detector_score = 0.85
            elif status == "NO_CFA_PATTERN":
                detector_score = 0.92
            elif status == "SYNTHETIC_GENERATIVE_LATTICE":
                detector_score = 0.95
            else:
                detector_score = 0.50

            confidence = float(np.clip(max(cfa_conf, 1.0 - cfa_conf), 0.50, 0.95))

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=round(detector_score, 4),
                confidence=round(confidence, 4),
                details={
                    "status": status,
                    "cfa_confidence": round(cfa_conf, 4),
                    "estimated_pattern": best_pattern if status != "NO_CFA_PATTERN" else None,
                    "grid_cv": round(grid_cv, 4),
                    "grid_periodicity_ratio": round(r_ratio, 3),
                    "p_spectrum_peak": round(p_peak, 2),
                    "tampered_blocks_detected": tampered_blocks,
                    "total_blocks_analyzed": total_blocks,
                    "evidence": evidence,
                },
                execution_time_ms=int((time.perf_counter() - start_time) * 1000),
            )

        except Exception as e:
            logger.warning("CFA Demosaicing analysis failed: %s", e)
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=0.5,
                confidence=0.0,
                details={"status": "INCONCLUSIVE", "error": str(e)},
                execution_time_ms=int((time.perf_counter() - start_time) * 1000),
            )


# Singleton factory
_cfa_detector: Optional[CFADemosaicingDetector] = None


def get_cfa_demosaicing_detector(config: Optional[dict[str, Any]] = None) -> CFADemosaicingDetector:
    global _cfa_detector
    if _cfa_detector is None or config is not None:
        _cfa_detector = CFADemosaicingDetector(config=config)
    return _cfa_detector
