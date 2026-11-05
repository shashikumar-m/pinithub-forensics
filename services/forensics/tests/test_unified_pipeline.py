"""
Test unified forensics analysis pipeline.
"""
import io
import pytest
import numpy as np
from PIL import Image
from app.pipelines.unified_analysis import run_unified_analysis


def test_unified_analysis_blind_mode():
    # Textured test image
    arr = np.random.RandomState(42).randint(50, 200, (150, 150, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw = buf.getvalue()

    result = run_unified_analysis(raw)
    assert result["status"] == "DONE"
    assert result["mode"] == "BLIND"
    assert result["verdict"] in ("EDITED", "NOT_EDITED", "INCONCLUSIVE")
    assert 0.0 <= result["probability"] <= 1.0
    assert "summary" in result
    assert "evidence" in result
    assert len(result["evidence"]) >= 7
    assert "artifacts" in result
    assert result["artifacts"]["heatmapUrl"].startswith("data:image/png;base64,")


def test_unified_analysis_reference_mode():
    arr = np.random.RandomState(42).randint(50, 200, (200, 200, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf_ref = io.BytesIO()
    img.save(buf_ref, format="JPEG")
    raw_ref = buf_ref.getvalue()

    cropped = img.crop((20, 20, 180, 180))
    buf_sus = io.BytesIO()
    cropped.save(buf_sus, format="JPEG")
    raw_sus = buf_sus.getvalue()

    result = run_unified_analysis(raw_sus, reference_bytes=raw_ref)
    assert result["status"] == "DONE"
    assert result["mode"] == "REFERENCE"
    assert "crop" in result
    assert result["crop"] is not None
    assert "cropPercentage" in result["crop"]


def test_digitally_enhanced_real_photo_calibration():
    """Verify that a real photo with digital enhancement gets classified as DIGITALLY_ENHANCED with dual scores ~88% Real."""
    import os
    if os.path.exists("Img_070.jpg") and os.path.exists("models/ai_detector_v1.pth"):
        os.environ["AI_WEIGHTS_PATH"] = "models/ai_detector_v1.pth"
        with open("Img_070.jpg", "rb") as f:
            data = f.read()
        res = run_unified_analysis(data)
        assert res["classification"] == "DIGITALLY_ENHANCED"
        assert res["finalCall"]["verdict"] == "REAL_PHOTO_DIGITALLY_ENHANCED"
        assert res["finalCall"]["title"] == "REAL PHOTO (DIGITALLY ENHANCED / FILTERED)"
        assert res["dualScore"]["realPercentage"] == 88.0
        assert res["dualScore"]["aiPercentage"] == 12.0
        assert len(res.get("regions", [])) == 0


