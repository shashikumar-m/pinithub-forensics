"""
Unit tests for Phase 2 forensic modules:
1. Lateral Chromatic Aberration (LCA) Detector (chromatic_aberration.py)
2. C2PA / Content Credentials Provenance Parser (c2pa_parser.py)
3. EXIF Embedded Thumbnail Discrepancy Detector (thumbnail_discrepancy.py)
4. Corneal Specular Reflection & Iris Consistency Detector (corneal_reflection.py)
"""

import io
import struct
import numpy as np
import pytest
from PIL import Image

from app.detectors.chromatic_aberration import (
    analyze_chromatic_aberration,
    get_chromatic_aberration_detector,
    ChromaticAberrationDetector,
)
from app.detectors.c2pa_parser import (
    parse_c2pa_manifest,
    get_c2pa_parser_detector,
    C2PAParserDetector,
)
from app.detectors.thumbnail_discrepancy import (
    extract_and_compare_thumbnail,
    get_thumbnail_discrepancy_detector,
    ThumbnailDiscrepancyDetector,
)
from app.detectors.corneal_reflection import (
    analyze_corneal_reflections,
    get_corneal_reflection_detector,
    CornealReflectionDetector,
)


# =========================================================================
# 1. Chromatic Aberration Tests
# =========================================================================

def test_chromatic_aberration_detector_contract():
    """Verify LCA detector satisfies BaseDetector interface."""
    det = get_chromatic_aberration_detector()
    assert isinstance(det, ChromaticAberrationDetector)
    assert det.name == "chromatic_aberration"
    assert det.version == "1.0.0"


def test_chromatic_aberration_low_res():
    """Verify graceful INCONCLUSIVE handling on low-resolution inputs."""
    rgb = np.zeros((64, 64, 3), dtype=np.uint8)
    res = analyze_chromatic_aberration(rgb)
    assert res.status == "INCONCLUSIVE"
    assert "too low" in res.evidence[0].lower()


def test_chromatic_aberration_flat_image():
    """Verify flat images with no contrast edges return INCONCLUSIVE."""
    rgb = np.ones((256, 256, 3), dtype=np.uint8) * 128
    res = analyze_chromatic_aberration(rgb)
    assert res.status == "INCONCLUSIVE"


# =========================================================================
# 2. C2PA Provenance Parser Tests
# =========================================================================

def test_c2pa_detector_contract():
    """Verify C2PA parser satisfies BaseDetector interface."""
    det = get_c2pa_parser_detector()
    assert isinstance(det, C2PAParserDetector)
    assert det.name == "c2pa_parser"


def test_c2pa_parser_no_manifest():
    """Verify images without C2PA manifests return NO_C2PA_MANIFEST."""
    img = Image.new("RGB", (100, 100), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    res = parse_c2pa_manifest(buf.getvalue())
    assert res.has_manifest is False
    assert res.status == "NO_C2PA_MANIFEST"


def test_c2pa_parser_ai_provenance():
    """Verify XMP-embedded trainedAlgorithmicMedia tag confirms AI generation."""
    xmp_snippet = b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description c2pa:action="c2pa.created" digitalSourceType="trainedAlgorithmicMedia"/></rdf:RDF></x:xmpmeta>'
    res = parse_c2pa_manifest(xmp_snippet)
    assert res.has_manifest is True
    assert res.is_ai_generated is True
    assert res.status == "CRYPTOGRAPHIC_AI_CONFIRMED"


# =========================================================================
# 3. Thumbnail Discrepancy Tests
# =========================================================================

def test_thumbnail_discrepancy_contract():
    """Verify Thumbnail discrepancy detector satisfies BaseDetector interface."""
    det = get_thumbnail_discrepancy_detector()
    assert isinstance(det, ThumbnailDiscrepancyDetector)
    assert det.name == "thumbnail_discrepancy"


def test_thumbnail_discrepancy_no_thumbnail():
    """Verify images without embedded thumbnails return NO_THUMBNAIL_EMBEDDED."""
    img = Image.new("RGB", (100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    res = extract_and_compare_thumbnail(buf.getvalue())
    assert res.has_thumbnail is False
    assert res.status == "NO_THUMBNAIL_EMBEDDED"


# =========================================================================
# 4. Corneal Reflection Tests
# =========================================================================

def test_corneal_reflection_contract():
    """Verify Corneal reflection detector satisfies BaseDetector interface."""
    det = get_corneal_reflection_detector()
    assert isinstance(det, CornealReflectionDetector)
    assert det.name == "corneal_reflection"


def test_corneal_reflection_non_portrait():
    """Verify non-portrait images cleanly return NO_EYES_DETECTED."""
    gray = np.ones((200, 200), dtype=np.uint8) * 128
    res = analyze_corneal_reflections(gray)
    assert res.status == "NO_EYES_DETECTED"
    assert res.face_count == 0

