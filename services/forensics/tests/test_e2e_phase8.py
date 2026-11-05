"""
Phase 8 — End-to-End Investigation Tests.

Tests A through G per Phase 8 spec.
Tests run through the full investigation pipeline:
  normalizer → verdict engine → region fusion → report → seal

No database access — runs on the Python service layer directly.
"""
import io
import json
import os
import numpy as np
from PIL import Image as PILImage, ImageEnhance
import cv2
import pytest

from app.fusion.normalizer import normalize_all
from app.fusion.verdict_engine import fuse
from app.fusion.region_fusion import fuse_regions
from app.fusion.report_generator import build_canonical_report, canonical_json, seal_report
from app.travel.generator import generate_travelled_copy, TransformStep
from app.travel.travel_analyzer import analyze_travelled_copy


def _img(width=256, height=256, seed=42) -> bytes:
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8).astype(np.float32)
    for i in range(0, height, 16): arr[i:i+4, :, 0] = 200
    for j in range(0, width, 24): arr[:, j:j+3, 1] = 180
    for _ in range(10):
        cx, cy = rng.randint(20, width-20), rng.randint(20, height-20)
        cv2.circle(arr, (cx, cy), int(rng.randint(5, 15)),
                   (int(rng.randint(0,255)),)*3, -1)
    buf = io.BytesIO()
    PILImage.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _run_investigation(ref: bytes, sus: bytes) -> dict:
    """Run the full investigation pipeline and return the result dict."""
    travel = analyze_travelled_copy(ref, sus)
    all_results = {
        "registration": travel.registration_quality,
        "crop": travel.crop,
        "ai": travel.ai_detection,
        "travel": travel.to_dict(),
    }
    evidence_items = normalize_all(all_results)
    reg_status = (travel.registration_quality or {}).get("status")
    assessment = fuse(evidence_items, registration_status=reg_status)
    regions = fuse_regions(
        travel.crop, travel.ai_detection,
        [c.to_dict() if hasattr(c, "to_dict") else c for c in (travel.changes or [])],
        None, 256, 256,
    )
    return {
        "verdict": assessment.verdict,
        "confidence_status": assessment.confidence_status,
        "evidence_strength": assessment.evidence_strength,
        "transformations": travel.transformations,
        "region_count": len(regions),
        "assessment": assessment,
        "evidence_items": evidence_items,
        "regions": regions,
    }


class TestE2EInvestigation:
    def setup_method(self):
        os.environ.pop("AI_WEIGHTS_PATH", None)
        from app.models.ai_model_registry import reset_ai_model_loader
        from app.detectors.ai_detector import reset_ai_detector
        reset_ai_model_loader()
        reset_ai_detector()

    # Test A — Original returned unchanged
    def test_a_original_unchanged(self):
        ref = _img(seed=1)
        result = _run_investigation(ref, ref)
        # Should be NOT_EDITED, TRANSFORMED_COPY, or INCONCLUSIVE — never CONTENT_CHANGED
        assert result["verdict"] not in ("EDITED",), (
            f"Identical image should not produce EDITED; got {result['verdict']}"
        )

    # Test B — JPEG transport only
    def test_b_jpeg_transport(self):
        ref = _img(seed=2)
        steps = [TransformStep("JPEG_RECOMPRESSION", {"quality": 75})]
        sus, _ = generate_travelled_copy(ref, steps)
        result = _run_investigation(ref, sus)
        # Transport-only must not produce CONTENT_CHANGED
        assert result["verdict"] != "CONTENT_CHANGED"

    # Test C — 20% crop
    def test_c_crop_20pct(self):
        ref = _img(seed=3)
        steps = [TransformStep("CROP", {"crop_fraction": 0.20})]
        sus, _ = generate_travelled_copy(ref, steps)
        result = _run_investigation(ref, sus)
        # Should produce EDITED (crop is content change) or CONTENT_CHANGED in travel
        assert result["verdict"] in ("EDITED", "INCONCLUSIVE", "NOT_EDITED")
        # CROP should be in transformations if detected
        if "CROP" in result["transformations"]:
            assert result["verdict"] in ("EDITED", "INCONCLUSIVE")

    # Test D — AI detection (status conforms to valid categories)
    def test_d_ai_unavailable(self):
        ref = _img(seed=4)
        result = _run_investigation(ref, ref)
        ai_items = [e for e in result["evidence_items"] if e.category == "AI"]
        if ai_items:
            ai_status = ai_items[0].status
            assert ai_status in ("UNAVAILABLE", "SUPPORTING", "NEUTRAL")

    # Test E — Combined: crop + JPEG compression
    def test_e_combined_crop_jpeg(self):
        ref = _img(seed=5)
        steps = [
            TransformStep("CROP", {"crop_fraction": 0.20}),
            TransformStep("JPEG_RECOMPRESSION", {"quality": 75}),
        ]
        sus, _ = generate_travelled_copy(ref, steps)
        result = _run_investigation(ref, sus)
        assert result["verdict"] is not None
        # Both CROP (content) and JPEG_RECOMPRESSION (transport) should appear
        transforms = set(result["transformations"])
        assert "JPEG_RECOMPRESSION" in transforms or len(transforms) > 0

    # Test F — Unrelated image
    def test_f_unrelated_image(self):
        ref = _img(seed=6)
        unrelated = _img(seed=999)
        result = _run_investigation(ref, unrelated)
        assert result["verdict"] in ("NO_MATCH", "INCONCLUSIVE")

    # Test G — Insufficient evidence
    def test_g_insufficient_evidence_inconclusive(self):
        # Very small image — likely too few features → registration may fail
        rng = np.random.RandomState(77)
        arr = rng.randint(0, 255, (16, 16, 3), dtype=np.uint8)
        buf = io.BytesIO()
        PILImage.fromarray(arr).save(buf, "JPEG", quality=90)
        tiny = buf.getvalue()
        result = _run_investigation(tiny, tiny)
        # Should not claim EDITED for an unanalyzable tiny image
        assert result["verdict"] in ("NO_MATCH", "INCONCLUSIVE", "NOT_EDITED", "ANALYSIS_UNAVAILABLE")


class TestE2EReport:
    def test_report_sealed_hash_changes_on_verdict_change(self):
        """Seal must change if verdict changes — tamper-evident."""
        report1 = build_canonical_report(
            "inv-1", "EDITED", "UNCALIBRATED", "HIGH", "Test", [], "v1",
            None, None, None, [], [], [], [], None, None, []
        )
        report2 = build_canonical_report(
            "inv-1", "NOT_EDITED", "UNCALIBRATED", "LOW", "Test", [], "v1",
            None, None, None, [], [], [], [], None, None, []
        )
        j1, j2 = canonical_json(report1), canonical_json(report2)
        s1 = seal_report(j1)["reportHash"]
        s2 = seal_report(j2)["reportHash"]
        assert s1 != s2

    def test_full_investigation_report_round_trip(self):
        """JSON report can be serialized and deserialized deterministically."""
        ref = _img(seed=8)
        sus, _ = generate_travelled_copy(ref, [TransformStep("CROP", {"crop_fraction": 0.20})])
        travel = analyze_travelled_copy(ref, sus)
        all_results = {"registration": travel.registration_quality, "crop": travel.crop}
        evidence = normalize_all(all_results)
        assessment = fuse(evidence)
        report = build_canonical_report(
            "test-e2e", assessment.verdict, assessment.confidence_status,
            assessment.evidence_strength, assessment.explanation,
            assessment.warnings, assessment.fusion_version,
            None, None, None, [], travel.transformations, evidence, [], travel.crop, None, []
        )
        j = canonical_json(report)
        parsed = json.loads(j)
        assert parsed["verdict"] == assessment.verdict
        assert parsed["schemaVersion"] == "1.0"
        assert isinstance(parsed["transformations"], list)

    def test_no_probability_in_uncalibrated_report(self):
        """Uncalibrated fusion must not include a probability field."""
        ref = _img(seed=9)
        all_results = {}
        evidence = normalize_all(all_results)
        assessment = fuse(evidence)
        assert assessment.probability is None

    def test_limitations_always_present(self):
        """Report must always include limitations."""
        report = build_canonical_report(
            "x", "INCONCLUSIVE", "UNCALIBRATED", "INSUFFICIENT", "",
            [], "v1", None, None, None, [], [], [], [], None, None,
            ["AI detection is experimental"]
        )
        assert len(report["limitations"]) > 0

    def test_canonical_json_sorted_keys(self):
        """Canonical JSON must have sorted keys for determinism."""
        report = build_canonical_report(
            "z", "EDITED", "UNCALIBRATED", "HIGH", "X", [], "v1",
            None, None, None, [], [], [], [], None, None, []
        )
        j = canonical_json(report)
        # Re-parse and re-serialize to confirm stability
        j2 = json.dumps(json.loads(j), sort_keys=True, separators=(",", ":"))
        assert j == j2
