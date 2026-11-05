"""
Phase 8 — Reproducible Demo Scenario for PinITHUB internship presentation.

Demonstrates all 15 steps:
  1. Protect original image (synthetic)
  2. Display SHA-256 and metadata
  3. Create a travelled copy
  4. Apply crop + compression
  5. Apply a small visual change (sticker simulation for AI edit placeholder)
  6–10. Run full investigation pipeline
  11–15. Generate report, seal, display result

All values come from actual execution — no mocked forensic values.

Usage:
    python -m app.utils.demo_scenario
"""
from __future__ import annotations

import hashlib
import io
import json
import time

import numpy as np
import cv2
from PIL import Image as PILImage

from app.travel.generator import generate_travelled_copy, TransformStep
from app.travel.travel_analyzer import analyze_travelled_copy
from app.fusion.normalizer import normalize_all
from app.fusion.verdict_engine import fuse
from app.fusion.region_fusion import fuse_regions
from app.fusion.report_generator import (
    build_canonical_report, canonical_json, seal_report, generate_text_report
)


def run_demo() -> None:
    print("=" * 60)
    print("PINITHUB FORENSICS — Demo Scenario")
    print("=" * 60)

    # Step 1: Create / "protect" a synthetic original image
    print("\n[1] Creating synthetic original image...")
    rng = np.random.RandomState(42)
    arr = rng.randint(0, 255, (256, 256, 3), dtype=np.uint8).astype(np.float32)
    for i in range(0, 256, 16): arr[i:i+4, :, 0] = 200
    for j in range(0, 256, 24): arr[:, j:j+3, 1] = 180
    for _ in range(15):
        cx, cy = rng.randint(20, 236), rng.randint(20, 236)
        cv2.circle(arr, (cx, cy), int(rng.randint(5, 20)),
                   (int(rng.randint(0, 255)),)*3, -1)
    img = PILImage.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=92); original_bytes = buf.getvalue()

    # Step 2: Display SHA-256 and basic info
    sha256_original = hashlib.sha256(original_bytes).hexdigest()
    print(f"   SHA-256: {sha256_original[:32]}...")
    print(f"   Size:    {len(original_bytes)} bytes")
    print(f"   Dims:    256x256 px")

    # Step 3–5: Create a travelled copy with crop + compression + sticker
    print("\n[2] Creating travelled copy (crop 20% + JPEG q=75 + sticker)...")
    steps = [
        TransformStep("CROP", {"crop_fraction": 0.20, "direction": "center"}),
        TransformStep("JPEG_RECOMPRESSION", {"quality": 75}),
        TransformStep("STICKER_ADDED", {"x": 40, "y": 40, "size": 30,
                                          "color": [255, 200, 0]}),
    ]
    suspect_bytes, manifest = generate_travelled_copy(original_bytes, steps, "COMBINED")
    sha256_suspect = manifest.output_sha256
    print(f"   Applied: {[s.type for s in steps]}")
    print(f"   SHA-256: {sha256_suspect[:32]}...")
    print(f"   Size:    {len(suspect_bytes)} bytes")

    # Step 6–7: Register + travel analysis
    print("\n[3] Running registration and travel analysis...")
    t0 = time.perf_counter()
    travel_result = analyze_travelled_copy(original_bytes, suspect_bytes)
    t_travel = int((time.perf_counter() - t0) * 1000)
    print(f"   Travel status: {travel_result.status}")
    print(f"   Transformations detected: {travel_result.transformations}")
    print(f"   Registration: {(travel_result.registration_quality or {}).get('status')}")
    print(f"   Time: {t_travel}ms")

    # Step 8: Evidence fusion
    print("\n[4] Fusing evidence...")
    all_results = {
        "registration": travel_result.registration_quality,
        "crop": travel_result.crop,
        "ai": travel_result.ai_detection,
        "travel": travel_result.to_dict(),
    }
    evidence_items = normalize_all(all_results)
    reg_status = (travel_result.registration_quality or {}).get("status")
    assessment = fuse(evidence_items, registration_status=reg_status)
    print(f"   Verdict:          {assessment.verdict}")
    print(f"   Evidence strength: {assessment.evidence_strength}")
    print(f"   Confidence:       {assessment.confidence_status}")
    print(f"   Fusion version:   {assessment.fusion_version}")

    # Step 9: Regions
    regions = fuse_regions(
        travel_result.crop, travel_result.ai_detection,
        [c.to_dict() if hasattr(c, "to_dict") else c for c in (travel_result.changes or [])],
        None, 256, 256,
    )
    print(f"\n[5] Fused regions: {len(regions)}")
    for r in regions:
        print(f"   [{r.type}] area={r.area_percentage:.2f}% bbox=({r.bbox_x},{r.bbox_y},{r.bbox_width}x{r.bbox_height})")

    # Step 10: Crop summary
    crop_info = travel_result.crop
    if crop_info and crop_info.get("status") == "DETECTED":
        print(f"\n[6] Crop: {crop_info.get('crop_percentage', 0):.2f}% removed from original")

    # Steps 11–12: Generate report
    print("\n[7] Generating canonical JSON report...")
    meta_changes = [m.to_dict() if hasattr(m, "to_dict") else m
                    for m in (travel_result.metadata_changes or [])]
    report = build_canonical_report(
        investigation_id="demo-investigation-001",
        verdict=assessment.verdict,
        confidence_status=assessment.confidence_status,
        evidence_strength=assessment.evidence_strength,
        explanation=assessment.explanation,
        warnings=assessment.warnings,
        fusion_version=assessment.fusion_version,
        reference_image={"sha256": sha256_original, "originalFilename": "original.jpg",
                          "width": 256, "height": 256, "format": "jpeg"},
        suspect_image={"sha256": sha256_suspect, "originalFilename": "travelled_copy.jpg",
                        "format": "jpeg"},
        registration=travel_result.registration_quality,
        metadata_changes=meta_changes,
        transformations=travel_result.transformations,
        evidence_items=evidence_items,
        regions=regions,
        crop=crop_info,
        ai_detection=travel_result.ai_detection,
        limitations=["AI detection requires trained model weights",
                      "Fusion weights are heuristic (UNCALIBRATED)"],
    )
    report_json_str = canonical_json(report)
    print(f"   Report size: {len(report_json_str)} bytes")
    print(f"   Verdict in report: {report.get('verdict')}")

    # Steps 13–14: Seal
    print("\n[8] Sealing report (tamper-evident SHA-256)...")
    seal = seal_report(report_json_str)
    print(f"   Sealed hash: {seal['reportHash']}")
    print(f"   Sealed at:   {seal['sealedAt']}")
    print(f"   Algorithm:   {seal['algorithm']}")
    print(f"   Note: {seal['note'][:60]}...")

    # Step 15: Summary
    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print(f"  Verdict:          {assessment.verdict}")
    print(f"  Evidence strength: {assessment.evidence_strength}")
    print(f"  Report hash:      {seal['reportHash'][:32]}...")
    print("=" * 60)
    print("\nAll values above came from actual execution — no mocked results.")


if __name__ == "__main__":
    run_demo()
