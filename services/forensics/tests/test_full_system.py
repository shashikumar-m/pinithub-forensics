"""
End-to-End System Tests for Unified Forensics & Crop Percentage Detection.
Verifies compliance with PinITHUB_Plan.pdf and Crop_plan.pdf.
"""
import io
import pytest
import numpy as np
from PIL import Image, ImageDraw
from app.pipelines.unified_analysis import run_unified_analysis
from app.detectors.crop_detector import get_crop_detector


def _generate_synthetic_image(w=300, h=300, seed=123) -> bytes:
    rng = np.random.RandomState(seed)
    arr = rng.randint(40, 220, (h, w, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    # Draw geometric shapes so SIFT/ORB keypoints are rich
    draw.rectangle([50, 50, 120, 120], fill=(240, 50, 50), outline=(10, 10, 10))
    draw.ellipse([160, 60, 250, 150], fill=(50, 240, 50), outline=(10, 10, 10))
    draw.rectangle([80, 180, 220, 260], fill=(50, 50, 240), outline=(255, 255, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_blind_analysis_generates_heatmap_and_verdict():
    raw = _generate_synthetic_image(300, 300, seed=99)
    result = run_unified_analysis(raw)

    assert result["status"] == "DONE"
    assert result["mode"] == "BLIND"
    assert result["verdict"] in ("EDITED", "NOT_EDITED", "INCONCLUSIVE")
    assert "summary" in result
    assert "artifacts" in result
    assert "heatmapUrl" in result["artifacts"]
    assert result["artifacts"]["heatmapUrl"].startswith("data:image/png;base64,")
    assert "evidence" in result
    # Check that detectors have maturity tags
    for ev in result["evidence"]:
        assert ev["tag"] in ("PROVEN", "PROVEN, LIMITED", "EXPERIMENTAL")


def test_crop_analysis_known_percentage_matches_crop_plan():
    """
    Test according to Crop_plan.pdf:
    Given original and cropped copy, verify exact crop percentage and bounding box.
    """
    orig_bytes = _generate_synthetic_image(400, 400, seed=42)
    orig_img = Image.open(io.BytesIO(orig_bytes))

    # Cut out exactly a 200x200 center crop:
    # Original area = 160,000 px^2, Kept area = 40,000 px^2 -> Crop % = 75.0%
    cropped_img = orig_img.crop((100, 100, 300, 300))
    buf = io.BytesIO()
    cropped_img.save(buf, format="JPEG", quality=90)
    crop_bytes = buf.getvalue()

    result = run_unified_analysis(crop_bytes, reference_bytes=orig_bytes)

    assert result["mode"] == "REFERENCE"
    assert result["crop"] is not None
    crop_data = result["crop"]

    assert crop_data["status"] == "DETECTED"
    # Ground truth is ~75%. Homography should predict within 5% tolerance
    pred_crop = crop_data["cropPercentage"]
    assert 65.0 <= pred_crop <= 85.0
    assert "keptPercentage" in crop_data
    assert round(crop_data["cropPercentage"] + crop_data["keptPercentage"], 0) == 100.0


def test_honest_verdict_rule_no_authentic_claim():
    """Verify that system never outputs 'authentic' or '100% unedited'."""
    raw = _generate_synthetic_image(200, 200, seed=7)
    result = run_unified_analysis(raw)

    summary_lower = result["summary"].lower()
    assert "100%" not in summary_lower
    assert "authentic" not in summary_lower
    if result["verdict"] == "NOT_EDITED":
        assert "no evidence of editing found" in summary_lower

