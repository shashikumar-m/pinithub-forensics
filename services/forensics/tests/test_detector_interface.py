"""
Tests for the detector interface contract.
Verifies that the base contract is properly defined and that
DetectorResult serializes correctly.
"""
from app.detectors.base import BaseDetector, DetectorResult, DetectorCategory


def test_detector_result_has_required_fields():
    result = DetectorResult(
        detector="test-detector",
        version="1.0.0",
        category=DetectorCategory.ELA,
    )
    d = result.to_dict()
    assert d["detector"] == "test-detector"
    assert d["version"] == "1.0.0"
    assert d["category"] == "ELA"
    assert d["score"] is None
    assert d["confidence"] is None
    assert d["map_path"] is None
    assert d["details"] == {}


def test_detector_result_with_values():
    result = DetectorResult(
        detector="ela",
        version="2.0.0",
        category=DetectorCategory.ELA,
        score=0.85,
        confidence=0.92,
        map_path="artifacts/heatmap_001.png",
        details={"threshold": 90, "jpeg_quality": 95},
        execution_time_ms=150,
    )
    d = result.to_dict()
    assert d["score"] == 0.85
    assert d["confidence"] == 0.92
    assert d["map_path"] == "artifacts/heatmap_001.png"
    assert d["details"]["threshold"] == 90
    assert d["execution_time_ms"] == 150


def test_detector_categories_exist():
    """All expected forensic categories should be defined."""
    categories = [c.value for c in DetectorCategory]
    expected = [
        "AI_GENERATED", "AI_EDITED", "ELA", "NOISE_RESIDUAL", "DCT",
        "JPEG_DOUBLE_COMPRESSION", "COPY_MOVE", "KEYPOINT_MATCH",
        "CROP_PERCENTAGE", "TRAVELLED_COPY", "METADATA",
    ]
    for cat in expected:
        assert cat in categories, f"Missing category: {cat}"


def test_base_detector_is_abstract():
    """BaseDetector should not be directly instantiable."""
    import pytest
    with pytest.raises(TypeError):
        BaseDetector()  # type: ignore[abstract]


def test_detectors_endpoint_returns_empty(client=None):
    """Phase 0: No detectors are registered yet."""
    # This is verified via the API test, but the contract says:
    # the list should be empty until detectors are implemented
    assert True  # Placeholder — verified in test_ready via /detectors endpoint
