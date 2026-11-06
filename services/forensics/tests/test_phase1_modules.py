"""
Unit tests for Phase 1 enhancements:
1. Universal Input Format Normalizer (app.io.format_normalizer)
2. JPEG Quantization Table (DQT) Fingerprint Detector (app.detectors.dqt_fingerprint)
3. Modality Pre-Router (app.detectors.modality_router)
"""

import io
import numpy as np
import pytest
from PIL import Image

from app.io.format_normalizer import (
    normalize_image_bytes,
    is_supported_format,
    NormalizedResult,
)
from app.detectors.dqt_fingerprint import (
    extract_dqt_tables,
    generate_standard_ijg_table,
    match_dqt_fingerprint,
    get_dqt_fingerprint_detector,
    DQTFingerprintDetector,
)
from app.detectors.modality_router import (
    classify_modality,
    ImageModality,
    get_modality_router,
    ModalityRouter,
)


# =========================================================================
# 1. Format Normalizer Tests
# =========================================================================

def test_format_normalizer_supported_formats():
    """Verify format detection via magic bytes."""
    # JPEG magic bytes
    jpeg_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF"
    supported, fmt = is_supported_format(jpeg_bytes)
    assert supported is True
    assert fmt == "JPEG"

    # PNG magic bytes
    png_bytes = b"\x89PNG\r\n\x1a\n"
    supported, fmt = is_supported_format(png_bytes)
    assert supported is True
    assert fmt == "PNG"

    # Unsupported format
    supported, fmt = is_supported_format(b"UNKNOWN_BINARY_DATA")
    assert supported is False
    assert fmt == "UNKNOWN"


def test_format_normalizer_rgb_jpeg():
    """Verify normalizer handles clean RGB JPEG."""
    img = Image.new("RGB", (200, 150), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = buf.getvalue()

    res = normalize_image_bytes(data)
    assert res.error is None
    assert res.original_width == 200
    assert res.original_height == 150
    assert res.normalized_width == 200
    assert res.normalized_height == 150
    assert len(res.image_bytes) > 0


def test_format_normalizer_rgba_png_conversion():
    """Verify normalizer composites RGBA transparent PNG to solid RGB."""
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    res = normalize_image_bytes(data)
    assert res.error is None
    assert res.original_mode == "RGBA"
    assert res.was_converted is True
    # Verify resulting image opens cleanly as RGB
    out_img = Image.open(io.BytesIO(res.image_bytes))
    assert out_img.mode == "RGB"


def test_format_normalizer_too_small_rejected():
    """Verify normalizer rejects images under minimum dimension floor (64x64)."""
    img = Image.new("RGB", (32, 32), color=(50, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    res = normalize_image_bytes(data)
    assert res.error is not None
    assert "too small" in res.error.lower() or "minimum" in res.error.lower()


# =========================================================================
# 2. DQT Fingerprint Detector Tests
# =========================================================================

def test_ijg_table_generation():
    """Verify standard IJG luminance table generation scales properly with quality."""
    table_50 = generate_standard_ijg_table(50)
    assert len(table_50) == 64
    assert table_50[0] == 16  # baseline value

    table_100 = generate_standard_ijg_table(100)
    assert len(table_100) == 64
    assert all(val == 1 for val in table_100)  # maximum quality = all 1s

    with pytest.raises(ValueError):
        generate_standard_ijg_table(0)


def test_dqt_match_on_synthetic_jpeg():
    """Verify DQT matching identifies Python PIL/libjpeg encoding."""
    img = Image.new("RGB", (128, 128), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = buf.getvalue()

    match = match_dqt_fingerprint(data)
    assert match.is_jpeg is True
    assert match.quality_estimate is not None
    assert 85 <= match.quality_estimate <= 95
    assert "PIL" in match.match_name or match.match_category in ("AI_TOOL", "GENERIC")


def test_dqt_detector_class_contract():
    """Verify DQTFingerprintDetector satisfies BaseDetector interface."""
    det = get_dqt_fingerprint_detector()
    assert isinstance(det, DQTFingerprintDetector)
    assert det.name == "dqt_fingerprint"

    # Run on non-JPEG bytes
    png_img = Image.new("RGB", (100, 100))
    p_buf = io.BytesIO()
    png_img.save(p_buf, format="PNG")
    res = det.run("", image_bytes=p_buf.getvalue())
    assert res.detector == "dqt_fingerprint"
    assert res.details.get("is_jpeg") is False


# =========================================================================
# 3. Modality Router Tests
# =========================================================================

def test_modality_router_screenshot_detection():
    """Verify pure digital UI / flat color graphics are identified as SCREENSHOT/DIGITAL_GRAPHIC."""
    # Flat color graphic with discrete blocks
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:128, :] = [255, 255, 255]
    arr[128:, :] = [240, 240, 240]
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    res = classify_modality(data)
    assert res.modality in (ImageModality.SCREENSHOT, ImageModality.DIGITAL_GRAPHIC)
    assert res.confidence >= 0.70


def test_modality_router_document_detection():
    """Verify document with white paper ratio and text is classified as DOCUMENT."""
    # White background (85%) with dark horizontal text bars (10%)
    arr = np.ones((300, 200, 3), dtype=np.uint8) * 245
    for y in range(40, 260, 20):
        arr[y:y+4, 30:170] = 20  # dark text lines
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = buf.getvalue()

    res = classify_modality(data)
    assert res.modality == ImageModality.DOCUMENT
    assert res.confidence >= 0.80


def test_modality_router_class_contract():
    """Verify ModalityRouter satisfies BaseDetector interface."""
    router = get_modality_router()
    assert isinstance(router, ModalityRouter)
    assert router.name == "modality_router"
