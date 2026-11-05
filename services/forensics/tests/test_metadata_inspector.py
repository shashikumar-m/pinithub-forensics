"""
Phase 2 — Python metadata inspector tests.

Uses synthetic images created with Pillow — no real private images committed.
"""
import io
import pytest
from PIL import Image as PILImage

from app.detectors.metadata_inspector import MetadataInspector, get_metadata_inspector


def make_jpeg(width: int = 20, height: int = 20, quality: int = 85) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_png(width: int = 15, height: int = 15) -> bytes:
    img = PILImage.new("RGBA", (width, height), color=(50, 50, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_webp(width: int = 10, height: int = 10) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


@pytest.fixture
def inspector():
    return get_metadata_inspector()


class TestMetadataInspector:
    """Tests for the MetadataInspector detector."""

    def test_name_and_version(self, inspector):
        assert inspector.name == "metadata_inspector"
        assert inspector.version == "1.0.0"

    def test_jpeg_extraction_succeeds(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        assert result.details["status"] == "COMPLETED"
        assert "normalized_metadata" in result.details

    def test_png_extraction_succeeds(self, inspector):
        result = inspector.run("", image_bytes=make_png())
        assert result.details["status"] == "COMPLETED"

    def test_webp_extraction_succeeds(self, inspector):
        result = inspector.run("", image_bytes=make_webp())
        assert result.details["status"] == "COMPLETED"

    def test_no_score_fabricated(self, inspector):
        """Metadata extraction must not fabricate a score."""
        result = inspector.run("", image_bytes=make_jpeg())
        assert result.score is None
        assert result.confidence is None

    def test_camera_fields_null_without_exif(self, inspector):
        """A synthetic image has no camera metadata."""
        result = inspector.run("", image_bytes=make_jpeg())
        nm = result.details["normalized_metadata"]
        assert nm["camera"]["make"] is None
        assert nm["camera"]["model"] is None

    def test_c2pa_absent_for_plain_jpeg(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        nm = result.details["normalized_metadata"]
        assert nm["c2pa"]["status"] == "ABSENT"

    def test_has_gps_false_without_gps(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        nm = result.details["normalized_metadata"]
        assert nm["location"]["has_gps"] is False
        assert nm["location"]["latitude"] is None
        assert nm["location"]["longitude"] is None

    def test_characteristics_width_height(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg(30, 20))
        ch = result.details["characteristics"]
        assert ch["width"] == 30
        assert ch["height"] == 20

    def test_pixel_count(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg(12, 8))
        ch = result.details["characteristics"]
        assert ch["pixel_count"] == 96

    def test_aspect_ratio_reduced(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg(40, 30))
        ch = result.details["characteristics"]
        assert ch["aspect_ratio_w"] == 4
        assert ch["aspect_ratio_h"] == 3

    def test_png_has_alpha(self, inspector):
        result = inspector.run("", image_bytes=make_png())
        ch = result.details["characteristics"]
        assert ch["has_alpha"] is True

    def test_jpeg_has_quant_tables(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        ch = result.details["characteristics"]
        # JPEG should produce quantization tables
        if ch.get("jpeg"):
            assert "quant_tables" in ch["jpeg"]

    def test_jpeg_quality_is_estimate(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg(quality=75))
        ch = result.details["characteristics"]
        if ch.get("jpeg") and ch["jpeg"].get("quality_estimate") is not None:
            assert ch["jpeg"]["quality_is_estimate"] is True

    def test_empty_bytes_returns_failed(self, inspector):
        result = inspector.run("", image_bytes=b"")
        assert result.details.get("status") == "FAILED"

    def test_random_bytes_no_crash(self, inspector):
        result = inspector.run("", image_bytes=b"random garbage data 12345678")
        assert result is not None

    def test_evidence_items_structure(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        items = result.details.get("evidence_items", [])
        assert isinstance(items, list)
        for item in items:
            assert "category" in item
            assert "key" in item
            assert "value" in item
            assert "value_type" in item

    def test_gps_not_in_evidence_coords(self, inspector):
        """GPS coordinates must not appear in evidence_items keys."""
        result = inspector.run("", image_bytes=make_jpeg())
        items = result.details.get("evidence_items", [])
        coord_keys = {i["key"] for i in items}
        assert "gps_latitude" not in coord_keys
        assert "gps_longitude" not in coord_keys

    def test_detector_metadata_in_result(self, inspector):
        result = inspector.run("", image_bytes=make_jpeg())
        assert result.detector == "metadata_inspector"
        assert result.version == "1.0.0"

    def test_execution_time_recorded(self, inspector):
        result = inspector.timed_run("", image_bytes=make_jpeg())
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 0

    def test_note_present_in_details(self, inspector):
        """Must include a note that metadata is not a verdict."""
        result = inspector.run("", image_bytes=make_jpeg())
        note = result.details.get("note", "")
        assert "evidence" in note.lower() or "verdict" in note.lower()
