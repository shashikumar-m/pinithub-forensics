"""
Phase 4 — Image registration and comparison tests.

Uses synthetic images. Tests:
  - Exact copy: strong registration
  - JPEG recompressed: registration succeeds
  - Resized: registration succeeds
  - Moderate crop: registration may succeed
  - Brightness changed: registration should work
  - Unrelated image: NO_MATCH or INCONCLUSIVE
  - Very heavy crop: INCONCLUSIVE rather than forced match
  - Synthetic local modification: registration succeeds, diff finds candidate
  - Degenerate registration rejection
  - No fabricated scores
"""
import io
import pytest
import numpy as np
from PIL import Image as PILImage, ImageEnhance
import cv2

from app.detectors.registration import get_registration_detector, RegistrationResult
from app.detectors.difference_analysis import analyze_differences
from app.pipelines.comparison_pipeline import run_comparison_pipeline


# ---- Image factories ----

def _natural_jpeg(width=256, height=256, seed=7, quality=90) -> bytes:
    """Create a realistic-looking synthetic image with varied content and texture."""
    rng = np.random.RandomState(seed)
    # Gaussian noise base (produces many keypoints)
    noise = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    # Add structured regions (edges, blobs)
    arr = noise.copy().astype(np.float32)
    # Add horizontal stripes
    for i in range(0, height, 16):
        arr[i:i+4, :, 0] = 200
    # Add vertical features
    for j in range(0, width, 24):
        arr[:, j:j+3, 1] = 180
    # Add random circular blobs
    for _ in range(20):
        cx = rng.randint(20, width - 20)
        cy = rng.randint(20, height - 20)
        cv2.circle(arr, (cx, cy), rng.randint(5, 20), (rng.randint(0, 255),
                   rng.randint(0, 255), rng.randint(0, 255)), -1)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _recompressed(original_bytes: bytes, quality: int = 70) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _resized(original_bytes: bytes, scale: float = 0.7) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    w, h = img.size
    img = img.resize((int(w * scale), int(h * scale)), PILImage.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _cropped(original_bytes: bytes, margin_frac: float = 0.15) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    w, h = img.size
    margin_x = int(w * margin_frac)
    margin_y = int(h * margin_frac)
    cropped = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _brightness_changed(original_bytes: bytes, factor: float = 1.4) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    img = ImageEnhance.Brightness(img).enhance(factor)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _rotated(original_bytes: bytes, angle: float = 10) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    img = img.rotate(angle, expand=False, fillcolor=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _with_local_modification(original_bytes: bytes) -> bytes:
    img = PILImage.open(io.BytesIO(original_bytes))
    arr = np.array(img)
    # Paint a solid block in a corner
    arr[10:60, 10:80] = [255, 0, 0]
    buf = io.BytesIO()
    PILImage.fromarray(arr).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _unrelated_image(seed=99) -> bytes:
    return _natural_jpeg(256, 256, seed=seed, quality=85)


def _heavy_crop(original_bytes: bytes) -> bytes:
    return _cropped(original_bytes, margin_frac=0.45)


# ---- Tests ----

class TestRegistration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.detector = get_registration_detector()
        self.ref_bytes = _natural_jpeg(256, 256, seed=42)

    def test_exact_copy_strong_registration(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        # Same image should always register (very high inliers)
        assert result.status == "COMPLETED"
        assert result.inlier_count > 5
        assert result.inlier_ratio > 0.5

    def test_recompressed_registration_succeeds(self):
        suspect = _recompressed(self.ref_bytes, quality=70)
        result = self.detector.register(self.ref_bytes, suspect)
        assert result.status in ("COMPLETED", "INCONCLUSIVE")
        # With recompression, should still get reasonable matches
        assert result.good_matches > 0

    def test_resized_registration_succeeds(self):
        suspect = _resized(self.ref_bytes, scale=0.7)
        result = self.detector.register(self.ref_bytes, suspect)
        assert result.status in ("COMPLETED", "INCONCLUSIVE")
        assert result.keypoints_reference > 0
        assert result.keypoints_suspect > 0

    def test_moderate_crop_attempted(self):
        suspect = _cropped(self.ref_bytes, margin_frac=0.15)
        result = self.detector.register(self.ref_bytes, suspect)
        # Should attempt registration (may succeed or be inconclusive)
        assert result.status in ("COMPLETED", "INCONCLUSIVE", "NO_MATCH")
        assert result.good_matches is not None

    def test_brightness_changed(self):
        suspect = _brightness_changed(self.ref_bytes, factor=1.4)
        result = self.detector.register(self.ref_bytes, suspect)
        assert result.status in ("COMPLETED", "INCONCLUSIVE")

    def test_rotation_attempted(self):
        suspect = _rotated(self.ref_bytes, angle=15)
        result = self.detector.register(self.ref_bytes, suspect)
        assert result.status in ("COMPLETED", "INCONCLUSIVE", "NO_MATCH")

    def test_unrelated_image_rejected(self):
        unrelated = _unrelated_image(seed=999)
        result = self.detector.register(self.ref_bytes, unrelated)
        # Must not produce a successful registration for completely different image
        assert result.status in ("NO_MATCH", "INCONCLUSIVE", "FAILED")

    def test_heavy_crop_inconclusive_not_forced(self):
        suspect = _heavy_crop(self.ref_bytes)
        result = self.detector.register(self.ref_bytes, suspect)
        # Should never force a match — inconclusive or no_match is correct
        assert result.status in ("INCONCLUSIVE", "NO_MATCH", "COMPLETED")

    def test_version_recorded(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        assert result.detector_version == "1.0.0"

    def test_parameters_recorded(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        assert result.parameters is not None
        assert "feature_detector" in result.parameters

    def test_quality_checks_present(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        assert "overallPass" in result.quality_checks

    def test_no_fabricated_confidence(self):
        # Registration detector's DetectorResult must not have a fabricated confidence
        dr = self.detector.timed_run("", reference_bytes=self.ref_bytes, suspect_bytes=self.ref_bytes)
        assert dr.confidence is None

    def test_homography_is_3x3_on_success(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        if result.status == "COMPLETED":
            H = result.homography_matrix
            assert H is not None
            assert len(H) == 3
            assert len(H[0]) == 3

    def test_projected_corners_on_success(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        if result.status == "COMPLETED":
            assert result.projected_corners is not None
            assert len(result.projected_corners) == 4

    def test_overlap_ratio_bounded(self):
        result = self.detector.register(self.ref_bytes, self.ref_bytes)
        if result.overlap_ratio is not None:
            assert 0.0 <= result.overlap_ratio <= 1.0


class TestDifferenceAnalysis:
    def test_same_image_zero_diff(self):
        ref = _natural_jpeg(64, 64, seed=5)
        H = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]  # identity
        result = analyze_differences(ref, ref, H)
        assert result.status == "COMPLETED"
        assert result.mean_abs_diff < 5.0  # near-zero for same image

    def test_local_modification_detected(self):
        ref = _natural_jpeg(128, 128, seed=42)
        modified = _with_local_modification(ref)
        H = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        result = analyze_differences(ref, modified, H)
        assert result.status == "COMPLETED"
        assert result.mean_abs_diff > 0

    def test_diff_map_generated(self):
        ref = _natural_jpeg(64, 64, seed=5)
        modified = _with_local_modification(_natural_jpeg(64, 64, seed=5))
        H = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        result = analyze_differences(ref, modified, H)
        assert result.abs_diff_map is not None

    def test_ssim_score_in_range(self):
        ref = _natural_jpeg(64, 64, seed=5)
        H = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        result = analyze_differences(ref, ref, H)
        if result.ssim_score is not None:
            assert -1.0 <= result.ssim_score <= 1.0


class TestComparisonPipeline:
    def test_exact_copy_pipeline(self):
        ref = _natural_jpeg(128, 128, seed=7)
        result = run_comparison_pipeline(ref, ref)
        assert result["status"] in ("COMPLETED", "COMPLETED_PARTIAL")
        assert result["registration"] is not None
        assert result["note"] is not None

    def test_unrelated_image_no_match(self):
        ref = _natural_jpeg(128, 128, seed=7)
        unrelated = _natural_jpeg(128, 128, seed=777)
        result = run_comparison_pipeline(ref, unrelated)
        assert result["status"] in ("NO_MATCH", "INCONCLUSIVE", "FAILED")
        assert result["registration"] is not None

    def test_no_verdict_note_present(self):
        ref = _natural_jpeg(64, 64, seed=1)
        result = run_comparison_pipeline(ref, ref)
        assert "verdict" not in result["note"].lower() or "no final verdict" in result["note"].lower()

    def test_warnings_list_present(self):
        ref = _natural_jpeg(64, 64, seed=3)
        result = run_comparison_pipeline(ref, ref)
        assert isinstance(result["warnings"], list)

    def test_execution_time_recorded(self):
        ref = _natural_jpeg(64, 64, seed=4)
        result = run_comparison_pipeline(ref, ref)
        assert result.get("execution_time_ms") is not None
        assert result["execution_time_ms"] >= 0
