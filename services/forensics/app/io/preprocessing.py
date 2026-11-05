"""
Preprocessing pipeline for forensic detectors.

Provides standardized image loading, format conversion, and derived
artifact generation. The protected original is NEVER modified — all
preprocessing outputs are derived artifacts.

Phase 3: Implements RGB/grayscale conversion, orientation-aware loading,
and controlled resizing with dimension tracking.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

PREPROCESSING_VERSION = "1.0.0"


@dataclass
class PreprocessedImage:
    """Result of preprocessing an image for detector input."""
    rgb: np.ndarray               # H×W×3 uint8
    gray: np.ndarray              # H×W uint8
    width: int
    height: int
    channels: int
    mode: str                     # PIL mode
    is_jpeg: bool
    original_width: int
    original_height: int
    # Scale factor for mapping spatial results back to original dims
    scale_x: float = 1.0
    scale_y: float = 1.0
    parameters: dict = field(default_factory=dict)
    preprocessing_version: str = PREPROCESSING_VERSION


def load_image(image_bytes: bytes) -> PILImage.Image:
    """Load image from bytes. Does NOT modify the original bytes."""
    return PILImage.open(io.BytesIO(image_bytes))


def preprocess(
    image_bytes: bytes,
    *,
    max_dimension: Optional[int] = None,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    interpolation: str = "bilinear",
) -> PreprocessedImage:
    """
    Preprocess an image for detector input.

    Args:
        image_bytes: Raw image file bytes (never modified).
        max_dimension: If set, resize so the longest side is at most this.
        target_width: Explicit resize width (overrides max_dimension).
        target_height: Explicit resize height.
        interpolation: "bilinear", "bicubic", or "nearest".

    Returns:
        PreprocessedImage with rgb, gray arrays and dimension metadata.
    """
    img = load_image(image_bytes)
    orig_w, orig_h = img.size

    # Detect format
    fmt = (img.format or "").upper()
    is_jpeg = fmt == "JPEG"

    # Convert to RGB (handle RGBA, L, etc.)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Determine resize if needed
    new_w, new_h = orig_w, orig_h
    resized = False
    interp_method = PILImage.BILINEAR
    if interpolation == "bicubic":
        interp_method = PILImage.BICUBIC
    elif interpolation == "nearest":
        interp_method = PILImage.NEAREST

    if target_width and target_height:
        new_w, new_h = target_width, target_height
        resized = True
    elif max_dimension:
        longest = max(orig_w, orig_h)
        if longest > max_dimension:
            ratio = max_dimension / longest
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            resized = True

    if resized:
        img = img.resize((new_w, new_h), interp_method)

    # Convert to numpy arrays
    rgb = np.array(img, dtype=np.uint8)
    if rgb.ndim == 2:
        # Grayscale — expand to 3-channel for consistency
        rgb = np.stack([rgb, rgb, rgb], axis=-1)

    gray = np.array(img.convert("L"), dtype=np.uint8)

    scale_x = orig_w / new_w if new_w > 0 else 1.0
    scale_y = orig_h / new_h if new_h > 0 else 1.0

    params = {
        "max_dimension": max_dimension,
        "target_width": target_width,
        "target_height": target_height,
        "interpolation": interpolation,
        "resized": resized,
        "original_width": orig_w,
        "original_height": orig_h,
        "analysis_width": new_w,
        "analysis_height": new_h,
    }

    return PreprocessedImage(
        rgb=rgb,
        gray=gray,
        width=new_w,
        height=new_h,
        channels=3,
        mode=img.mode,
        is_jpeg=is_jpeg,
        original_width=orig_w,
        original_height=orig_h,
        scale_x=scale_x,
        scale_y=scale_y,
        parameters=params,
    )


def encode_artifact_png(array: np.ndarray, normalize: bool = True) -> bytes:
    """
    Encode a numpy array (e.g. heatmap, mask) as PNG bytes for storage.
    Normalizes to 0-255 if needed.
    """
    if normalize and array.dtype != np.uint8:
        arr = array.astype(np.float64)
        mn, mx = arr.min(), arr.max()
        if mx > mn:
            arr = (arr - mn) / (mx - mn) * 255
        else:
            arr = np.zeros_like(arr)
        array = arr.astype(np.uint8)

    if array.ndim == 2:
        img = PILImage.fromarray(array, mode="L")
    elif array.ndim == 3 and array.shape[2] == 3:
        img = PILImage.fromarray(array, mode="RGB")
    else:
        img = PILImage.fromarray(array.squeeze(), mode="L")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
