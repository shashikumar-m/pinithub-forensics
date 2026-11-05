"""
Travelled-Copy Generator — Phase 7.

Generates realistic transformations of a source image for evaluation.
Every copy has a manifest recording exactly what was applied.

IMPORTANT:
  Platform profiles are SIMULATIONS, not exact reproductions of
  proprietary pipelines. They model common transformations used by
  messaging and social media platforms.

Generator version: 1.0.0
"""
from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image as PILImage, ImageEnhance, ImageFilter

GENERATOR_VERSION = "1.0.0"


# ---- Transformation types ----

TRANSFORM_TYPES = [
    "NONE", "JPEG_RECOMPRESSION", "RESIZE", "CROP", "CROP_AND_RESIZE",
    "ROTATION", "BRIGHTNESS", "CONTRAST", "COLOR_CHANGE", "FILTER",
    "SCREENSHOT", "METADATA_CHANGE", "TEXT_ADDED", "STICKER_ADDED",
    "OBJECT_ADDED", "OBJECT_REMOVED", "AI_EDIT", "AI_GENERATED", "UNKNOWN",
]


@dataclass
class TransformStep:
    """One transformation in a chain."""
    type: str                        # TRANSFORM_TYPES
    parameters: dict = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "parameters": self.parameters,
                "description": self.description}


@dataclass
class TravelledCopyManifest:
    """Records exactly what was applied to produce a travelled copy."""
    source_image: str
    output_image: str
    source_sha256: str
    output_sha256: str
    transformations: list
    generator_version: str
    created_at: str
    severity: str                    # TRANSPORT | CONTENT | COMBINED

    def to_dict(self) -> dict:
        return {
            "source_image": self.source_image,
            "output_image": self.output_image,
            "source_sha256": self.source_sha256,
            "output_sha256": self.output_sha256,
            "transformations": [t.to_dict() if isinstance(t, TransformStep) else t
                                  for t in self.transformations],
            "generator_version": self.generator_version,
            "created_at": self.created_at,
            "severity": self.severity,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_travelled_copy(
    source_bytes: bytes,
    steps: list[TransformStep],
    severity: str = "TRANSPORT",
) -> tuple[bytes, TravelledCopyManifest]:
    """
    Apply a sequence of transformations to source_bytes.
    Returns (output_bytes, manifest).

    The source_bytes are never modified — each step operates on a copy.
    """
    output_bytes = source_bytes
    for step in steps:
        output_bytes = _apply_step(output_bytes, step)

    manifest = TravelledCopyManifest(
        source_image="source",
        output_image="output",
        source_sha256=_sha256(source_bytes),
        output_sha256=_sha256(output_bytes),
        transformations=steps,
        generator_version=GENERATOR_VERSION,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        severity=severity,
    )
    return output_bytes, manifest


def _apply_step(image_bytes: bytes, step: TransformStep) -> bytes:
    """Apply a single transformation step."""
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")

    if step.type == "NONE":
        return image_bytes

    elif step.type == "JPEG_RECOMPRESSION":
        quality = step.parameters.get("quality", 85)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, subsampling=2)
        return buf.getvalue()

    elif step.type == "RESIZE":
        scale = step.parameters.get("scale", 0.75)
        w, h = img.size
        img = img.resize((max(8, int(w * scale)), max(8, int(h * scale))), PILImage.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=step.parameters.get("quality", 90))
        return buf.getvalue()

    elif step.type == "CROP":
        frac = step.parameters.get("crop_fraction", 0.2)
        direction = step.parameters.get("direction", "center")
        w, h = img.size
        kw = max(8, int(w * (1 - frac)))
        kh = max(8, int(h * (1 - frac)))
        if direction == "center":
            x, y = (w - kw) // 2, (h - kh) // 2
        elif direction == "right":
            x, y = 0, 0
            kw = w - int(w * frac)
        elif direction == "top":
            x, y = 0, int(h * frac)
        else:
            x, y = (w - kw) // 2, (h - kh) // 2
        img = img.crop((x, y, x + kw, y + kh))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "CROP_AND_RESIZE":
        frac = step.parameters.get("crop_fraction", 0.2)
        w, h = img.size
        kw = max(8, int(w * (1 - frac)))
        kh = max(8, int(h * (1 - frac)))
        x, y = (w - kw) // 2, (h - kh) // 2
        img = img.crop((x, y, x + kw, y + kh)).resize((w, h), PILImage.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=step.parameters.get("quality", 85))
        return buf.getvalue()

    elif step.type == "ROTATION":
        angle = step.parameters.get("angle", 2.0)
        img = img.rotate(angle, expand=False, resample=PILImage.BILINEAR,
                          fillcolor=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "BRIGHTNESS":
        factor = step.parameters.get("factor", 1.2)
        img = ImageEnhance.Brightness(img).enhance(factor)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "CONTRAST":
        factor = step.parameters.get("factor", 1.3)
        img = ImageEnhance.Contrast(img).enhance(factor)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "COLOR_CHANGE":
        sat = step.parameters.get("saturation", 1.2)
        temp = step.parameters.get("temperature_shift", 10)
        img = ImageEnhance.Color(img).enhance(sat)
        # Simple color temperature shift (warm/cool)
        arr = np.array(img, dtype=np.float32)
        arr[:, :, 0] = np.clip(arr[:, :, 0] + temp, 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] - temp // 2, 0, 255)
        img = PILImage.fromarray(arr.astype(np.uint8))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "FILTER":
        filter_type = step.parameters.get("filter", "unsharp_mask")
        if filter_type == "unsharp_mask":
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=3))
        elif filter_type == "smooth":
            img = img.filter(ImageFilter.SMOOTH_MORE)
        elif filter_type == "edge_enhance":
            img = img.filter(ImageFilter.EDGE_ENHANCE)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "SCREENSHOT":
        # Screenshot simulation: add padding/border and re-encode as JPEG/PNG
        w, h = img.size
        padding = step.parameters.get("padding", 20)
        bg_color = tuple(step.parameters.get("bg_color", [240, 240, 240]))
        canvas = PILImage.new("RGB", (w + 2 * padding, h + 2 * padding), bg_color)
        canvas.paste(img, (padding, padding))
        fmt = step.parameters.get("format", "JPEG")
        buf = io.BytesIO()
        quality = step.parameters.get("quality", 85)
        if fmt == "PNG":
            canvas.save(buf, format="PNG")
        else:
            canvas.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    elif step.type == "METADATA_CHANGE":
        action = step.parameters.get("action", "STRIP")
        if action == "STRIP":
            # Re-encode without EXIF
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
        return image_bytes

    elif step.type == "TEXT_ADDED":
        # Add a text overlay (simulation only)
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        text = step.parameters.get("text", "Sample Text")
        x = step.parameters.get("x", img.width // 4)
        y = step.parameters.get("y", img.height // 4)
        color = tuple(step.parameters.get("color", [255, 255, 255]))
        draw.rectangle([x - 2, y - 2, x + len(text) * 7 + 2, y + 18],
                        fill=(0, 0, 0, 180) if img.mode == "RGBA" else (0, 0, 0))
        draw.text((x, y), text, fill=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    elif step.type == "STICKER_ADDED":
        # Add a solid colored rectangle as sticker simulation
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        x = step.parameters.get("x", img.width // 2)
        y = step.parameters.get("y", img.height // 2)
        size = step.parameters.get("size", 40)
        color = tuple(step.parameters.get("color", [255, 200, 0]))
        draw.rectangle([x, y, x + size, y + size], fill=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    else:
        # Unknown or unimplemented transform — return unchanged
        return image_bytes
