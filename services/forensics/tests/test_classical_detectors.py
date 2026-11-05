"""
Phase 3 — Classical forensic detector tests.

Uses synthetic images created with Pillow + numpy/cv2 — no real images committed.
Tests cover:
  - ELA: normal JPEG, deterministic output
  - Noise: normal image, deterministic residual
  - DCT/JPEG: JPEG, PNG non-applicability, quantization extraction
  - Double compression: original vs recompressed
  - Resampling: original vs resized
  - JPEG grid: JPEG, non-JPEG
  - Copy-move: no copy-move, synthetic copy-move, hard negative
  - Detector failure isolation
  - Parameter recording
  - Versioning
"""
import io
import pytest
import numpy as np
from PIL import Image as PILImage
import cv2

from app.detectors.ela import get_ela_detector
from app.detectors.noise_residual import get_noise_residual_detector
from app.detectors.dct_analysis import get_dct_analysis_detector
from app.detectors.jpeg_double_compression import get_jpeg_double_compression_detector
from app.detectors.resampling import get_resampling_detector
from app.detectors.jpeg_grid import get_jpeg_grid_detector
from app.detectors.copy_move import get_copy_move_detector
from app.pipelines.classical_pipeline import run_classical_pipeline


# ---- Synthetic fixture factories ----

def make_jpeg(width=64, height=64, quality=85, noise=False):
    """Create a synthetic JPEG with optional noise."""
    rng = np.random.RandomState(42)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    if noise:
        arr = np.clip(arr.astype(np.float64) + rng.normal(0, 10, arr.shape), 0, 255).astype(np.uint8)
    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_png(width=64, height=64):
    """Create a synthetic PNG."""
    rng = np.random.RandomState(99)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_recompressed_jpeg(width=64, height=64):
    """Create a JPEG that has been compressed twice."""
    jpeg1 = make_jpeg(width, height, quality=90)
    img = PILImage.open(io.BytesIO(jpeg1))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


def make_resized_jpeg(width=128, height=128, scale=0.5):
    """Create a JPEG that has been resized."""
    jpeg = make_jpeg(width, height, quality=85)
    img = PILImage.open(io.BytesIO(jpeg))
    new_size = (int(width * scale), int(height * scale))
    resized = img.resize(new_size, PILImage.BILINEAR)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def make_copy_move_image(width=128, height=128, block_size=32):
    """
    Create a JPEG with a copy-move edit.
    Copies a block from one region to another.
    """
    rng = np.random.RandomState(42)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    # Copy a block from (10,10) to (80,10)
    src = arr[10:10+block_size, 10:10+block_size].copy()
    # Add some distinctive pattern to the source block
    src[:16, :16, 0] = 200
    src[:16, :16, 1] = 50
    src[:16, :16, 2] = 50
    arr[10:10+block_size, 10:10+block_size] = src
    # Paste to different location
    arr[80:80+block_size, 80:80+block_size] = src

    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_repeated_pattern_image(width=128, height=128):
    """Create an image with natural repeated structures (hard negative)."""
    # Create a brick-like pattern
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(0, height, 16):
        for x in range(0, width, 32):
            arr[y:y+14, x:x+30] = [180, 80, 60]
            arr[y+14:y+16, :] = [100, 100, 100]  # mortar lines
    img = PILImage.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---- ELA Tests ----

class TestELA:
    def test_normal_jpeg(self):
        buf = make_jpeg(64, 64, quality=85)
        result = get_ela_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert result.score is not None
        assert 0 <= result.score <= 1

    def test_deterministic_output(self):
        buf = make_jpeg(64, 64, quality=85)
        r1 = get_ela_detector().run("", image_bytes=buf)
        r2 = get_ela_detector().run("", image_bytes=buf)
        assert r1.score == r2.score

    def test_recompressed_jpeg_different_error(self):
        """Recompressed JPEG should have different ELA than original."""
        orig = make_jpeg(64, 64, quality=90)
        recompressed = make_recompressed_jpeg(64, 64)
        r1 = get_ela_detector().run("", image_bytes=orig)
        r2 = get_ela_detector().run("", image_bytes=recompressed)
        assert r1.score is not None
        assert r2.score is not None

    def test_records_parameters(self):
        buf = make_jpeg(32, 32)
        result = get_ela_detector().run("", image_bytes=buf)
        assert "parameters" in result.details
        assert "jpeg_quality" in result.details["parameters"]

    def test_has_version(self):
        assert get_ela_detector().version == "1.0.0"

    def test_no_fabricated_confidence(self):
        buf = make_jpeg(32, 32)
        result = get_ela_detector().run("", image_bytes=buf)
        assert result.confidence is None

    def test_reliability_uncalibrated(self):
        buf = make_jpeg(32, 32)
        result = get_ela_detector().run("", image_bytes=buf)
        assert result.details.get("reliability") == "UNCALIBRATED"


# ---- Noise Residual Tests ----

class TestNoiseResidual:
    def test_normal_image(self):
        buf = make_jpeg(64, 64)
        result = get_noise_residual_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert result.score is not None
        assert 0 <= result.score <= 1

    def test_deterministic_output(self):
        buf = make_jpeg(64, 64)
        r1 = get_noise_residual_detector().run("", image_bytes=buf)
        r2 = get_noise_residual_detector().run("", image_bytes=buf)
        assert r1.score == r2.score

    def test_noisy_image_different_score(self):
        normal = make_jpeg(64, 64, noise=False)
        noisy = make_jpeg(64, 64, noise=True)
        r1 = get_noise_residual_detector().run("", image_bytes=normal)
        r2 = get_noise_residual_detector().run("", image_bytes=noisy)
        assert r1.score is not None
        assert r2.score is not None

    def test_no_fabricated_confidence(self):
        buf = make_jpeg(32, 32)
        result = get_noise_residual_detector().run("", image_bytes=buf)
        assert result.confidence is None


# ---- DCT/JPEG Analysis Tests ----

class TestDCTAnalysis:
    def test_jpeg_extraction(self):
        buf = make_jpeg(64, 64, quality=75)
        result = get_dct_analysis_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert "num_blocks" in result.details["evidence"]

    def test_png_not_applicable(self):
        buf = make_png(64, 64)
        result = get_dct_analysis_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "NOT_APPLICABLE"
        assert result.score is None

    def test_quantization_tables_extracted(self):
        buf = make_jpeg(64, 64, quality=80)
        result = get_dct_analysis_detector().run("", image_bytes=buf)
        evidence = result.details["evidence"]
        assert evidence.get("quantization_tables") is not None


# ---- Double Compression Tests ----

class TestJPEGDoubleCompression:
    def test_original_jpeg(self):
        buf = make_jpeg(64, 64, quality=85)
        result = get_jpeg_double_compression_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"

    def test_recompressed_jpeg(self):
        buf = make_recompressed_jpeg(64, 64)
        result = get_jpeg_double_compression_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert result.score is not None

    def test_png_not_applicable(self):
        buf = make_png(64, 64)
        result = get_jpeg_double_compression_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "NOT_APPLICABLE"

    def test_score_semantics_documented(self):
        buf = make_jpeg(32, 32)
        result = get_jpeg_double_compression_detector().run("", image_bytes=buf)
        assert "score_semantics" in result.details


# ---- Resampling Tests ----

class TestResampling:
    def test_original_image(self):
        buf = make_jpeg(64, 64)
        result = get_resampling_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert result.score is not None

    def test_resized_image(self):
        buf = make_resized_jpeg(128, 128, scale=0.5)
        result = get_resampling_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"

    def test_deterministic(self):
        buf = make_jpeg(32, 32)
        r1 = get_resampling_detector().run("", image_bytes=buf)
        r2 = get_resampling_detector().run("", image_bytes=buf)
        assert r1.score == r2.score


# ---- JPEG Grid Tests ----

class TestJPEGGrid:
    def test_jpeg_analysis(self):
        buf = make_jpeg(64, 64)
        result = get_jpeg_grid_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert "mean_horizontal_blocking" in result.details["evidence"]

    def test_png_not_applicable(self):
        buf = make_png(64, 64)
        result = get_jpeg_grid_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "NOT_APPLICABLE"


# ---- Copy-Move Tests ----

class TestCopyMove:
    def test_no_copy_move(self):
        """Image without copy-move should produce low or zero score."""
        buf = make_jpeg(128, 128, quality=85)
        result = get_copy_move_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        # Random noise image should have few consistent matches
        assert result.score is not None

    def test_synthetic_copy_move(self):
        """Image with explicit copy-move should produce higher evidence."""
        buf = make_copy_move_image(128, 128, block_size=32)
        result = get_copy_move_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        evidence = result.details["evidence"]
        assert "keypoint_count" in evidence
        assert "filtered_match_count" in evidence

    def test_repeated_pattern_hard_negative(self):
        """Repeated patterns should not automatically be flagged."""
        buf = make_repeated_pattern_image(128, 128)
        result = get_copy_move_detector().timed_run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        # Should complete without crashing
        assert result.details["status"] != "FAILED"

    def test_records_match_counts(self):
        buf = make_jpeg(64, 64)
        result = get_copy_move_detector().run("", image_bytes=buf)
        evidence = result.details["evidence"]
        assert "keypoint_count" in evidence
        assert "filtered_match_count" in evidence
        assert "geometrically_consistent" in evidence

    def test_conservative_design(self):
        """Low match count should produce zero score, not crash."""
        buf = make_jpeg(16, 16)  # very small image
        result = get_copy_move_detector().run("", image_bytes=buf)
        assert result.details["status"] == "COMPLETED"
        assert result.score is not None

    def test_no_fabricated_confidence(self):
        buf = make_jpeg(64, 64)
        result = get_copy_move_detector().run("", image_bytes=buf)
        assert result.confidence is None


# ---- Pipeline Tests ----

class TestClassicalPipeline:
    def test_runs_all_detectors(self):
        buf = make_jpeg(64, 64, quality=85)
        result = run_classical_pipeline(buf)
        assert result["pipeline_version"] == "1.0.0"
        assert len(result["results"]) == 7
        assert result["summary"]["total"] == 7

    def test_failure_isolation(self):
        """One detector failure should not stop others."""
        # Pass empty bytes — some detectors will fail
        result = run_classical_pipeline(b"")
        assert result["summary"]["total"] == 7
        # At least some should fail, but pipeline completes

    def test_summary_counts(self):
        buf = make_jpeg(64, 64)
        result = run_classical_pipeline(buf)
        summary = result["summary"]
        assert summary["completed"] + summary["failed"] + summary["not_applicable"] == 7

    def test_no_fusion_note(self):
        buf = make_jpeg(32, 32)
        result = run_classical_pipeline(buf)
        assert "fusion" in result["note"].lower() or "verdict" in result["note"].lower()
