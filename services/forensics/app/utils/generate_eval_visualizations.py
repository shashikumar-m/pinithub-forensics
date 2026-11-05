"""
Evaluation Visualization Generator — Phase 6.

Generates visual evaluation artifacts for the PinITHUB internship demonstration:
  1. Original image
  2. Ground-truth mask
  3. Predicted heatmap
  4. Predicted binary mask
  5. Overlay (original + heatmap)
  6. False positives
  7. False negatives

Created for edit percentages: 2%, 5%, 10%, 25%, 50%

These visualizations are stored in: training/eval_visualizations/

Usage:
    python -m app.utils.generate_eval_visualizations --output_dir training/eval_visualizations
"""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
from typing import Optional

import numpy as np
import cv2
from PIL import Image as PILImage, ImageDraw

# ---- Synthetic fixture creation ----

def _textured_image(width: int = 256, height: int = 256, seed: int = 42) -> np.ndarray:
    """Create a textured synthetic image suitable for visualization."""
    rng = np.random.RandomState(seed)
    # Create a natural-looking base
    noise = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    arr = noise.copy().astype(np.float32)
    for i in range(0, height, 16):
        arr[i:i+4, :, 0] = 200
    for j in range(0, width, 24):
        arr[:, j:j+3, 1] = 180
    for _ in range(15):
        cx = rng.randint(20, width - 20)
        cy = rng.randint(20, height - 20)
        cv2.circle(arr, (cx, cy), int(rng.randint(5, 20)),
                   (int(rng.randint(0, 255)), int(rng.randint(0, 255)), int(rng.randint(0, 255))), -1)
    return np.clip(arr, 0, 255).astype(np.uint8)


def _create_gt_mask(width: int, height: int, area_pct: float, seed: int = 42) -> np.ndarray:
    """Create a ground-truth mask with ~area_pct% affected pixels."""
    rng = np.random.RandomState(seed)
    mask = np.zeros((height, width), dtype=np.uint8)
    # Place a rectangular region in a random position
    target_pixels = int(width * height * area_pct / 100.0)
    if target_pixels == 0:
        return mask
    region_size = int(np.sqrt(target_pixels))
    region_size = max(4, region_size)
    x = rng.randint(0, max(1, width - region_size))
    y = rng.randint(0, max(1, height - region_size))
    mask[y:y+region_size, x:x+region_size] = 255
    return mask


def _simulate_prediction(gt_mask: np.ndarray, noise_level: float = 0.1, seed: int = 7) -> np.ndarray:
    """Simulate a model prediction (noisy version of ground truth)."""
    rng = np.random.RandomState(seed)
    pred = gt_mask.astype(np.float32) / 255.0
    noise = rng.normal(0, noise_level, pred.shape)
    pred = np.clip(pred + noise, 0.0, 1.0).astype(np.float32)
    return pred


def _make_overlay(image: np.ndarray, heatmap: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """Overlay a heatmap onto an RGB image."""
    h_colored = cv2.applyColorMap(
        (heatmap * 255).astype(np.uint8), cv2.COLORMAP_JET
    )
    h_rgb = cv2.cvtColor(h_colored, cv2.COLOR_BGR2RGB)
    blended = cv2.addWeighted(image, 1 - alpha, h_rgb, alpha, 0)
    return blended


def _make_fp_fn_vis(gt_mask: np.ndarray, pred_bin: np.ndarray) -> np.ndarray:
    """Create a false positive / false negative visualization."""
    h, w = gt_mask.shape
    vis = np.zeros((h, w, 3), dtype=np.uint8)
    # True positives = green
    tp = (pred_bin > 0) & (gt_mask > 0)
    # False positives = red
    fp = (pred_bin > 0) & (gt_mask == 0)
    # False negatives = blue
    fn = (pred_bin == 0) & (gt_mask > 0)
    vis[tp] = [0, 200, 0]    # green = correct detection
    vis[fp] = [200, 0, 0]    # red = false positive
    vis[fn] = [0, 0, 200]    # blue = missed (false negative)
    return vis


def save_png(arr: np.ndarray, path: Path) -> None:
    """Save a numpy array as a PNG."""
    if arr.ndim == 2:
        img = PILImage.fromarray(arr, mode="L")
    else:
        img = PILImage.fromarray(arr, mode="RGB")
    img.save(path)


def generate_visualizations(output_dir: str = "training/eval_visualizations") -> None:
    """Generate all evaluation visualizations for the required edit percentages."""
    edit_percentages = [0.5, 2.0, 5.0, 10.0, 25.0, 50.0]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    width, height = 256, 256

    for pct in edit_percentages:
        label = f"{pct:.1f}pct".replace(".", "_")
        subdir = out / label
        subdir.mkdir(exist_ok=True)

        # 1. Create original image
        original = _textured_image(width, height, seed=42)

        # 2. Create ground-truth mask
        gt_mask = _create_gt_mask(width, height, pct, seed=42)

        # 3. Simulate prediction heatmap
        pred_heatmap = _simulate_prediction(gt_mask, noise_level=0.08, seed=7)

        # 4. Binary prediction mask
        pred_bin = (pred_heatmap > 0.5).astype(np.uint8) * 255

        # 5. Overlay
        overlay = _make_overlay(original, pred_heatmap, alpha=0.45)

        # 6 & 7. FP/FN visualization
        fp_fn = _make_fp_fn_vis(gt_mask, pred_bin)

        # Compute metrics for this visualization
        tp = int(((pred_bin > 0) & (gt_mask > 0)).sum())
        fp_count = int(((pred_bin > 0) & (gt_mask == 0)).sum())
        fn_count = int(((pred_bin == 0) & (gt_mask > 0)).sum())
        eps = 1e-7
        precision = tp / (tp + fp_count + eps)
        recall = tp / (tp + fn_count + eps)
        f1 = 2 * precision * recall / (precision + recall + eps)
        iou = tp / (tp + fp_count + fn_count + eps)

        # Save all artifacts
        save_png(original, subdir / "1_original.png")
        save_png(gt_mask, subdir / "2_ground_truth_mask.png")
        save_png((pred_heatmap * 255).astype(np.uint8), subdir / "3_predicted_heatmap.png")
        save_png(pred_bin, subdir / "4_predicted_mask.png")
        save_png(overlay, subdir / "5_overlay.png")
        save_png(fp_fn, subdir / "6_fp_fn_visualization.png")

        # Save metrics summary
        metrics_text = (
            f"Edit area: {pct:.1f}%\n"
            f"GT pixels: {int((gt_mask > 0).sum())} / {width*height}\n"
            f"Precision: {precision:.4f}\n"
            f"Recall: {recall:.4f}\n"
            f"F1: {f1:.4f}\n"
            f"IoU: {iou:.4f}\n"
            f"\nNote: This is a SYNTHETIC visualization using simulated predictions.\n"
            f"Real metrics require a trained model + labelled dataset.\n"
        )
        (subdir / "metrics.txt").write_text(metrics_text)

        print(f"  {pct:5.1f}% edit -> {subdir.name}/ | F1={f1:.4f} IoU={iou:.4f}")

    print(f"\nVisualisations saved to: {out.resolve()}")
    print("Note: These use SYNTHETIC (simulated) predictions for demonstration.")
    print("Real evaluation requires trained model weights + labelled dataset.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", default="training/eval_visualizations")
    args = parser.parse_args()
    print("Generating Phase 6 evaluation visualizations...")
    generate_visualizations(args.output_dir)
