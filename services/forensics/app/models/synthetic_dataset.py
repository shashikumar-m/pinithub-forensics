"""
Synthetic Dataset Generator — Phase 9A.

Generates a controlled synthetic AI-forensics dataset for evaluation.
Since no real labelled dataset exists, this creates:
  - REAL images (textured synthetic images)
  - AI_EDITED_LOCAL images with known ground-truth masks
  - AI_GENERATED images (fully-noise images as stand-in)

Edit area targets:
  <0.5%, 0.5–1%, 1–2%, 2–5%, 5–10%, 10–25%, >25%

The 2% bucket is especially important per Phase 9A requirements.

Ground-truth masks are binary PNG files (255=edited, 0=clean).
Area percentages are computed from actual mask pixel counts.

This dataset is NOT for training — it is for evaluation only.
Do not use this to tune thresholds or model selection.

Dataset version: synthetic_v1
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image as PILImage

from app.models.ai_dataset import ManifestEntry

DATASET_VERSION = "synthetic_v1"
GENERATOR_SEED = 42


def _textured_image(width: int = 256, height: int = 256, seed: int = 42) -> np.ndarray:
    """Create a textured synthetic image."""
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8).astype(np.float32)
    for i in range(0, height, 16):
        arr[i:i+4, :, 0] = 200
    for j in range(0, width, 24):
        arr[:, j:j+3, 1] = 180
    for _ in range(15):
        cx = rng.randint(20, width - 20)
        cy = rng.randint(20, height - 20)
        cv2.circle(arr, (cx, cy), int(rng.randint(5, 20)),
                   (int(rng.randint(0, 255)),) * 3, -1)
    return np.clip(arr, 0, 255).astype(np.uint8)


def _create_edit_mask(
    width: int, height: int, target_pct: float, seed: int = 0
) -> tuple[np.ndarray, float]:
    """
    Create a binary mask with approximately target_pct% of pixels set.
    Returns (mask_array, actual_pct).
    Mask is 0/255 uint8.
    """
    rng = np.random.RandomState(seed)
    mask = np.zeros((height, width), dtype=np.uint8)
    target_pixels = int(width * height * target_pct / 100.0)
    if target_pixels < 1:
        return mask, 0.0

    size = max(2, int(np.sqrt(target_pixels)))
    x = rng.randint(0, max(1, width - size))
    y = rng.randint(0, max(1, height - size))
    mask[y:y+size, x:x+size] = 255

    actual_pct = float(mask.sum() // 255) / (width * height) * 100.0
    return mask, round(actual_pct, 4)


def _apply_edit_to_image(image: np.ndarray, mask: np.ndarray, seed: int = 0) -> np.ndarray:
    """Apply a synthetic 'AI edit' to the masked region."""
    rng = np.random.RandomState(seed)
    edited = image.copy()
    # Replace masked pixels with a contrasting solid color
    color = (int(rng.randint(200, 255)), int(rng.randint(50, 150)), int(rng.randint(50, 150)))
    edited[mask > 0] = color
    return edited


def generate_synthetic_dataset(
    output_dir: str,
    n_real: int = 20,
    target_edit_pcts: Optional[list] = None,
    n_generated: int = 10,
    image_size: int = 256,
    seed: int = GENERATOR_SEED,
) -> list[ManifestEntry]:
    """
    Generate a synthetic evaluation dataset.
    Returns list of ManifestEntry.

    Edit targets:
      [0.3, 0.7, 1.5, 3.0, 7.5, 15.0, 40.0]
      covering each bucket: <0.5, 0.5-1, 1-2, 2-5, 5-10, 10-25, >25
    """
    if target_edit_pcts is None:
        target_edit_pcts = [0.3, 0.7, 1.5, 3.0, 7.5, 15.0, 40.0]

    out = Path(output_dir)
    (out / "real").mkdir(parents=True, exist_ok=True)
    (out / "ai_edited").mkdir(parents=True, exist_ok=True)
    (out / "ai_generated").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(parents=True, exist_ok=True)
    (out / "manifests").mkdir(parents=True, exist_ok=True)
    (out / "splits").mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    entries: list[ManifestEntry] = []

    # ---- Real images ----
    for i in range(n_real):
        img_arr = _textured_image(image_size, image_size, seed=i * 7 + seed)
        img_path = f"real/real_{i:04d}.jpg"
        full_path = out / img_path
        PILImage.fromarray(img_arr).save(full_path, format="JPEG", quality=90)
        entries.append(ManifestEntry(
            image=img_path,
            label="REAL",
            split="",
            source_image=img_path,
            dataset_version=DATASET_VERSION,
        ))

    # ---- AI-edited images ----
    for i in range(n_real):
        for j, tgt_pct in enumerate(target_edit_pcts):
            src_seed = i * 7 + seed
            src_arr = _textured_image(image_size, image_size, seed=src_seed)
            mask_arr, actual_pct = _create_edit_mask(
                image_size, image_size, tgt_pct, seed=i * 100 + j
            )
            if actual_pct == 0:
                continue

            edited_arr = _apply_edit_to_image(src_arr, mask_arr, seed=i * 50 + j)

            img_path = f"ai_edited/edited_{i:04d}_p{j}.jpg"
            mask_path = f"masks/mask_{i:04d}_p{j}.png"
            full_img = out / img_path
            full_mask = out / mask_path

            PILImage.fromarray(edited_arr).save(full_img, format="JPEG", quality=90)
            PILImage.fromarray(mask_arr).save(full_mask, format="PNG")

            entries.append(ManifestEntry(
                image=img_path,
                label="AI_EDITED_LOCAL",
                split="",
                source_image=f"real/real_{i:04d}.jpg",
                edit_type="generative_fill",
                mask=mask_path,
                edited_area_percentage=actual_pct,
                generator="synthetic_v1",
                dataset_version=DATASET_VERSION,
            ))

    # ---- AI-generated images ----
    for i in range(n_generated):
        rng2 = np.random.RandomState(seed + i * 13 + 1000)
        arr = rng2.randint(0, 255, (image_size, image_size, 3), dtype=np.uint8)
        img_path = f"ai_generated/gen_{i:04d}.jpg"
        PILImage.fromarray(arr).save(out / img_path, format="JPEG", quality=90)
        entries.append(ManifestEntry(
            image=img_path,
            label="AI_GENERATED",
            split="",
            source_image=img_path,
            generator="synthetic_noise_v1",
            dataset_version=DATASET_VERSION,
        ))

    return entries
