"""
Unit tests for C2PA (Content Credentials) Cryptographic Provenance Parser.
"""
import io
import pytest
from PIL import Image
from app.detectors.c2pa_parser import C2PAParserDetector, get_c2pa_parser_detector


def test_c2pa_parser_no_manifest():
    """Verify that a standard uncertified image returns NO_C2PA_MANIFEST."""
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    bio = io.BytesIO()
    img.save(bio, format="JPEG")
    jpeg_bytes = bio.getvalue()

    det = get_c2pa_parser_detector()
    res = det.run("", image_bytes=jpeg_bytes)
    assert res.score is None
    assert res.details["status"] == "NO_C2PA_MANIFEST"
    assert res.details["has_manifest"] is False


def test_c2pa_parser_synthetic_ai_manifest():
    """Verify that an image with an OpenAI / DALL-E C2PA manifest is confirmed as CRYPTOGRAPHIC_AI_CONFIRMED."""
    # Synthesize an APP11 JUMBF segment with C2PA OpenAI claim
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    bio = io.BytesIO()
    img.save(bio, format="JPEG")
    base_bytes = bio.getvalue()

    # Inject C2PA marker segment
    c2pa_payload = b"c2pa\x00\x00jumb\x00\x00OpenAI\x00\x00trainedAlgorithmicMedia\x00\x00DALL-E 3"
    marker = b"\xff\xeb" + (len(c2pa_payload) + 2).to_bytes(2, "big") + c2pa_payload
    injected_bytes = base_bytes[:2] + marker + base_bytes[2:]

    det = get_c2pa_parser_detector()
    res = det.run("", image_bytes=injected_bytes)
    assert res.score == 1.0
    assert res.details["status"] == "CRYPTOGRAPHIC_AI_CONFIRMED"
    assert res.details["is_ai_generated"] is True
    assert res.details["has_manifest"] is True


def test_c2pa_parser_camera_hardware_manifest():
    """Verify that an image with a Leica/Sony camera hardware C2PA manifest is confirmed as CRYPTOGRAPHIC_CAMERA_CONFIRMED."""
    img = Image.new("RGB", (100, 100), color=(50, 120, 80))
    bio = io.BytesIO()
    img.save(bio, format="JPEG")
    base_bytes = bio.getvalue()

    c2pa_payload = b"c2pa\x00\x00jumb\x00\x00Leica Camera\x00\x00c2pa.created\x00\x00Leica M11-P Hardware Secure Element"
    marker = b"\xff\xeb" + (len(c2pa_payload) + 2).to_bytes(2, "big") + c2pa_payload
    injected_bytes = base_bytes[:2] + marker + base_bytes[2:]

    det = get_c2pa_parser_detector()
    res = det.run("", image_bytes=injected_bytes)
    assert res.score == 0.0
    assert res.details["status"] == "CRYPTOGRAPHIC_CAMERA_CONFIRMED"
    assert res.details["is_camera_hardware"] is True
    assert res.details["has_manifest"] is True
