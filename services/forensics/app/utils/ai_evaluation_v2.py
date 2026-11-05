"""
AI Detection Evaluation v2 — Phase 9A.

Complete evaluation including:
  - Image-level: ROC-AUC, PR-AUC, F1, balanced accuracy, TPR@FPR1%, TPR@FPR5%
  - Pixel-level: precision, recall, F1, IoU, Dice, MCC
  - Region-level: region recall
  - Per-area-bucket metrics (especially 2–5%)
  - Versioned output

Uses the FROZEN test set only — never the train/val sets.
Does NOT tune thresholds on test data.

Model metadata is recorded in every evaluation output.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image as PILImage

from app.models.ai_dataset import AIForensicsManifest, AREA_BUCKETS, ManifestEntry
from app.models.ai_model_registry import get_ai_model_loader, DEFAULT_THRESHOLD
from app.models.dataset_splitter import load_frozen_test
from app.detectors.ai_detector import get_ai_detector

EVAL_VERSION = "eval_v1"


def _compute_pixel_metrics(
    pred_prob: np.ndarray,
    gt_mask: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Pixel-level segmentation metrics."""
    pred_bin = (pred_prob > threshold).astype(np.float32)
    gt_bin   = (gt_mask > 127).astype(np.float32)
    eps = 1e-7
    tp = float((pred_bin * gt_bin).sum())
    fp = float((pred_bin * (1 - gt_bin)).sum())
    fn = float(((1 - pred_bin) * gt_bin).sum())
    tn = float(((1 - pred_bin) * (1 - gt_bin)).sum())

    precision = tp / (tp + fp + eps)
    recall    = tp / (tp + fn + eps)
    f1        = 2 * precision * recall / (precision + recall + eps)
    iou       = tp / (tp + fp + fn + eps)
    dice      = 2 * tp / (2 * tp + fp + fn + eps)

    # MCC
    num = tp * tn - fp * fn
    den = ((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)) ** 0.5
    mcc = num / (den + eps)

    return {
        "pixel_precision": round(precision, 4),
        "pixel_recall":    round(recall, 4),
        "pixel_f1":        round(f1, 4),
        "iou":             round(iou, 4),
        "dice":            round(dice, 4),
        "mcc":             round(float(mcc), 4),
    }


def _compute_image_metrics(
    labels: list[int],
    scores: list[float],
) -> dict:
    """Image-level binary classification metrics."""
    metrics: dict = {}
    try:
        from sklearn.metrics import (
            roc_auc_score, average_precision_score,
            precision_score, recall_score, f1_score, balanced_accuracy_score,
            roc_curve,
        )
        if len(set(labels)) < 2:
            metrics["note"] = "Only one class present — skipping ROC metrics"
            return metrics

        preds_bin = [1 if s >= DEFAULT_THRESHOLD else 0 for s in scores]
        metrics["roc_auc"]           = round(roc_auc_score(labels, scores), 4)
        metrics["pr_auc"]            = round(average_precision_score(labels, scores), 4)
        metrics["f1"]                = round(f1_score(labels, preds_bin, zero_division=0), 4)
        metrics["precision"]         = round(precision_score(labels, preds_bin, zero_division=0), 4)
        metrics["recall"]            = round(recall_score(labels, preds_bin, zero_division=0), 4)
        metrics["balanced_accuracy"] = round(balanced_accuracy_score(labels, preds_bin), 4)

        # TPR at FPR 1% and 5%
        fpr, tpr, _ = roc_curve(labels, scores)
        def tpr_at_fpr(target_fpr):
            idx = np.searchsorted(fpr, target_fpr)
            if idx >= len(tpr): return float(tpr[-1])
            return float(tpr[idx])

        metrics["tpr_at_fpr_1pct"] = round(tpr_at_fpr(0.01), 4)
        metrics["tpr_at_fpr_5pct"] = round(tpr_at_fpr(0.05), 4)
    except Exception as e:
        metrics["image_metrics_error"] = str(e)
    return metrics


def run_frozen_test_evaluation(
    dataset_dir: str,
    output_dir: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """
    Run evaluation on the frozen test set.

    This is the only function allowed to read frozen_test.json.
    It does NOT touch train or val data.
    Threshold must NOT be tuned using the results here.
    """
    frozen = load_frozen_test(dataset_dir)
    if frozen is None:
        return {"error": "Frozen test manifest not found. Run create_and_freeze_splits first."}

    loader = get_ai_model_loader()
    detector = get_ai_detector()
    model_meta = loader.get_metadata()

    if not model_meta.is_available:
        return {
            "status": "UNAVAILABLE",
            "message": "AI model not loaded. Train and provide weights via AI_WEIGHTS_PATH.",
            "model_metadata": model_meta.to_dict(),
            "frozen_test_hash": frozen.manifest_sha256,
        }

    manifest = AIForensicsManifest(dataset_dir)
    # Load only the frozen test entries
    test_entries = manifest.load("test")
    if not test_entries:
        return {"error": "No test entries in manifests/test.jsonl"}

    dataset_path = Path(dataset_dir)
    results = []
    all_labels = []
    all_scores = []
    all_pixel_metrics = []

    for entry in test_entries:
        img_path = dataset_path / entry.image
        if not img_path.exists():
            results.append({"image": entry.image, "status": "FILE_NOT_FOUND"})
            continue

        with open(img_path, "rb") as f:
            img_bytes = f.read()

        t0 = time.perf_counter()
        # Get raw probability map for pixel metrics
        prob_map = loader.predict(img_bytes)
        elapsed = int((time.perf_counter() - t0) * 1000)

        if prob_map is None:
            results.append({"image": entry.image, "status": "UNAVAILABLE"})
            continue

        # Image-level score
        score = float(prob_map.mean())
        label_bin = 0 if entry.label == "REAL" else 1
        all_labels.append(label_bin)
        all_scores.append(score)

        # Pixel-level metrics if mask exists
        pix_metrics = None
        if entry.mask:
            mask_path = dataset_path / entry.mask
            if mask_path.exists():
                gt_mask = np.array(PILImage.open(mask_path).convert("L"), dtype=np.uint8)
                # Resize prob_map to match gt_mask
                from PIL import Image as PILImage2
                pm_img = PILImage2.fromarray((prob_map * 255).astype(np.uint8), mode="L")
                h, w = gt_mask.shape
                pm_resized = np.array(pm_img.resize((w, h), PILImage2.BILINEAR),
                                       dtype=np.float32) / 255.0
                pix_metrics = _compute_pixel_metrics(pm_resized, gt_mask, threshold)
                all_pixel_metrics.append(pix_metrics)

        # Region count
        det_result = detector.run("", image_bytes=img_bytes,
                                    params={"threshold": threshold})
        region_count = len(det_result.details.get("regions", []))

        results.append({
            "image": entry.image,
            "label": entry.label,
            "area_bucket": entry.area_bucket,
            "edited_area_pct": entry.edited_area_percentage,
            "image_score": round(score, 4),
            "region_count": region_count,
            "pixel_metrics": pix_metrics,
            "elapsed_ms": elapsed,
            "status": "COMPLETED",
        })

    # Aggregate image-level metrics
    image_metrics = _compute_image_metrics(all_labels, all_scores) if all_scores else {}

    # Aggregate pixel-level metrics
    pixel_agg: dict = {}
    if all_pixel_metrics:
        for key in ["pixel_precision", "pixel_recall", "pixel_f1", "iou", "dice", "mcc"]:
            vals = [m[key] for m in all_pixel_metrics if key in m]
            if vals:
                pixel_agg[key] = round(float(np.mean(vals)), 4)

    # Per-area-bucket metrics
    bucket_metrics: dict = {}
    for lo, hi, name in AREA_BUCKETS:
        bucket = [r for r in results
                  if r.get("area_bucket") == name
                  and r.get("label") == "AI_EDITED_LOCAL"
                  and r.get("status") == "COMPLETED"]
        if not bucket:
            continue
        detected = sum(1 for r in bucket if r.get("region_count", 0) > 0)
        pms = [r["pixel_metrics"] for r in bucket if r.get("pixel_metrics")]
        bucket_f1 = round(float(np.mean([m["pixel_f1"] for m in pms])), 4) if pms else None
        bucket_metrics[name] = {
            "samples": len(bucket),
            "detected_regions": detected,
            "detection_rate_pct": round(detected / max(1, len(bucket)) * 100, 1),
            "mean_pixel_f1": bucket_f1,
        }

    # Save versioned output
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    out_path = out_dir / f"evaluation_{ts}.json"

    evaluation_record = {
        "eval_version": EVAL_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_metadata": model_meta.to_dict(),
        "dataset_version": frozen.dataset_version,
        "frozen_test_sha256": frozen.manifest_sha256,
        "frozen_test_entry_count": frozen.entry_count,
        "threshold": threshold,
        "total_evaluated": len([r for r in results if r.get("status") == "COMPLETED"]),
        "unavailable": len([r for r in results if r.get("status") == "UNAVAILABLE"]),
        "not_found": len([r for r in results if r.get("status") == "FILE_NOT_FOUND"]),
        "image_level_metrics": image_metrics,
        "pixel_level_metrics": pixel_agg,
        "per_area_bucket": bucket_metrics,
        "note": (
            "Frozen test evaluation. "
            "Threshold was NOT tuned using this data. "
            "Model is UNCALIBRATED. "
            "Results are experimental."
        ),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(evaluation_record, f, indent=2)

    return evaluation_record


def create_and_freeze_splits(
    dataset_dir: str,
    output_dir: Optional[str] = None,
    seed: int = 42,
    generate_synthetic: bool = True,
) -> dict:
    """
    One-shot: generate synthetic dataset, split, freeze test set.
    Idempotent — if frozen_test.json already exists, skip.
    """
    from app.models.synthetic_dataset import generate_synthetic_dataset
    from app.models.dataset_splitter import (
        create_splits, load_frozen_test, validate_no_leakage
    )

    frozen_path = Path(dataset_dir) / "splits" / "frozen_test.json"

    entries = []
    if generate_synthetic:
        entries = generate_synthetic_dataset(dataset_dir)

    if not entries:
        manifest = AIForensicsManifest(dataset_dir)
        all_splits = manifest.load_all()
        for split_entries in all_splits.values():
            entries.extend(split_entries)

    if not entries:
        return {"error": "No dataset entries found or generated."}

    train, val, test = create_splits(entries, dataset_dir, seed=seed)

    violations = validate_no_leakage(train, val, test)
    frozen = load_frozen_test(dataset_dir)

    return {
        "train_count": len(train),
        "val_count": len(val),
        "test_count": len(test),
        "source_leakage_violations": violations,
        "leakage_clean": len(violations) == 0,
        "frozen_test_hash": frozen.manifest_sha256 if frozen else None,
        "frozen_test_path": str(frozen_path),
    }
