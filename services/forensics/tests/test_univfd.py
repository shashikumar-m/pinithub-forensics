"""
Tests for Universal Fake Detection (UnivFD) detector.
Validates CLIP-ViT feature projection and linear probe integration.
"""
import os
import pytest
from app.detectors.univfd import get_univfd_detector, UnivFDDetector


def test_univfd_detector_interface():
    det = get_univfd_detector()
    assert isinstance(det, UnivFDDetector)
    assert det.name == "univfd"
    assert det.version == "1.0.0"
    assert det.category.value == "AI_GENERATED"


def test_univfd_inference_ai_vs_camera():
    det = get_univfd_detector()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    
    # Authentic Camera Photo
    camera_path = os.path.join(root, "Img_072.jpg")
    if os.path.exists(camera_path):
        with open(camera_path, "rb") as f:
            res_cam = det.run("", image_bytes=f.read())
        assert res_cam.score is not None
        assert res_cam.score <= 0.20
        assert res_cam.details.get("status") == "AUTHENTIC"

    # Synthetic AI Image
    ai_path = os.path.join(root, "image.png")
    if os.path.exists(ai_path):
        with open(ai_path, "rb") as f:
            res_ai = det.run("", image_bytes=f.read())
        assert res_ai.score is not None
        assert res_ai.score >= 0.80
        assert res_ai.details.get("status") == "AI_GENERATED"

