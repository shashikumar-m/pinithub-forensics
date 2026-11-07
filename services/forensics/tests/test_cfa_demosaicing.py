import io
import cv2
import numpy as np
import pytest
from PIL import Image

from app.detectors.cfa_demosaicing import (
    CFADemosaicingDetector,
    get_cfa_demosaicing_detector,
    DETECTOR_NAME,
    DETECTOR_VERSION,
)


def create_simulated_bayer_demosaiced_image(width: int = 128, height: int = 128) -> bytes:
    """
    Creates a synthetic image with authentic Bayer CFA interpolation:
    1. Generates textured RGB image.
    2. Interpolates red on a 2x2 grid to create authentic Bayer variance disparity.
    """
    np.random.seed(42)
    img = np.random.randint(60, 200, (height, width, 3), dtype=np.uint8)
    # Red sampled at (even row, even col), interpolated at other 3 positions
    # Position (0, 1) interpolated from (0, 0) and (0, 2)
    img[0::2, 1:-1:2, 2] = (img[0::2, 0:-2:2, 2].astype(int) + img[0::2, 2::2, 2].astype(int)) // 2
    # Position (1, 0) interpolated from (0, 0) and (2, 0)
    img[1:-1:2, 0::2, 2] = (img[0:-2:2, 0::2, 2].astype(int) + img[2::2, 0::2, 2].astype(int)) // 2

    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def create_synthetic_ai_style_image(width: int = 128, height: int = 128) -> bytes:
    """
    Creates an image synthesized directly in RGB (like Midjourney / SD) without any Bayer CFA lattice.
    """
    np.random.seed(99)
    x = np.linspace(0, 4 * np.pi, width)
    y = np.linspace(0, 4 * np.pi, height)
    xx, yy = np.meshgrid(x, y)
    r = (128 + 60 * np.sin(xx)).astype(np.uint8)
    g = (128 + 60 * np.cos(yy)).astype(np.uint8)
    b = (128 + 60 * np.sin(xx * 0.5 + yy * 0.5)).astype(np.uint8)
    rgb = np.stack([r, g, b], axis=-1)

    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return buf.getvalue()


def test_cfa_detector_contract():
    detector = get_cfa_demosaicing_detector()
    assert detector.name == DETECTOR_NAME
    assert detector.version == DETECTOR_VERSION
    assert detector.category.value == "NOISE_RESIDUAL"


def test_cfa_detector_too_small():
    detector = get_cfa_demosaicing_detector()
    small_img = np.zeros((32, 32, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", small_img)
    res = detector.run("", image_bytes=buf.tobytes())
    assert res.details["status"] == "INCONCLUSIVE"
    assert "too small" in res.details["error"]


def test_cfa_detector_on_bayer_demosaiced_image():
    detector = get_cfa_demosaicing_detector()
    bayer_bytes = create_simulated_bayer_demosaiced_image(width=128, height=128)
    res = detector.run("", image_bytes=bayer_bytes)
    assert res.details["status"] in ("BAYER_CFA_CONFIRMED", "CFA_DISCONTINUITY")
    assert res.details["grid_periodicity_ratio"] >= 1.018
    assert res.score < 0.35  # low tampering score = authentic camera


def test_cfa_detector_on_synthetic_ai_style_image():
    detector = get_cfa_demosaicing_detector()
    ai_bytes = create_synthetic_ai_style_image(width=128, height=128)
    res = detector.run("", image_bytes=ai_bytes)
    assert res.details["status"] in ("NO_CFA_PATTERN", "INCONCLUSIVE")
    assert res.details["grid_periodicity_ratio"] <= 1.025
    assert res.score >= 0.50  # higher suspicion score
