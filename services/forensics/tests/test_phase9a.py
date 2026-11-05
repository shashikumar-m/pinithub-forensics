"""
Phase 9A — AI Model Registry, Dataset Splitting, Frozen Test, Evaluation Tests.

Covers:
  - Model loading: valid, missing, corrupt, incompatible
  - Model hash determinism
  - Dataset: source separation, frozen test, no leakage
  - Inference: unavailable=null, preprocessing shape
  - Safety: UNAVAILABLE never becomes NO_AI_EVIDENCE
  - Evaluation pipeline
"""
import hashlib
import io
import json
import os
import struct
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from app.models.ai_model_registry import (
    AIModelLoader, get_ai_model_loader, reset_ai_model_loader,
    DEFAULT_THRESHOLD, IMG_SIZE, MODEL_ID, MODEL_VERSION, PREPROCESSING_VERSION,
)
from app.models.ai_dataset import ManifestEntry, split_dataset
from app.models.dataset_splitter import (
    create_splits, freeze_test_set, validate_no_leakage,
    check_test_not_in_train, load_frozen_test,
)
from app.models.synthetic_dataset import generate_synthetic_dataset, _create_edit_mask
from app.detectors.ai_detector import get_ai_detector, reset_ai_detector


# ---- Helpers ----

def _make_jpeg(w=64, h=64, seed=1) -> bytes:
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (h, w, 3), dtype=np.uint8)
    buf = io.BytesIO()
    PILImage.fromarray(arr).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _write_fake_weights(path: str, valid: bool = True) -> str:
    """Write a fake .pth that triggers load failure."""
    if valid:
        # A minimal valid state dict for a 1-layer model — will fail strict=True
        # but is a valid pickle/tensor file
        import torch
        d = {"fake.weight": torch.zeros(1)}
        torch.save(d, path)
    else:
        with open(path, "wb") as f:
            f.write(b"THIS_IS_CORRUPT_DATA_NOT_A_PYTORCH_FILE")
    return path


# ---- AIModelLoader tests ----

class TestAIModelLoader:
    def setup_method(self):
        reset_ai_model_loader()
        reset_ai_detector()

    def test_missing_weights_returns_unavailable(self):
        loader = AIModelLoader("/nonexistent/path/model.pth")
        assert not loader.is_available()
        assert loader._load_error is not None

    def test_no_path_returns_unavailable(self):
        loader = AIModelLoader(None)
        # Ensure AI_WEIGHTS_PATH is not set
        os.environ.pop("AI_WEIGHTS_PATH", None)
        assert not loader.is_available()

    def test_predict_returns_none_when_unavailable(self):
        loader = AIModelLoader("/no/weights.pth")
        result = loader.predict(_make_jpeg())
        assert result is None

    def test_corrupt_weights_returns_unavailable(self):
        with tempfile.NamedTemporaryFile(suffix=".pth", delete=False) as f:
            f.write(b"CORRUPTED_DATA_XYZ_12345")
            tmppath = f.name
        try:
            loader = AIModelLoader(tmppath)
            assert not loader.is_available()
            assert loader._load_error is not None
        finally:
            os.unlink(tmppath)

    def test_model_hash_is_deterministic(self):
        with tempfile.NamedTemporaryFile(suffix=".pth", delete=False) as f:
            f.write(b"fake_model_data_for_hash_test")
            tmppath = f.name
        try:
            expected = hashlib.sha256(b"fake_model_data_for_hash_test").hexdigest()
            # The hash function in ai_model_registry is standalone
            from app.models.ai_model_registry import _sha256_file
            actual = _sha256_file(tmppath)
            assert actual == expected
            assert len(actual) == 64
        finally:
            os.unlink(tmppath)

    def test_get_metadata_always_returns(self):
        loader = AIModelLoader(None)
        meta = loader.get_metadata()
        assert meta.model_id == MODEL_ID
        assert meta.model_version == MODEL_VERSION
        assert meta.preprocessing_version == PREPROCESSING_VERSION
        assert meta.threshold == DEFAULT_THRESHOLD
        assert meta.is_available is False
        assert meta.model_hash is None

    def test_metadata_to_dict_serializable(self):
        loader = AIModelLoader(None)
        d = loader.get_metadata().to_dict()
        json.dumps(d)  # must not raise

    def test_img_size_matches_preprocessing(self):
        assert IMG_SIZE == (512, 512)


# ---- Safety: UNAVAILABLE never becomes NO_AI_EVIDENCE ----

class TestUnavailableSafety:
    def setup_method(self):
        reset_ai_detector()
        reset_ai_model_loader()
        os.environ.pop("AI_WEIGHTS_PATH", None)

    def test_unavailable_status_when_no_weights(self):
        detector = get_ai_detector()
        result = detector.run("", image_bytes=_make_jpeg())
        d = result.details
        assert d["status"] == "UNAVAILABLE"
        assert d["status"] != "NO_AI_EVIDENCE"

    def test_unavailable_probability_is_null(self):
        detector = get_ai_detector()
        result = detector.run("", image_bytes=_make_jpeg())
        d = result.details
        # No image_level_score should be present or it should be None
        score = d.get("image_level_score")
        if d["status"] == "UNAVAILABLE":
            assert score is None

    def test_unavailable_no_fabricated_regions(self):
        detector = get_ai_detector()
        result = detector.run("", image_bytes=_make_jpeg())
        d = result.details
        if d["status"] == "UNAVAILABLE":
            assert d.get("regions") is None or d.get("regions") == []


# ---- Dataset tests ----

class TestDatasetSplit:
    def test_source_isolation_no_leakage(self):
        entries = [
            ManifestEntry(f"img_{i}_{j}.jpg", "AI_EDITED_LOCAL", "",
                          source_image=f"src_{i}.jpg")
            for i in range(10) for j in range(3)
        ] + [
            ManifestEntry(f"real_{i}.jpg", "REAL", "")
            for i in range(20)
        ]
        train, val, test = split_dataset(entries, seed=42)
        violations = validate_no_leakage(train, val, test)
        assert violations == [], f"Leakage: {violations}"

    def test_all_splits_non_empty(self):
        entries = [ManifestEntry(f"img_{i}.jpg", "REAL", "") for i in range(30)]
        train, val, test = split_dataset(entries, seed=42)
        assert len(train) > 0
        assert len(val) > 0
        assert len(test) > 0

    def test_no_duplicate_images_across_splits(self):
        entries = [ManifestEntry(f"img_{i}.jpg", "REAL", "") for i in range(30)]
        train, val, test = split_dataset(entries, seed=42)
        all_images = [e.image for e in train + val + test]
        assert len(all_images) == len(set(all_images))

    def test_frozen_test_hash_is_deterministic(self):
        entries = [ManifestEntry(f"img_{i}.jpg", "REAL", "") for i in range(30)]
        _, _, test = split_dataset(entries, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = freeze_test_set(test, tmpdir)
            f2 = freeze_test_set(test, tmpdir)
        assert f1.manifest_sha256 == f2.manifest_sha256

    def test_frozen_test_has_required_fields(self):
        entries = [ManifestEntry(f"img_{i}.jpg", "REAL", "") for i in range(30)]
        _, _, test = split_dataset(entries, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            frozen = freeze_test_set(test, tmpdir)
        assert frozen.dataset_version is not None
        assert frozen.creation_timestamp is not None
        assert frozen.seed == 42
        assert frozen.entry_count == len(test)
        assert len(frozen.manifest_sha256) == 64

    def test_check_test_not_in_train_catches_leak(self):
        # Artificially create a leak
        src = "shared_source.jpg"
        train_entries = [ManifestEntry("train_img.jpg", "REAL", "train", source_image=src)]
        test_entries  = [ManifestEntry("test_img.jpg", "REAL", "test",  source_image=src)]
        with tempfile.TemporaryDirectory() as tmpdir:
            frozen = freeze_test_set(test_entries, tmpdir)
        violations = check_test_not_in_train(train_entries, frozen)
        assert len(violations) > 0

    def test_check_test_not_in_train_clean(self):
        train_entries = [ManifestEntry("train_img.jpg", "REAL", "train", source_image="src_train.jpg")]
        test_entries  = [ManifestEntry("test_img.jpg",  "REAL", "test",  source_image="src_test.jpg")]
        with tempfile.TemporaryDirectory() as tmpdir:
            frozen = freeze_test_set(test_entries, tmpdir)
        violations = check_test_not_in_train(train_entries, frozen)
        assert violations == []


# ---- Synthetic dataset tests ----

class TestSyntheticDataset:
    def test_generates_all_label_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = generate_synthetic_dataset(tmpdir, n_real=5, n_generated=3)
        labels = {e.label for e in entries}
        assert "REAL" in labels
        assert "AI_EDITED_LOCAL" in labels
        assert "AI_GENERATED" in labels

    def test_edited_entries_have_masks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = generate_synthetic_dataset(tmpdir, n_real=3, n_generated=2)
            for e in entries:
                if e.label == "AI_EDITED_LOCAL":
                    assert e.mask is not None
                    assert (Path(tmpdir) / e.mask).exists()

    def test_area_percentages_are_positive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = generate_synthetic_dataset(tmpdir, n_real=3, n_generated=2)
        for e in entries:
            if e.label == "AI_EDITED_LOCAL":
                assert e.edited_area_percentage is not None
                assert e.edited_area_percentage > 0

    def test_2pct_bucket_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = generate_synthetic_dataset(tmpdir, n_real=5, n_generated=2,
                                                  target_edit_pcts=[3.0])
        buckets = {e.area_bucket for e in entries if e.label == "AI_EDITED_LOCAL"}
        assert "2–5%" in buckets

    def test_create_edit_mask_area_accurate(self):
        mask, pct = _create_edit_mask(256, 256, 2.0, seed=1)
        assert 1.0 <= pct <= 5.0  # within reasonable range of 2%

    def test_source_images_recorded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = generate_synthetic_dataset(tmpdir, n_real=3, n_generated=2)
        for e in entries:
            assert e.source_image is not None

    def test_full_split_creation_no_leakage(self):
        from app.utils.ai_evaluation_v2 import create_and_freeze_splits
        with tempfile.TemporaryDirectory() as tmpdir:
            result = create_and_freeze_splits(tmpdir, seed=42, generate_synthetic=True)
        assert result.get("leakage_clean") is True
        assert result["train_count"] > 0
        assert result["test_count"] > 0
        assert result["frozen_test_hash"] is not None


# ---- Evaluation pipeline tests ----

class TestEvaluationPipeline:
    def setup_method(self):
        reset_ai_detector()
        reset_ai_model_loader()
        os.environ.pop("AI_WEIGHTS_PATH", None)

    def test_eval_returns_unavailable_when_no_model(self):
        from app.utils.ai_evaluation_v2 import run_frozen_test_evaluation
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create splits so frozen manifest exists
            from app.utils.ai_evaluation_v2 import create_and_freeze_splits
            create_and_freeze_splits(tmpdir, generate_synthetic=True)
            result = run_frozen_test_evaluation(tmpdir, tmpdir)
        assert result.get("status") == "UNAVAILABLE"

    def test_eval_without_frozen_manifest_returns_error(self):
        from app.utils.ai_evaluation_v2 import run_frozen_test_evaluation
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_frozen_test_evaluation(tmpdir, tmpdir)
        assert "error" in result

    def test_create_and_freeze_produces_frozen_manifest(self):
        from app.utils.ai_evaluation_v2 import create_and_freeze_splits
        tmpdir = tempfile.mkdtemp()
        try:
            result = create_and_freeze_splits(tmpdir, generate_synthetic=True)
            frozen_path = Path(tmpdir) / "splits" / "frozen_test.json"
            assert frozen_path.exists(), f"Frozen manifest not found at {frozen_path}"
            assert result["frozen_test_hash"] is not None
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_frozen_test_hash_prevents_modification(self):
        """Changing a test entry changes the hash."""
        entries_a = [ManifestEntry("a.jpg", "REAL", "test")]
        entries_b = [ManifestEntry("a.jpg", "REAL", "test"),
                     ManifestEntry("b.jpg", "REAL", "test")]
        with tempfile.TemporaryDirectory() as tmpdir:
            fa = freeze_test_set(entries_a, tmpdir)
        with tempfile.TemporaryDirectory() as tmpdir:
            fb = freeze_test_set(entries_b, tmpdir)
        assert fa.manifest_sha256 != fb.manifest_sha256
