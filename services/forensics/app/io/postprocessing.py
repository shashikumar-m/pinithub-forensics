"""
Post-processing / robustness simulation — Phase 6.

Applies various transformations to images to evaluate detector robustness.
Every transformation is documented and preserved in metadata.

Transformations supported:
  - JPEG compression (quality 95/85/75/60)
  - resize (75%/50%)
  - screenshot simulation (PNG conversion)
  - crop + resize
  - brightness change
  - contrast change
  - mild sharpening

Usage:
    result = apply_postprocessing(image_bytes, config)

The original image is NEVER modified. The transformation is applied to
a copy and the config is preserved for reproducibility.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

from PIL import Image as PILImage, ImageEnhance, ImageFilter

# Available transformation types
JPEG_QUALITIES = [95, 85, 75, 60]
RESIZE_SCALES = [0.75, 0.50]


@dataclass
class TransformationConfig:
    """Defines a single post-processing transformation."""
    type: str                         # jpeg | resize | screenshot | crop_resize | brightness | contrast | sharpen
    jpeg_quality: Optional[int] = None
    resize_scale: Optional[float] = None
    crop_fraction: Optional[float] = None
    brightness_factor: Optional[float] = None
    contrast_factor: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def apply_postprocessing(image_bytes: bytes, config: TransformationConfig) -> bytes:
    """
    Apply a transformation to image bytes.
    Returns transformed bytes. Original bytes are unchanged.
    """
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")

    if config.type == "jpeg":
        quality = config.jpeg_quality or 85
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, subsampling=2)
        return buf.getvalue()

    elif config.type == "resize":
        scale = config.resize_scale or 0.75
        w, h = img.size
        new_w = max(8, int(w * scale))
        new_h = max(8, int(h * scale))
        img = img.resize((new_w, new_h), PILImage.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif config.type == "screenshot":
        # PNG conversion (simulates screenshot)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    elif config.type == "crop_resize":
        frac = config.crop_fraction or 0.1
        w, h = img.size
        margin_x = int(w * frac / 2)
        margin_y = int(h * frac / 2)
        img = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))
        img = img.resize((w, h), PILImage.BILINEAR)  # resize back to original dims
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    elif config.type == "brightness":
        factor = config.brightness_factor or 1.2
        img = ImageEnhance.Brightness(img).enhance(factor)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif config.type == "contrast":
        factor = config.contrast_factor or 1.3
        img = ImageEnhance.Contrast(img).enhance(factor)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif config.type == "sharpen":
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=50, threshold=3))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    else:
        raise ValueError(f"Unknown transformation type: {config.type}")


# Standard robustness evaluation suite
ROBUSTNESS_SUITE: list[TransformationConfig] = [
    TransformationConfig("jpeg", jpeg_quality=95, description="JPEG q=95"),
    TransformationConfig("jpeg", jpeg_quality=85, description="JPEG q=85"),
    TransformationConfig("jpeg", jpeg_quality=75, description="JPEG q=75"),
    TransformationConfig("jpeg", jpeg_quality=60, description="JPEG q=60"),
    TransformationConfig("resize", resize_scale=0.75, description="Resize 75%"),
    TransformationConfig("resize", resize_scale=0.50, description="Resize 50%"),
    TransformationConfig("screenshot", description="Screenshot (PNG)"),
    TransformationConfig("crop_resize", crop_fraction=0.1, description="Crop+resize"),
    TransformationConfig("brightness", brightness_factor=1.2, description="Brightness +20%"),
    TransformationConfig("contrast", contrast_factor=1.3, description="Contrast +30%"),
    TransformationConfig("sharpen", description="Mild sharpen"),
]
