"""
Tests for Diffusion Reconstruction Error (DIRE) detector.
Validates ResNet-18 residual reconstruction evaluation and feature classification.
"""
import os
import pytest
from app.detectors.dire import get_dire_detector, DIREDetector


def test_dire_detector_interface():
    det = get_dire_detector()
    assert isinstance(det, DIREDetector)
    assert det.name == "dire"
    assert det.version == "1.0.0"
    assert det.category.value == "AI_GENERATED"


def test_dire_inference_ai_vs_camera():
    det = get_dire_detector()
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

