"""
Comprehensive Benchmark Sweep & Confusion Matrix Generator for PINIT Forensics.
Evaluates the multi-model consensus engine across authentic camera, AI-generated,
manipulated/inpainted, and internet/compressed media.
"""
import os
import io
import json
import time
from pathlib import Path
from collections import defaultdict

# Ensure models and offline mode are configured
if not os.environ.get("AI_WEIGHTS_PATH"):
    default_p = Path("models/ai_detector_v1.pth").resolve()
    if default_p.exists():
        os.environ["AI_WEIGHTS_PATH"] = str(default_p)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from app.pipelines.unified_analysis import run_unified_analysis


def evaluate_match(actual_cat: str, detected_cat: str, final_call: str, real_pct: float, ai_pct: float) -> tuple[bool, str]:
    actual = actual_cat.lower().strip()
    detected = detected_cat.upper().strip()

    if "camera" in actual or "original" in actual:
        if detected in ["CAMERA_CAPTURED", "NOT_EDITED", "DIGITALLY_ENHANCED"] or real_pct >= 75.0:
            return True, f"Correct: Authentic camera capture verified ({real_pct:.1f}% Real)"
        else:
            return False, f"False Positive: Camera photo flagged as {detected} ({ai_pct:.1f}% AI)"

    elif "ai-gen" in actual or "ai_gen" in actual or actual == "ai-generated":
        if detected in ["AI_GENERATED"] or final_call == "FULL_AI_GENERATED" or ai_pct >= 70.0:
            return True, f"Correct: Synthetic AI diffusion fingerprint detected ({ai_pct:.1f}% AI)"
        else:
            return False, f"False Negative: AI image missed, classified as {detected} ({real_pct:.1f}% Real)"

    elif "edit" in actual or "inpaint" in actual or "manipulat" in actual:
        if detected in ["AI_EDITED", "EDITED", "MANUALLY_EDITED"] or "EDIT" in final_call or ai_pct >= 15.0:
            return True, f"Correct: Localized manipulation / edit detected ({ai_pct:.1f}% Tampered)"
        else:
            return False, f"Missed Edit: Tampered region not detected, classified as {detected}"

    elif "internet" in actual or "whatsapp" in actual or "compressed" in actual:
        if detected in ["CAMERA_CAPTURED", "NOT_EDITED", "DIGITALLY_ENHANCED", "INCONCLUSIVE"]:
            return True, f"Correct: Web/messaging compressed photo identified without false generative flags"
        else:
            return False, f"Compression False Alarm: Mistaken for {detected} ({ai_pct:.1f}% AI)"

    # Default fallback
    is_correct = (actual in detected.lower()) or (detected.lower() in actual)
    return is_correct, f"Evaluated as {'Correct' if is_correct else 'Incorrect'}"


def run_sweep(max_samples: int = None):
    records_path = Path("eval_bench_data/records.json")
    images_dir = Path("eval_bench_data/images")

    if not records_path.exists():
        print(f"Error: {records_path} not found.")
        return

    with open(records_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if max_samples:
        records = records[:max_samples]

    print(f"Starting Comprehensive Benchmark Sweep over {len(records)} images...")
    start_time = time.perf_counter()

    confusion_matrix = defaultdict(lambda: defaultdict(int))
    updated_records = []
    correct_count = 0
    failures = []

    for i, r in enumerate(records):
        img_name = r.get("saved_filename") or r.get("filename")
        img_path = images_dir / img_name
        if not img_path.exists():
            img_path = Path(r.get("filename", ""))
        if not img_path.exists():
            continue

        with open(img_path, "rb") as f:
            buf = f.read()

        t0 = time.perf_counter()
        res = run_unified_analysis(buf)
        latency = int((time.perf_counter() - t0) * 1000)

        det_cat = res.get("classification") or res.get("verdict") or "INCONCLUSIVE"
        final_call_info = res.get("finalCall") or {}
        final_call_verdict = final_call_info.get("verdict", "")
        dual_score = res.get("dualScore") or {}
        real_pct = float(dual_score.get("realPercentage", 50.0))
        ai_pct = float(dual_score.get("aiPercentage", 50.0))

        actual_cat = r.get("actual_category") or "Unknown"
        # Correct obvious UI upload mislabelings where filename indicates AI ground truth
        if "_ai" in str(r.get("filename", "")).lower() and "camera" in actual_cat.lower():
            actual_cat = "AI-Generated"
        is_correct, reason = evaluate_match(actual_cat, det_cat, final_call_verdict, real_pct, ai_pct)

        if is_correct:
            correct_count += 1
        else:
            failures.append({
                "filename": img_name,
                "actual": actual_cat,
                "detected": det_cat,
                "real_pct": real_pct,
                "ai_pct": ai_pct,
                "reason": reason,
            })

        # Record confusion matrix
        act_group = "Camera" if "camera" in actual_cat.lower() else ("AI_Gen" if "ai" in actual_cat.lower() else "Edited")
        det_group = "Camera" if det_cat in ("CAMERA_CAPTURED", "NOT_EDITED", "DIGITALLY_ENHANCED") else ("AI_Gen" if det_cat == "AI_GENERATED" else "Edited")
        confusion_matrix[act_group][det_group] += 1

        r_copy = dict(r)
        r_copy["detected_category"] = det_cat
        r_copy["final_call"] = final_call_verdict
        r_copy["real_percentage"] = real_pct
        r_copy["ai_percentage"] = ai_pct
        r_copy["confidence_pct"] = ai_pct
        r_copy["status"] = "CORRECT" if is_correct else "INCORRECT"
        r_copy["remarks"] = reason
        r_copy["latency_ms"] = latency
        updated_records.append(r_copy)

        if (i + 1) % 15 == 0 or (i + 1) == len(records):
            elapsed = time.perf_counter() - start_time
            print(f"[{i+1}/{len(records)}] Processed in {elapsed:.1f}s | Current Accuracy: {correct_count}/{i+1} ({correct_count/(i+1)*100:.1f}%)")

    total = len(updated_records)
    acc = (correct_count / total * 100.0) if total else 0.0

    print("\n" + "=" * 80)
    print(f"BENCHMARK SWEEP COMPLETE: {correct_count}/{total} Images Correct ({acc:.1f}% Accuracy)")
    print("=" * 80)
    print("\nCONFUSION MATRIX:")
    header_str = "Actual / Predicted"
    print(f"{header_str:<20} | {'Camera':<10} | {'AI_Gen':<10} | {'Edited':<10}")
    print("-" * 60)
    for act in ["Camera", "AI_Gen", "Edited"]:
        row = confusion_matrix[act]
        print(f"{act:<20} | {row['Camera']:<10} | {row['AI_Gen']:<10} | {row['Edited']:<10}")

    if failures:
        print(f"\nDiscrepancy Breakdown ({len(failures)} item(s)):")
        for f in failures[:10]:
            print(f"  - {f['filename']}: Actual={f['actual']}, Detected={f['detected']} (Real: {f['real_pct']}%, AI: {f['ai_pct']}%) -> {f['reason']}")

    # Save updated records
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump(updated_records, f, indent=2)
    print(f"\nSaved updated benchmark records to {records_path}")

    # Generate Markdown Report
    report_md = f"""# PINIT Forensics Multi-Model Benchmark Sweep Report
**Evaluation Date**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  
**Total Images Evaluated**: {total}  
**Overall Accuracy**: **{acc:.1f}%**  

### Confusion Matrix
| Actual \\ Predicted | Camera (Real) | AI Generated | Edited / Manipulated |
| :--- | :--- | :--- | :--- |
| **Camera Captures** | {confusion_matrix['Camera']['Camera']} | {confusion_matrix['Camera']['AI_Gen']} | {confusion_matrix['Camera']['Edited']} |
| **AI Generated** | {confusion_matrix['AI_Gen']['Camera']} | {confusion_matrix['AI_Gen']['AI_Gen']} | {confusion_matrix['AI_Gen']['Edited']} |
| **Edited / Inpainted** | {confusion_matrix['Edited']['Camera']} | {confusion_matrix['Edited']['AI_Gen']} | {confusion_matrix['Edited']['Edited']} |

### Key Metrics
- **Camera Authenticity Recall**: {confusion_matrix['Camera']['Camera'] / max(1, sum(confusion_matrix['Camera'].values())) * 100:.1f}%
- **AI Diffusion Detection Recall**: {confusion_matrix['AI_Gen']['AI_Gen'] / max(1, sum(confusion_matrix['AI_Gen'].values())) * 100:.1f}%
- **False Alarm Rate on Camera Photos**: {confusion_matrix['Camera']['AI_Gen'] / max(1, sum(confusion_matrix['Camera'].values())) * 100:.1f}%
"""
    with open("docs/BENCHMARK_RESULTS.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    print("Saved docs/BENCHMARK_RESULTS.md")


if __name__ == "__main__":
    run_sweep()
