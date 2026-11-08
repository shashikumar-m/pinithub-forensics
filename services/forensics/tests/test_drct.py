"""
Tests for Diffusion Reconstruction Contrastive Training (DRCT) detector.
Validates ConvNeXt feature extraction and contrastive projection head integration.
"""
import os
import pytest
from app.detectors.drct import get_drct_detector, DRCTDetector


def test_drct_detector_interface():
    det = get_drct_detector()
    assert isinstance(det, DRCTDetector)
    assert det.name == "drct"
    assert det.version == "1.0.0"
    assert det.category.value == "AI_GENERATED"


def test_drct_inference_ai_vs_camera():
    det = get_drct_detector()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    # Authentic Camera Photo
    camera_path = os.path.join(root, "Img_072.jpg")
    if os.path.exists(camera_path):
        with open(camera_path, "rb") as f:
            res_cam = det.run("", image_bytes=f.read())
        assert res_cam.score is not None
        assert res_cam.score < 0.50
        assert res_cam.details.get("status") in ("NATURAL_SENSOR_CONSISTENT", "INCONCLUSIVE")

    # Synthetic AI Image
    ai_path = os.path.join(root, "Img_027.jpg")
    if os.path.exists(ai_path):
        with open(ai_path, "rb") as f:
            res_ai = det.run("", image_bytes=f.read())
        assert res_ai.score is not None
        assert res_ai.score > 0.50
        assert res_ai.details.get("status") in ("AI_DIFFUSION_DETECTED", "INCONCLUSIVE")

