#!/usr/bin/env python3
"""
PINITHUB Forensics — Command Line Forensic Detection Tool.
Inspects an image and determines whether it is:
  - AI_GENERATED (full synthetic image)
  - AI_EDITED (localized inpainting / generative fill)
  - CAMERA_CAPTURED (genuine physical camera photograph)
  - INCONCLUSIVE (conflicting / insufficient evidence)

Usage:
  services/forensics/.venv/Scripts/python pinithub_detect.py <image_path> [--reference <ref_path>] [--json]
"""
import argparse
import json
import os
import sys
import time

# Auto-configure environment and paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FORENSICS_DIR = os.path.join(BASE_DIR, "services", "forensics")
sys.path.insert(0, FORENSICS_DIR)

# Set AI weights path if available
default_weights = os.path.join(BASE_DIR, "models", "ai_detector_v1.pth")
if os.path.isfile(default_weights) and not os.environ.get("AI_WEIGHTS_PATH"):
    os.environ["AI_WEIGHTS_PATH"] = default_weights

from app.pipelines.unified_analysis import run_unified_analysis

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GRAY = "\033[90m"
MAGENTA = "\033[35m"


def format_classification(cls: str) -> str:
    if cls == "AI_GENERATED":
        return f"{RED}{BOLD}[AI_GENERATED]{RESET} {RED}(Full Synthetic AI Synthesis){RESET}"
    elif cls == "AI_EDITED":
        return f"{YELLOW}{BOLD}[AI_EDITED]{RESET} {YELLOW}(Localized AI Inpainting / Modification){RESET}"
    elif cls == "CAMERA_CAPTURED":
        return f"{GREEN}{BOLD}[CAMERA_CAPTURED]{RESET} {GREEN}(Authentic Physical Camera Optics){RESET}"
    else:
        return f"{CYAN}{BOLD}[INCONCLUSIVE]{RESET} {GRAY}(Conflicting / Insufficient Evidence){RESET}"


def main():
    parser = argparse.ArgumentParser(
        description="PINITHUB Forensics — CLI AI & Tampering Detection Engine"
    )
    parser.add_argument("image", help="Path to suspect image (JPEG, PNG, WebP)")
    parser.add_argument("--reference", "-r", help="Optional reference original image", default=None)
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of terminal report")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"{RED}Error: File not found: {args.image}{RESET}", file=sys.stderr)
        sys.exit(1)

    with open(args.image, "rb") as f:
        suspect_bytes = f.read()

    reference_bytes = None
    if args.reference:
        if not os.path.exists(args.reference):
            print(f"{RED}Error: Reference file not found: {args.reference}{RESET}", file=sys.stderr)
            sys.exit(1)
        with open(args.reference, "rb") as f:
            reference_bytes = f.read()

    print(f"{GRAY}Running PINITHUB Forensic Engine on {os.path.basename(args.image)}...{RESET}")
    t0 = time.perf_counter()
    result = run_unified_analysis(suspect_bytes, reference_bytes=reference_bytes)
    elapsed = time.perf_counter() - t0

    if args.json:
        # Strip large binary data URLs for clean JSON output
        clean_res = {k: v for k, v in result.items() if k not in ("heatmap", "mask")}
        print(json.dumps(clean_res, indent=2))
        return

    cls = result.get("classification") or result.get("verdict")
    prob = result.get("probability", 0.5)
    summary = result.get("summary", "")
    dims = result.get("dimensions", {})
    regions = result.get("regions", [])
    affected_pct = result.get("affectedAreaPercentage", 0.0)
    ai_det = result.get("aiDetection", {})
    ai_score = ai_det.get("score", 0.0)
    crop = result.get("crop")

    print("\n" + "=" * 70)
    print(f"{BOLD}PINITHUB FORENSICS — IMAGE AUTHENTICITY ANALYSIS REPORT{RESET}")
    print("=" * 70)
    print(f"File:         {BOLD}{os.path.basename(args.image)}{RESET} ({len(suspect_bytes) / 1024:.1f} KB)")
    print(f"Dimensions:   {dims.get('width', '?')} × {dims.get('height', '?')} px")
    print(f"Analysis:     {result.get('mode', 'BLIND')} mode in {elapsed:.2f}s")
    print("-" * 70)

    print(f"CLASSIFICATION:       {format_classification(cls)}")
    print(f"Calibrated Confidence: {BOLD}{prob * 100:.1f}%{RESET}")
    print(f"AI Trace Score:        {BOLD}{ai_score * 100:.1f}%{RESET} ({ai_det.get('status', 'N/A')})")
    if affected_pct > 0:
        print(f"Manipulated Area:      {BOLD}{affected_pct:.2f}%{RESET} (Exact Boolean Mask Union)")
    print("-" * 70)

    print(f"{BOLD}EXECUTIVE SUMMARY:{RESET}")
    print(f"  {summary}")

    if crop and crop.get("status") == "DETECTED":
        print("-" * 70)
        print(f"{BOLD}CROP ANALYSIS:{RESET}")
        print(f"  Cropped area: {crop.get('cropPercentage', 0.0):.1f}% removed from original.")
        print(f"  Kept area:    {crop.get('keptPercentage', 100.0):.1f}%")

    if regions:
        print("-" * 70)
        print(f"{BOLD}LOCALIZED TAMPERED REGIONS ({len(regions)} detected):{RESET}")
        print(f"  {'ID':<5} {'Type':<18} {'Area %':<10} {'Conf %':<10} {'Bounding Box (x, y, w, h)'}")
        print(f"  {'-'*5} {'-'*18} {'-'*10} {'-'*10} {'-'*30}")
        for r in regions:
            bb = r.get("bbox", {})
            bb_str = f"[{bb.get('x',0)}, {bb.get('y',0)}, {bb.get('w',0)}, {bb.get('h',0)}]"
            print(f"  {r.get('id', ''):<5} {r.get('editTypeGuess', ''):<18} {r.get('areaPct', 0.0):<10.2f} {r.get('confidence', 0.0)*100:<10.1f} {bb_str}")

    print("-" * 70)
    print(f"{BOLD}KEY DETECTOR SIGNALS:{RESET}")
    for ev in result.get("evidence", []):
        tag = ev.get("tag", "PROVEN")
        tag_color = GREEN if "PROVEN" in tag else (YELLOW if "LIMITED" in tag else MAGENTA)
        score_val = f"{ev.get('score'):.3f}" if ev.get("score") is not None else "N/A"
        notes = ev.get("notes", [])
        note_str = notes[0] if notes else ""
        print(f"  * {BOLD}{ev.get('detector', ''):<22}{RESET} [{tag_color}{tag:<12}{RESET}] Score: {score_val:<6} | {GRAY}{note_str}{RESET}")

    warnings = result.get("warnings", [])
    if warnings:
        print("-" * 70)
        print(f"{YELLOW}{BOLD}WARNINGS & LIMITATIONS:{RESET}")
        for w in warnings:
            print(f"  [!] {w}")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
