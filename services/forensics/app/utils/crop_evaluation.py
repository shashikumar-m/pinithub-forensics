"""
Crop Percentage Evaluation Script — Phase 5.

Generates synthetic test images at known crop percentages and evaluates
detector accuracy. Reports MAE, median error, and per-bucket metrics.

Usage:
    python -m app.utils.crop_evaluation

Ground truth is NEVER exposed to the detector during inference.
"""
from __future__ import annotations

import io
import json
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image as PILImage, ImageEnhance
import cv2

from app.detectors.crop_detector import get_crop_detector


CROP_PERCENTAGES = [10, 20, 30, 40, 50, 60, 70, 80, 90]
VARIANTS_PER_CROP = 5  # number of transform variants per crop percentage


def _textured_jpeg(width: int = 256, height: int = 256, seed: int = 7) -> bytes:
    rng = np.random.RandomState(seed)
    noise = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    arr = noise.copy().astype(np.float32)
    for i in range(0, height, 16):
        arr[i:i+4, :, 0] = 200
    for j in range(0, width, 24):
        arr[:, j:j+3, 1] = 180
    for _ in range(20):
        cx = rng.randint(20, width - 20)
        cy = rng.randint(20, height - 20)
        cv2.circle(arr, (cx, cy), rng.randint(5, 20),
                   (int(rng.randint(0, 255)), int(rng.randint(0, 255)), int(rng.randint(0, 255))), -1)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _crop_to_percentage(original: bytes, pct: float, direction: str = "center") -> tuple[bytes, float]:
    """
    Crop the image so that `pct` percent of the area is removed.
    Returns (cropped_bytes, actual_crop_pct).
    The actual percentage may differ slightly due to rounding.
    """
    img = PILImage.open(io.BytesIO(original))
    w, h = img.size
    keep = 1.0 - pct / 100.0
    kw = max(8, int(w * np.sqrt(keep)))
    kh = max(8, int(h * np.sqrt(keep)))

    if direction == "center":
        x, y = (w - kw) // 2, (h - kh) // 2
    elif direction == "left":
        x, y = w - kw, 0
    elif direction == "right":
        x, y = 0, 0
    elif direction == "top":
        x, y = 0, h - kh
    else:
        x, y = (w - kw) // 2, (h - kh) // 2

    cropped = img.crop((x, y, x + kw, y + kh))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    actual_pct = 100.0 * (1.0 - (kw * kh) / (w * h))
    return buf.getvalue(), actual_pct


def _apply_variant(image_bytes: bytes, variant: int) -> bytes:
    """Apply a post-crop transformation variant."""
    img = PILImage.open(io.BytesIO(image_bytes))
    if variant == 1:
        # JPEG recompress
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        return buf.getvalue()
    elif variant == 2:
        # Resize to 80%
        w, h = img.size
        img = img.resize((max(8, int(w * 0.8)), max(8, int(h * 0.8))), PILImage.BILINEAR)
    elif variant == 3:
        # Brightness change
        img = ImageEnhance.Brightness(img).enhance(1.3)
    elif variant == 4:
        # Mild rotation
        img = img.rotate(5, expand=False, fillcolor=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@dataclass
class EvalSample:
    gt_crop_pct: float
    actual_gt_pct: float
    predicted_pct: Optional[float]
    status: str
    abs_error: Optional[float]
    signed_error: Optional[float]
    variant: int
    direction: str
    execution_ms: int


def run_evaluation(seeds: list = None) -> dict:
    """
    Run the full crop evaluation.
    Returns a structured result dict.
    """
    if seeds is None:
        seeds = [42, 77, 133]  # multiple reference images

    detector = get_crop_detector()
    samples: list[EvalSample] = []
    directions = ["center", "left", "top"]

    for seed in seeds:
        ref = _textured_jpeg(256, 256, seed=seed)
        for gt_pct in CROP_PERCENTAGES:
            for vi in range(VARIANTS_PER_CROP):
                direction = directions[vi % len(directions)]
                variant = vi % 5

                cropped, actual_gt = _crop_to_percentage(ref, gt_pct, direction)
                suspect = _apply_variant(cropped, variant)

                t0 = time.perf_counter()
                try:
                    result = detector.run("", reference_bytes=ref, suspect_bytes=suspect)
                    exec_ms = int((time.perf_counter() - t0) * 1000)
                    d = result.details
                    predicted = d.get("crop_percentage")
                    status = d.get("status", "FAILED")
                except Exception as e:
                    exec_ms = int((time.perf_counter() - t0) * 1000)
                    predicted = None
                    status = "FAILED"

                abs_err = abs(predicted - actual_gt) if predicted is not None else None
                signed_err = (predicted - actual_gt) if predicted is not None else None

                samples.append(EvalSample(
                    gt_crop_pct=gt_pct,
                    actual_gt_pct=round(actual_gt, 2),
                    predicted_pct=round(predicted, 2) if predicted is not None else None,
                    status=status,
                    abs_error=round(abs_err, 2) if abs_err is not None else None,
                    signed_error=round(signed_err, 2) if signed_err is not None else None,
                    variant=variant,
                    direction=direction,
                    execution_ms=exec_ms,
                ))

    return _compute_metrics(samples)


def _compute_metrics(samples: list[EvalSample]) -> dict:
    total = len(samples)
    detected = [s for s in samples if s.predicted_pct is not None]
    inconclusive = [s for s in samples if s.status in ("INCONCLUSIVE", "NO_MATCH")]
    failed = [s for s in samples if s.status == "FAILED"]

    abs_errors = [s.abs_error for s in detected if s.abs_error is not None]

    global_metrics: dict = {}
    if abs_errors:
        global_metrics = {
            "mae": round(float(np.mean(abs_errors)), 2),
            "median_ae": round(float(np.median(abs_errors)), 2),
            "max_ae": round(float(np.max(abs_errors)), 2),
            "within_1pct": round(sum(e <= 1.0 for e in abs_errors) / len(abs_errors) * 100, 1),
            "within_2pct": round(sum(e <= 2.0 for e in abs_errors) / len(abs_errors) * 100, 1),
            "within_5pct": round(sum(e <= 5.0 for e in abs_errors) / len(abs_errors) * 100, 1),
            "within_10pct": round(sum(e <= 10.0 for e in abs_errors) / len(abs_errors) * 100, 1),
        }

    per_bucket: dict = {}
    for pct in CROP_PERCENTAGES:
        bucket = [s for s in samples if s.gt_crop_pct == pct]
        detected_b = [s for s in bucket if s.predicted_pct is not None]
        errs = [s.abs_error for s in detected_b if s.abs_error is not None]
        per_bucket[str(pct)] = {
            "total_samples": len(bucket),
            "detected": len(detected_b),
            "inconclusive_or_no_match": sum(1 for s in bucket if s.status in ("INCONCLUSIVE", "NO_MATCH")),
            "failed": sum(1 for s in bucket if s.status == "FAILED"),
            "mae": round(float(np.mean(errs)), 2) if errs else None,
            "median_ae": round(float(np.median(errs)), 2) if errs else None,
            "max_ae": round(float(np.max(errs)), 2) if errs else None,
            "sample_predictions": [
                {"gt": s.actual_gt_pct, "predicted": s.predicted_pct, "status": s.status}
                for s in detected_b[:3]  # show first 3
            ],
        }

    return {
        "dataset": "synthetic_crop_evaluation_v1",
        "total_samples": total,
        "successful_detections": len(detected),
        "inconclusive": len(inconclusive),
        "failed": len(failed),
        "detection_rate_pct": round(len(detected) / total * 100, 1) if total > 0 else 0,
        "global_metrics": global_metrics,
        "per_bucket": per_bucket,
        "note": (
            "Crop percentage evaluation on synthetic images. "
            "Errors below 5% indicate reliable detection. "
            "Inconclusive results mean registration evidence was insufficient — "
            "not a failure but an honest acknowledgment of limitation."
        ),
    }


if __name__ == "__main__":
    print("Running crop percentage evaluation...")
    result = run_evaluation()

    # Serialize numpy types for JSON
    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.float32, np.float64)):
                return float(obj)
            if isinstance(obj, (np.int32, np.int64)):
                return int(obj)
            return super().default(obj)

    print(json.dumps(result, indent=2, cls=NumpyEncoder))
    print(f"\nDetection rate: {result['detection_rate_pct']}%")
    if result["global_metrics"]:
        print(f"MAE: {result['global_metrics']['mae']}%")
        print(f"Median AE: {result['global_metrics']['median_ae']}%")
        print(f"Within ±5%: {result['global_metrics']['within_5pct']}%")
