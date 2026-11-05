"""Run Phase 9A dataset creation + evaluation."""
import os
from app.utils.ai_evaluation_v2 import create_and_freeze_splits, run_frozen_test_evaluation

DATASET_DIR = "ai_forensics/synthetic_eval"
EVAL_OUT    = "training/eval_output"
os.makedirs(DATASET_DIR, exist_ok=True)

print("Creating synthetic dataset + frozen splits...")
r = create_and_freeze_splits(DATASET_DIR, generate_synthetic=True)
print(f"  Train:             {r['train_count']}")
print(f"  Validation:        {r['val_count']}")
print(f"  Frozen test:       {r['test_count']}")
print(f"  Source leakage:    {'YES - ERROR' if not r['leakage_clean'] else 'NO - CLEAN'}")
print(f"  Frozen test hash:  {(r['frozen_test_hash'] or '')[:32]}...")
print()

print("Running frozen test evaluation...")
ev = run_frozen_test_evaluation(DATASET_DIR, EVAL_OUT)

status = ev.get("status", "COMPLETED")
print(f"  Evaluation status: {status}")

if status == "UNAVAILABLE":
    print("  AI model unavailable (no weights loaded)")
    print("  -> Returns UNAVAILABLE, not NO_AI_EVIDENCE")
    print(f"  Frozen test SHA:   {ev['frozen_test_hash'][:32]}...")
    meta = ev.get("model_metadata", {})
    print(f"  Model ID:          {meta.get('model_id')}")
    print(f"  Model version:     {meta.get('model_version')}")
    print(f"  Architecture:      {meta.get('architecture')}")
    print(f"  Backbone:          {meta.get('backbone')}")
    print(f"  Preprocessing:     {meta.get('preprocessing_version')}")
    print(f"  Threshold:         {meta.get('threshold')}")
else:
    print(f"  Total evaluated:   {ev.get('total_evaluated')}")
    img = ev.get("image_level_metrics", {})
    pix = ev.get("pixel_level_metrics", {})
    print(f"  ROC-AUC:           {img.get('roc_auc', 'N/A')}")
    print(f"  PR-AUC:            {img.get('pr_auc', 'N/A')}")
    print(f"  Image F1:          {img.get('f1', 'N/A')}")
    print(f"  Pixel F1:          {pix.get('pixel_f1', 'N/A')}")
    print(f"  IoU:               {pix.get('iou', 'N/A')}")
    print(f"  Dice:              {pix.get('dice', 'N/A')}")
    print(f"  MCC:               {pix.get('mcc', 'N/A')}")
    print()
    print("  Per-area-bucket:")
    for bucket, bm in ev.get("per_area_bucket", {}).items():
        print(f"    {bucket:12s}: {bm['samples']:3d} samples, "
              f"det_rate={bm['detection_rate_pct']:.1f}%, "
              f"pixel_f1={bm.get('mean_pixel_f1', 'N/A')}")

print("\nPhase 9A evaluation complete.")
