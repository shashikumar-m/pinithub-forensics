"""
Phase 8 — Evaluation Runner & Scientific Results Generator (PinITHUB Plan Section 12).

Evaluates the unified forensic analysis pipeline across:
- Frozen test split
- 10 Edit families:
    generative_fill, generative_inpaint, splicing, copy_move, retouching,
    text_insertion, crop, perspective_warp, color_grading, recompression_pipeline
- 7 Area buckets:
    <0.5%, 0.5–1%, 1–2%, 2–5%, 5–10%, 10–25%, >25%
- Post-processing robustness matrices:
    JPEG Q95/85/75/60, resize, WhatsApp, Instagram, PNG
- Leave-one-tool-out generalization (held-out generator)
- 95% Bootstrap Confidence Intervals (1,000 resamples)

Usage:
    python -m evaluation.run_eval --dataset data/forensics_v1 --update-docs
"""
from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
import time
from typing import Any, Optional

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

from app.pipelines.unified_analysis import run_unified_analysis

logger = logging.getLogger(__name__)


def bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_resamples: int = 1000,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """Computes 95% bootstrap confidence intervals for accuracy, precision, recall, and F1."""
    rng = np.random.RandomState(seed)
    n = len(y_true)
    if n < 5:
        return {}

    accs, precs, recs, f1s = [], [], [], []

    for _ in range(n_resamples):
        idx = rng.randint(0, n, n)
        yt_sample, yp_sample = y_true[idx], y_pred[idx]

        accs.append(accuracy_score(yt_sample, yp_sample))
        precs.append(precision_score(yt_sample, yp_sample, zero_division=0))
        recs.append(recall_score(yt_sample, yp_sample, zero_division=0))
        f1s.append(f1_score(yt_sample, yp_sample, zero_division=0))

    return {
        "accuracy": (round(float(np.percentile(accs, 2.5)), 3), round(float(np.percentile(accs, 97.5)), 3)),
        "precision": (round(float(np.percentile(precs, 2.5)), 3), round(float(np.percentile(precs, 97.5)), 3)),
        "recall": (round(float(np.percentile(recs, 2.5)), 3), round(float(np.percentile(recs, 97.5)), 3)),
        "f1": (round(float(np.percentile(f1s, 2.5)), 3), round(float(np.percentile(f1s, 97.5)), 3)),
    }


def evaluate_dataset(
    dataset_dir: str,
    max_samples: Optional[int] = None,
) -> dict[str, Any]:
    """
    Runs end-to-end evaluation on the frozen test set of dataset_dir.
    """
    base_path = Path(dataset_dir)
    frozen_manifest_path = base_path / "test_frozen_manifest.json"
    if not frozen_manifest_path.exists():
        frozen_manifest_path = base_path / "manifest.json"

    with open(frozen_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", data) if isinstance(data, dict) else data
    if max_samples:
        entries = entries[:max_samples]

    logger.info(f"Evaluating {len(entries)} test samples from {dataset_dir}...")

    y_true: list[int] = []
    y_pred: list[int] = []
    y_scores: list[float] = []

    slice_records: list[dict[str, Any]] = []

    start_time = time.perf_counter()

    for idx, entry in enumerate(entries):
        img_rel = entry["image"]
        img_full = base_path / img_rel
        if not img_full.exists():
            continue

        with open(img_full, "rb") as f:
            suspect_bytes = f.read()

        is_real = entry["label"] == "REAL"
        gt_binary = 0 if is_real else 1

        res = run_unified_analysis(suspect_bytes)
        pred_verdict = res["verdict"]
        prob = res.get("probability", 0.5)

        pred_binary = 1 if pred_verdict == "EDITED" else (0 if pred_verdict == "NOT_EDITED" else 1)

        y_true.append(gt_binary)
        y_pred.append(pred_binary)
        y_scores.append(prob)

        slice_records.append({
            "id": entry.get("id"),
            "edit_type": entry.get("edit_type", "unknown"),
            "area_bucket": entry.get("area_bucket", "NONE"),
            "postprocessing": entry.get("postprocessing", "original"),
            "generator": entry.get("generator"),
            "y_true": gt_binary,
            "y_pred": pred_binary,
            "prob": prob,
        })

    elapsed = round(time.perf_counter() - start_time, 2)

    yt = np.array(y_true)
    yp = np.array(y_pred)
    ys = np.array(y_scores)

    acc = round(float(accuracy_score(yt, yp)), 4) if len(yt) > 0 else 0.0
    prec = round(float(precision_score(yt, yp, zero_division=0)), 4) if len(yt) > 0 else 0.0
    rec = round(float(recall_score(yt, yp, zero_division=0)), 4) if len(yt) > 0 else 0.0
    f1 = round(float(f1_score(yt, yp, zero_division=0)), 4) if len(yt) > 0 else 0.0

    auc = 0.5
    if len(np.unique(yt)) > 1:
        try:
            auc = round(float(roc_auc_score(yt, ys)), 4)
        except Exception:
            auc = 0.5

    ci = bootstrap_ci(yt, yp)

    # --- Slice Metrics: Edit Families ---
    edit_families_metrics: dict[str, dict[str, Any]] = {}
    families = sorted(list({r["edit_type"] for r in slice_records}))
    for fam in families:
        fam_records = [r for r in slice_records if r["edit_type"] == fam]
        fam_yt = np.array([r["y_true"] for r in fam_records])
        fam_yp = np.array([r["y_pred"] for r in fam_records])
        if len(fam_yt) > 0:
            edit_families_metrics[fam] = {
                "count": len(fam_records),
                "accuracy": round(float(accuracy_score(fam_yt, fam_yp)), 3),
                "recall": round(float(recall_score(fam_yt, fam_yp, zero_division=0)), 3),
            }

    # --- Slice Metrics: Area Buckets ---
    area_bucket_metrics: dict[str, dict[str, Any]] = {}
    buckets = sorted(list({r["area_bucket"] for r in slice_records if r["area_bucket"] != "NONE"}))
    for b in buckets:
        b_records = [r for r in slice_records if r["area_bucket"] == b]
        b_yt = np.array([r["y_true"] for r in b_records])
        b_yp = np.array([r["y_pred"] for r in b_records])
        if len(b_yt) > 0:
            area_bucket_metrics[b] = {
                "count": len(b_records),
                "accuracy": round(float(accuracy_score(b_yt, b_yp)), 3),
                "recall": round(float(recall_score(b_yt, b_yp, zero_division=0)), 3),
            }

    # --- Robustness Matrix ---
    robustness_metrics: dict[str, dict[str, Any]] = {}
    variants = sorted(list({r["postprocessing"] for r in slice_records}))
    for var in variants:
        v_records = [r for r in slice_records if r["postprocessing"] == var]
        v_yt = np.array([r["y_true"] for r in v_records])
        v_yp = np.array([r["y_pred"] for r in v_records])
        if len(v_yt) > 0:
            robustness_metrics[var] = {
                "count": len(v_records),
                "accuracy": round(float(accuracy_score(v_yt, v_yp)), 3),
                "f1": round(float(f1_score(v_yt, v_yp, zero_division=0)), 3),
            }

    # --- Leave-One-Tool-Out (Holdout Generator) ---
    holdout_records = [r for r in slice_records if r.get("generator") == "flux_1_schnell"]
    holdout_acc = None
    if holdout_records:
        h_yt = np.array([r["y_true"] for r in holdout_records])
        h_yp = np.array([r["y_pred"] for r in holdout_records])
        holdout_acc = round(float(accuracy_score(h_yt, h_yp)), 3)

    return {
        "n_samples": len(yt),
        "elapsed_seconds": elapsed,
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "roc_auc": auc,
        "confidence_intervals_95": ci,
        "edit_families": edit_families_metrics,
        "area_buckets": area_bucket_metrics,
        "robustness": robustness_metrics,
        "holdout_generator": {
            "name": "flux_1_schnell",
            "count": len(holdout_records),
            "accuracy": holdout_acc,
        },
    }


def format_results_markdown(metrics: dict[str, Any]) -> str:
    """Formats full evaluation metrics into rich GitHub Flavored Markdown."""
    ci = metrics.get("confidence_intervals_95", {})
    acc_ci = ci.get("accuracy", (metrics["accuracy"], metrics["accuracy"]))
    f1_ci = ci.get("f1", (metrics["f1"], metrics["f1"]))

    lines = [
        "## Scientific Evaluation & Benchmarks (Phase 8)",
        "",
        f"Evaluated on **{metrics['n_samples']}** frozen test split samples in {metrics['elapsed_seconds']}s.",
        "",
        "### Global Performance Metrics",
        "",
        "| Metric | Score | 95% Bootstrap CI | Target (Plan §12) |",
        "|---|---|---|---|",
        f"| **Accuracy** | **{metrics['accuracy']:.1%}** | [{acc_ci[0]:.1%}, {acc_ci[1]:.1%}] | >= 85.0% |",
        f"| **Precision** | **{metrics['precision']:.1%}** | [{ci.get('precision', (0,0))[0]:.1%}, {ci.get('precision', (0,0))[1]:.1%}] | >= 80.0% |",
        f"| **Recall** | **{metrics['recall']:.1%}** | [{ci.get('recall', (0,0))[0]:.1%}, {ci.get('recall', (0,0))[1]:.1%}] | >= 80.0% |",
        f"| **F1-Score** | **{metrics['f1']:.3f}** | [{f1_ci[0]:.3f}, {f1_ci[1]:.3f}] | >= 0.820 |",
        f"| **ROC-AUC** | **{metrics['roc_auc']:.3f}** | — | >= 0.850 |",
        "",
        "### Slice Performance: 10 Edit Families",
        "",
        "| Edit Family | Sample Count | Accuracy | Recall |",
        "|---|---|---|---|",
    ]

    for fam, stats in metrics.get("edit_families", {}).items():
        lines.append(f"| `{fam}` | {stats['count']} | {stats['accuracy']:.1%} | {stats['recall']:.1%} |")

    lines.extend([
        "",
        "### Slice Performance: 7 Area Buckets",
        "",
        "| Area Bucket | Target Size | Sample Count | Recall |",
        "|---|---|---|---|",
    ])

    for b, stats in metrics.get("area_buckets", {}).items():
        note = "Key evaluation threshold" if b == "1–2%" else "Standard slice"
        lines.append(f"| `{b}` | {note} | {stats['count']} | {stats['recall']:.1%} |")

    lines.extend([
        "",
        "### Post-Processing Robustness Matrix",
        "",
        "| Post-Processing Pipeline | Sample Count | Accuracy | F1-Score |",
        "|---|---|---|---|",
    ])

    for var, stats in metrics.get("robustness", {}).items():
        lines.append(f"| `{var}` | {stats['count']} | {stats['accuracy']:.1%} | {stats['f1']:.3f} |")

    holdout = metrics.get("holdout_generator", {})
    lines.extend([
        "",
        "### Out-of-Distribution Generalization (Held-out Generator)",
        "",
        f"- **Held-out Tool**: `{holdout.get('name')}` (unseen during threshold selection)",
        f"- **Test Samples**: {holdout.get('count')}",
        f"- **Generalization Accuracy**: **{holdout.get('accuracy', 0.0):.1%}**",
        "",
    ])

    return "\n".join(lines)


def update_results_doc(metrics: dict[str, Any], doc_path: str = "docs/RESULTS.md") -> None:
    """Updates docs/RESULTS.md with newly computed benchmarks."""
    p = Path(doc_path)
    content = ""
    if p.exists():
        content = p.read_text(encoding="utf-8")

    section_header = "## Scientific Evaluation & Benchmarks (Phase 8)"
    new_section = format_results_markdown(metrics)

    if section_header in content:
        # Replace existing section
        parts = content.split(section_header)
        # Keep everything before, replace until next main header or end
        pre = parts[0]
        content = pre + new_section
    else:
        content = content + "\n\n" + new_section

    p.write_text(content, encoding="utf-8")
    logger.info(f"Updated {doc_path} with Phase 8 benchmarks.")


def main():
    parser = argparse.ArgumentParser(description="Run Full Forensics Evaluation (Phase 8)")
    parser.add_argument("--dataset", type=str, default="data/forensics_v1")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--update-docs", action="store_true", default=True)
    args = parser.parse_args()

    metrics = evaluate_dataset(args.dataset, max_samples=args.max_samples)
    print(format_results_markdown(metrics))

    if args.update_docs:
        update_results_doc(metrics)


if __name__ == "__main__":
    main()
