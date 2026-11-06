"""
Modality Pre-Router — classify an image into one of five modalities before
forensic analysis so that each downstream detector can apply modality-specific
thresholds.

Rationale
---------
Different image types obey fundamentally different physical laws.  A single
set of thresholds cannot correctly handle a landscape photograph, a scanned
bank receipt, a screenshot, and an AI-generated artwork at the same time.

This module classifies every incoming image into one of:

* **NATURAL_PHOTO** — camera photo of a real-world scene (portraits,
  landscapes, streets, food, pets).
* **DOCUMENT** — photographed / scanned paper document, certificate, ID card,
  receipt, form.
* **DIGITAL_GRAPHIC** — vector art, poster, logo, Canva design, infographic,
  meme template.
* **SCREENSHOT** — screen capture of an app UI, web page, chat window, or
  desktop.
* **MIXED_MEDIA** — camera photo with overlaid stickers, text, graphics, or
  heavy filters.

All classification signals are computed with **OpenCV + NumPy only** — no
neural network is involved.  The analysis is performed on a 256×256 thumbnail
and targets **< 50 ms** per image.

Signals used
~~~~~~~~~~~~
A. Color Palette Concentration (unique-color count, top-10 coverage)
B. Edge Density & Straightness (Canny + axis-aligned ratio)
C. Spatial Noise Variance (block-wise local variance)
D. White / Paper Background Ratio (HSV thresholds)
E. Aspect Ratio (device- / paper-specific heuristics)
F. Text Region Detection (morphological horizontal line segments)
G. Sticker / Overlay Detection (noise-discontinuity between regions)

Author:  Forensics Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import cv2
import numpy as np

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants – analysis thumbnail size
# ---------------------------------------------------------------------------
_THUMB_SIZE: int = 256
_BLOCK_SIZE: int = 32

# ---------------------------------------------------------------------------
# ImageModality enum
# ---------------------------------------------------------------------------


class ImageModality(str, Enum):
    """Five canonical modalities for forensic pre-routing."""

    NATURAL_PHOTO = "NATURAL_PHOTO"
    """Camera photo of real-world scene (portraits, landscapes, streets, food, pets)."""

    DOCUMENT = "DOCUMENT"
    """Photographed / scanned paper document, certificate, ID card, receipt, form."""

    DIGITAL_GRAPHIC = "DIGITAL_GRAPHIC"
    """Vector art, poster, logo, Canva design, infographic, meme template."""

    SCREENSHOT = "SCREENSHOT"
    """Screen capture of app UI, web page, chat, desktop."""

    MIXED_MEDIA = "MIXED_MEDIA"
    """Camera photo with overlaid stickers, text, graphics, or heavy filters."""


# ---------------------------------------------------------------------------
# ModalityResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class ModalityResult:
    """Result of classifying an image's modality.

    Attributes:
        modality:   The predicted :class:`ImageModality`.
        confidence: Classification confidence in the range ``[0.0, 1.0]``.
        features:   Dictionary of extracted numeric features used for
                    classification (useful for debugging / auditing).
        evidence:   Human-readable reasons that justify the classification.
    """

    modality: ImageModality
    confidence: float
    features: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)


# ===================================================================== #
#  Signal extraction helpers (all operate on numpy arrays)               #
# ===================================================================== #


def _to_thumbnail(image: np.ndarray, size: int = _THUMB_SIZE) -> np.ndarray:
    """Resize *image* (BGR) to a square *size*×*size* thumbnail.

    Uses ``cv2.INTER_AREA`` for downscaling quality and speed.
    """
    return cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)


# -- Signal A: Color Palette Concentration --------------------------------


def _signal_color_palette(thumb: np.ndarray) -> dict[str, Any]:
    """Compute unique-color count and top-10 color coverage.

    Parameters
    ----------
    thumb : np.ndarray
        BGR thumbnail (256×256).

    Returns
    -------
    dict
        ``unique_colors`` (int) and ``top10_coverage`` (float 0-1).
    """
    # Reshape to (N, 3) and view as structured array for fast unique count
    pixels = thumb.reshape(-1, 3).astype(np.uint32)
    # Pack R/G/B into a single 32-bit value for speed
    packed = (pixels[:, 0] << 16) | (pixels[:, 1] << 8) | pixels[:, 2]

    unique_vals, counts = np.unique(packed, return_counts=True)
    unique_colors = int(len(unique_vals))

    # Top-10 color coverage
    total_pixels = packed.shape[0]
    top10_count = int(np.sort(counts)[-10:].sum()) if len(counts) >= 10 else int(counts.sum())
    top10_coverage = top10_count / total_pixels if total_pixels > 0 else 0.0

    return {
        "unique_colors": unique_colors,
        "top10_coverage": round(top10_coverage, 4),
    }


# -- Signal B: Edge Density & Straightness --------------------------------


def _signal_edge(thumb_gray: np.ndarray) -> dict[str, Any]:
    """Run Canny edge detection and compute straightness ratio.

    Returns
    -------
    dict
        ``edge_density`` (float 0-1) and ``straight_edge_ratio`` (float 0-1).
    """
    edges = cv2.Canny(thumb_gray, 50, 150)
    edge_pixels = np.count_nonzero(edges)
    total_pixels = edges.shape[0] * edges.shape[1]
    edge_density = edge_pixels / total_pixels if total_pixels > 0 else 0.0

    # Straight-edge ratio: count pixels that have an axis-aligned neighbour
    if edge_pixels == 0:
        return {
            "edge_density": 0.0,
            "straight_edge_ratio": 0.0,
        }

    # Horizontal edges: pixel at (r,c) is edge AND pixel at (r, c±1) is edge
    h_shift_r = np.zeros_like(edges)
    h_shift_r[:, 1:] = edges[:, :-1]
    h_shift_l = np.zeros_like(edges)
    h_shift_l[:, :-1] = edges[:, 1:]
    horizontal = edges & (h_shift_r | h_shift_l)

    # Vertical edges: pixel at (r,c) is edge AND pixel at (r±1, c) is edge
    v_shift_d = np.zeros_like(edges)
    v_shift_d[1:, :] = edges[:-1, :]
    v_shift_u = np.zeros_like(edges)
    v_shift_u[:-1, :] = edges[1:, :]
    vertical = edges & (v_shift_d | v_shift_u)

    axis_aligned = np.count_nonzero(horizontal | vertical)
    straight_edge_ratio = axis_aligned / edge_pixels

    return {
        "edge_density": round(edge_density, 4),
        "straight_edge_ratio": round(straight_edge_ratio, 4),
    }


# -- Signal C: Spatial Noise Variance -------------------------------------


def _signal_noise_variance(
    thumb_gray: np.ndarray,
    block_size: int = _BLOCK_SIZE,
) -> dict[str, Any]:
    """Compute local noise variance across *block_size*×*block_size* blocks.

    Returns
    -------
    dict
        ``noise_variance_mean``, ``noise_variance_std``,
        ``low_noise_block_ratio`` (fraction of blocks with var < 2).
    """
    h, w = thumb_gray.shape[:2]
    rows = h // block_size
    cols = w // block_size

    if rows == 0 or cols == 0:
        return {
            "noise_variance_mean": 0.0,
            "noise_variance_std": 0.0,
            "low_noise_block_ratio": 1.0,
            "block_variances": [],
        }

    # Apply a Laplacian to isolate high-frequency noise
    laplacian = cv2.Laplacian(thumb_gray, cv2.CV_64F)

    variances: list[float] = []
    for r in range(rows):
        for c in range(cols):
            block = laplacian[
                r * block_size : (r + 1) * block_size,
                c * block_size : (c + 1) * block_size,
            ]
            variances.append(float(np.var(block)))

    var_arr = np.array(variances)
    low_noise_blocks = int(np.sum(var_arr < 2.0))
    total_blocks = len(variances)

    return {
        "noise_variance_mean": round(float(var_arr.mean()), 4),
        "noise_variance_std": round(float(var_arr.std()), 4),
        "low_noise_block_ratio": round(low_noise_blocks / total_blocks, 4) if total_blocks > 0 else 1.0,
        "block_variances": variances,
    }


# -- Signal D: White / Paper Background Ratio -----------------------------


def _signal_white_background(thumb_hsv: np.ndarray) -> dict[str, Any]:
    """Compute ratio of pixels that are 'paper white' (V > 180, S < 40).

    Returns
    -------
    dict
        ``white_paper_ratio`` (float 0-1).
    """
    s_channel = thumb_hsv[:, :, 1]
    v_channel = thumb_hsv[:, :, 2]

    white_mask = (v_channel > 180) & (s_channel < 40)
    total = thumb_hsv.shape[0] * thumb_hsv.shape[1]
    ratio = float(np.count_nonzero(white_mask)) / total if total > 0 else 0.0

    return {"white_paper_ratio": round(ratio, 4)}


# -- Signal E: Aspect Ratio -----------------------------------------------


_DEVICE_RATIOS = [16 / 9, 9 / 16, 4 / 3, 3 / 4, 16 / 10, 10 / 16]
_PAPER_RATIOS = [1 / 1.4142, 1.4142, 8.5 / 11, 11 / 8.5]  # A4, Letter


def _signal_aspect_ratio(orig_h: int, orig_w: int) -> dict[str, Any]:
    """Classify the original aspect ratio.

    Returns
    -------
    dict
        ``aspect_ratio`` (float), ``matches_device`` (bool),
        ``matches_paper`` (bool), ``is_square`` (bool).
    """
    if orig_h == 0 or orig_w == 0:
        return {
            "aspect_ratio": 1.0,
            "matches_device": False,
            "matches_paper": False,
            "is_square": True,
        }

    ar = orig_w / orig_h
    matches_device = any(abs(ar - r) < 0.05 for r in _DEVICE_RATIOS)
    matches_paper = any(abs(ar - r) < 0.05 for r in _PAPER_RATIOS)
    is_square = 0.95 <= ar <= 1.05

    return {
        "aspect_ratio": round(ar, 4),
        "matches_device": matches_device,
        "matches_paper": matches_paper,
        "is_square": is_square,
    }


# -- Signal F: Text Region Detection --------------------------------------


def _signal_text_regions(thumb_gray: np.ndarray) -> dict[str, Any]:
    """Detect text-like horizontal line segments via morphological ops.

    Returns
    -------
    dict
        ``text_density`` (float 0-1) — ratio of pixels in text-like regions.
    """
    # Adaptive threshold to binarize
    binary = cv2.adaptiveThreshold(
        thumb_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 10,
    )

    # Horizontal kernel to connect text characters into line segments
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)

    # Dilate vertically to form text blocks
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    text_blocks = cv2.dilate(h_lines, v_kernel, iterations=2)

    total = thumb_gray.shape[0] * thumb_gray.shape[1]
    text_pixels = int(np.count_nonzero(text_blocks))
    text_density = text_pixels / total if total > 0 else 0.0

    return {"text_density": round(text_density, 4)}


# -- Signal G: Sticker / Overlay Detection --------------------------------


def _signal_overlay(
    block_variances: list[float],
    noise_variance_mean: float,
) -> dict[str, Any]:
    """Detect noise-level discontinuities that indicate graphic overlays.

    A sticker / emoji pasted on a real photo creates blocks with near-zero
    noise adjacent to blocks with camera-level noise.

    Returns
    -------
    dict
        ``has_noise_discontinuity`` (bool),
        ``camera_noise_region_ratio`` (float 0-1).
    """
    if not block_variances or noise_variance_mean < 1.0:
        return {
            "has_noise_discontinuity": False,
            "camera_noise_region_ratio": 0.0,
        }

    var_arr = np.array(block_variances)
    total_blocks = len(var_arr)

    # "Camera-like" blocks: variance in a plausible range (> 5.0)
    camera_blocks = int(np.sum(var_arr > 5.0))
    # "Flat / digital" blocks: variance near zero (< 2.0)
    flat_blocks = int(np.sum(var_arr < 2.0))

    camera_ratio = camera_blocks / total_blocks if total_blocks > 0 else 0.0

    # Discontinuity exists when we have a significant mix of flat and noisy
    has_discontinuity = (
        flat_blocks >= 3
        and camera_blocks >= 3
        and 0.10 <= (flat_blocks / total_blocks) <= 0.50
    )

    return {
        "has_noise_discontinuity": has_discontinuity,
        "camera_noise_region_ratio": round(camera_ratio, 4),
    }


# ===================================================================== #
#  Main classification function                                          #
# ===================================================================== #


def classify_modality(image_bytes: bytes) -> ModalityResult:
    """Classify the modality of an image using lightweight OpenCV signals.

    The function decodes the image from raw bytes, down-scales it to a
    256×256 thumbnail, and runs seven cheap signal extractors.  A
    deterministic decision tree then maps the extracted features to one
    of the five :class:`ImageModality` values.

    Parameters
    ----------
    image_bytes : bytes
        Raw file content of the image (JPEG, PNG, WebP, …).

    Returns
    -------
    ModalityResult
        Classification result with modality, confidence, features, and
        human-readable evidence strings.

    Notes
    -----
    This function **never raises**.  On any internal error it returns
    ``NATURAL_PHOTO`` with ``confidence=0.0`` as a safe fallback.
    """
    try:
        # ----------------------------------------------------------
        # Decode image
        # ----------------------------------------------------------
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            logger.warning("modality_router: cv2.imdecode returned None")
            return ModalityResult(
                modality=ImageModality.NATURAL_PHOTO,
                confidence=0.0,
                features={},
                evidence=["Failed to decode image — defaulting to NATURAL_PHOTO"],
            )

        orig_h, orig_w = image.shape[:2]

        # ----------------------------------------------------------
        # Prepare derivatives
        # ----------------------------------------------------------
        thumb = _to_thumbnail(image)
        thumb_gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)
        thumb_hsv = cv2.cvtColor(thumb, cv2.COLOR_BGR2HSV)

        # ----------------------------------------------------------
        # Extract all signals
        # ----------------------------------------------------------
        sig_a = _signal_color_palette(thumb)
        sig_b = _signal_edge(thumb_gray)
        sig_c = _signal_noise_variance(thumb_gray)
        sig_d = _signal_white_background(thumb_hsv)
        sig_e = _signal_aspect_ratio(orig_h, orig_w)
        sig_f = _signal_text_regions(thumb_gray)
        sig_g = _signal_overlay(
            sig_c.get("block_variances", []),
            sig_c.get("noise_variance_mean", 0.0),
        )

        # Merge all features (drop block_variances from output — too large)
        features: dict[str, Any] = {}
        for sig in (sig_a, sig_b, sig_c, sig_d, sig_e, sig_f, sig_g):
            features.update(sig)
        features.pop("block_variances", None)

        # Convenience aliases
        unique_colors: int = sig_a["unique_colors"]
        top10_cov: float = sig_a["top10_coverage"]
        straight_ratio: float = sig_b["straight_edge_ratio"]
        noise_mean: float = sig_c["noise_variance_mean"]
        white_ratio: float = sig_d["white_paper_ratio"]
        text_density: float = sig_f["text_density"]
        has_disc: bool = sig_g["has_noise_discontinuity"]
        cam_ratio: float = sig_g["camera_noise_region_ratio"]

        # ----------------------------------------------------------
        # Decision tree
        # ----------------------------------------------------------
        evidence: list[str] = []

        # Rule 1 — SCREENSHOT
        if noise_mean < 2.0 and unique_colors < 5000 and straight_ratio > 0.60:
            evidence.append(
                f"Very low noise variance ({noise_mean:.2f}) indicates digital origin"
            )
            evidence.append(
                f"Few unique colors ({unique_colors}) with concentrated palette "
                f"(top-10 coverage {top10_cov:.1%})"
            )
            evidence.append(
                f"High straight-edge ratio ({straight_ratio:.1%}) suggests UI elements"
            )
            if sig_e["matches_device"]:
                evidence.append(
                    f"Aspect ratio {sig_e['aspect_ratio']:.3f} matches a common device ratio"
                )
            confidence = _compute_confidence(
                conditions_met=3,
                total_conditions=3,
                bonus=0.05 if sig_e["matches_device"] else 0.0,
            )
            return ModalityResult(
                modality=ImageModality.SCREENSHOT,
                confidence=confidence,
                features=features,
                evidence=evidence,
            )

        # Rule 2 — DIGITAL_GRAPHIC
        if noise_mean < 2.0 and unique_colors < 3000:
            evidence.append(
                f"Near-zero noise variance ({noise_mean:.2f}) indicates purely digital pixels"
            )
            evidence.append(
                f"Very few unique colors ({unique_colors}) — typical of vector / graphic art"
            )
            if top10_cov > 0.50:
                evidence.append(
                    f"Top-10 colors cover {top10_cov:.1%} of the image — flat fills"
                )
            confidence = _compute_confidence(
                conditions_met=2,
                total_conditions=2,
                bonus=0.05 if top10_cov > 0.50 else 0.0,
            )
            return ModalityResult(
                modality=ImageModality.DIGITAL_GRAPHIC,
                confidence=confidence,
                features=features,
                evidence=evidence,
            )

        # Rule 3 — DOCUMENT
        # Photographed documents/certificates often have large white margins with 4-12% text coverage.
        if (white_ratio > 0.50 and text_density > 0.05) or (white_ratio > 0.65 and text_density > 0.02):
            evidence.append(
                f"Large white/paper background ({white_ratio:.1%} of pixels)"
            )
            evidence.append(
                f"Significant text density ({text_density:.1%}) from structured text blocks"
            )
            if sig_e["matches_paper"]:
                evidence.append(
                    f"Aspect ratio {sig_e['aspect_ratio']:.3f} matches a standard paper size"
                )
            confidence = _compute_confidence(
                conditions_met=2,
                total_conditions=2,
                bonus=0.05 if sig_e["matches_paper"] else 0.0,
            )
            return ModalityResult(
                modality=ImageModality.DOCUMENT,
                confidence=confidence,
                features=features,
                evidence=evidence,
            )

        # Rule 4 — MIXED_MEDIA
        if has_disc and cam_ratio > 0.60:
            evidence.append(
                "Noise discontinuity detected — mix of flat digital blocks and "
                "camera-noise blocks"
            )
            evidence.append(
                f"Camera-noise regions cover {cam_ratio:.1%} of the image — "
                "base layer is a real photo"
            )
            evidence.append(
                "Graphic overlays (stickers, text, emoji) detected on top of "
                "the photograph"
            )
            confidence = _compute_confidence(
                conditions_met=2,
                total_conditions=2,
                bonus=0.0,
            )
            return ModalityResult(
                modality=ImageModality.MIXED_MEDIA,
                confidence=confidence,
                features=features,
                evidence=evidence,
            )

        # Rule 5 — NATURAL_PHOTO (default)
        evidence.append("No digital / document / overlay indicators triggered")
        if noise_mean >= 2.0:
            evidence.append(
                f"Moderate noise variance ({noise_mean:.2f}) consistent with camera sensor noise"
            )
        if unique_colors >= 5000:
            evidence.append(
                f"Rich color palette ({unique_colors} unique colors) suggests smooth gradients"
            )
        confidence = _compute_confidence(
            conditions_met=2 if (noise_mean >= 2.0 and unique_colors >= 5000) else 1,
            total_conditions=2,
            bonus=0.0,
        )
        return ModalityResult(
            modality=ImageModality.NATURAL_PHOTO,
            confidence=confidence,
            features=features,
            evidence=evidence,
        )

    except Exception:
        logger.exception("modality_router: unexpected error — defaulting to NATURAL_PHOTO")
        return ModalityResult(
            modality=ImageModality.NATURAL_PHOTO,
            confidence=0.0,
            features={},
            evidence=["Internal error — defaulting to NATURAL_PHOTO"],
        )


# ===================================================================== #
#  Confidence helper                                                     #
# ===================================================================== #


def _compute_confidence(
    conditions_met: int,
    total_conditions: int,
    bonus: float = 0.0,
) -> float:
    """Compute a heuristic confidence score.

    Parameters
    ----------
    conditions_met : int
        Number of decision-tree conditions satisfied.
    total_conditions : int
        Total number of conditions evaluated.
    bonus : float
        Extra credit (e.g. for matching device/paper aspect ratio).

    Returns
    -------
    float
        Confidence clamped to ``[0.0, 1.0]``.
    """
    if total_conditions == 0:
        return 0.0
    base = 0.60 + 0.30 * (conditions_met / total_conditions)
    return float(min(max(base + bonus, 0.0), 1.0))


# ===================================================================== #
#  ModalityRouter — BaseDetector wrapper                                 #
# ===================================================================== #


class ModalityRouter(BaseDetector):
    """Forensic pre-router that classifies an image into one of five
    modalities before any analysis detector runs.

    This detector reads the image file, calls :func:`classify_modality`,
    and wraps the :class:`ModalityResult` into a standard
    :class:`~app.detectors.base.DetectorResult`.
    """

    @property
    def name(self) -> str:
        """Detector identifier."""
        return "modality_router"

    @property
    def version(self) -> str:
        """Detector version."""
        return "1.0.0"

    @property
    def category(self) -> DetectorCategory:
        """Detector category (metadata, since it classifies, not analyses)."""
        return DetectorCategory.METADATA

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """Classify the modality of the image at *image_path*.

        Parameters
        ----------
        image_path : str
            Absolute path to an image file on disk.
        **kwargs
            Ignored — present for interface compatibility.

        Returns
        -------
        DetectorResult
            ``score`` is set to the confidence value.
            ``details`` contains the full :class:`ModalityResult` fields.
        """
        try:
            with open(image_path, "rb") as fh:
                image_bytes = fh.read()
        except Exception:
            logger.exception(
                "modality_router: failed to read image at %s", image_path
            )
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=0.0,
                confidence=0.0,
                details={
                    "modality": ImageModality.NATURAL_PHOTO.value,
                    "evidence": [f"Could not read file: {image_path}"],
                    "features": {},
                },
            )

        result = classify_modality(image_bytes)

        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=result.confidence,
            confidence=result.confidence,
            details={
                "modality": result.modality.value,
                "confidence": result.confidence,
                "evidence": result.evidence,
                "features": result.features,
            },
        )


# ===================================================================== #
#  Singleton accessor                                                    #
# ===================================================================== #

_singleton: Optional[ModalityRouter] = None


def get_modality_router() -> ModalityRouter:
    """Return the process-wide :class:`ModalityRouter` singleton.

    The instance is created on first call and reused thereafter.  Because
    the router carries no mutable state this is safe for concurrent use.

    Returns
    -------
    ModalityRouter
        Singleton instance.
    """
    global _singleton
    if _singleton is None:
        _singleton = ModalityRouter()
    return _singleton
