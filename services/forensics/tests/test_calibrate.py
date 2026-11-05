"""
Unit tests for Phase 7 Scientific Calibration (calibrate.py).
"""
import numpy as np
import pytest

from app.fusion.calibrate import (
    compute_ece,
    compute_brier_score,
    fit_temperature_scaling,
    EvidenceCalibrator,
    run_calibration,
)


def test_ece_perfect_calibration():
    # If confidence equals accuracy, ECE is near 0
    probs = np.array([0.1, 0.1, 0.9, 0.9])
    labels = np.array([0, 0, 1, 1])
    ece, bins = compute_ece(probs, labels, n_bins=10)
    assert ece < 0.15


def test_ece_bounds():
    rng = np.random.RandomState(42)
    probs = rng.uniform(0, 1, 100)
    labels = rng.randint(0, 2, 100)
    ece, bins = compute_ece(probs, labels, n_bins=15)
    assert 0.0 <= ece <= 1.0


def test_brier_score_bounds():
    probs = np.array([0.9, 0.8, 0.1])
    labels = np.array([1, 1, 0])
    brier = compute_brier_score(probs, labels)
    assert 0.0 <= brier <= 1.0


def test_fit_temperature_scaling():
    rng = np.random.RandomState(42)
    logits = rng.normal(0, 2, 200)
    labels = (logits > 0).astype(int)
    optimal_t, ece, brier, _ = fit_temperature_scaling(logits, labels)
    assert optimal_t > 0
    assert ece <= 0.10
    assert brier <= 0.15


def test_calibrator_clamping(tmp_path):
    calibrator = EvidenceCalibrator(str(tmp_path / "nonexistent.json"))
    assert not calibrator.is_calibrated
    # Without calibration, clamps between 0.02 and 0.98
    assert 0.01 < calibrator.calibrate_probability(0.0) < 0.05
    assert 0.95 < calibrator.calibrate_probability(1.0) < 0.99


def test_run_calibration_generates_file(tmp_path):
    out_file = str(tmp_path / "calib.json")
    res = run_calibration(output_path=out_file, n_samples=200, seed=42)
    assert res["ece_target_met"] is True
    assert res["brier_target_met"] is True
    assert (tmp_path / "calib.json").exists()

