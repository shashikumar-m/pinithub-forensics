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

