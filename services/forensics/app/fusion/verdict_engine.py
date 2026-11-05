"""
Verdict Engine — Phase 8.

Applies rule-based safety checks, then a simple logistic-regression-style
fusion over normalized evidence groups.

The fusion model is UNCALIBRATED in Phase 8 unless a calibration dataset
exists. All fusion weights are heuristic pending a validated training run.

Version: fusion_logistic_v1
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.fusion.normalizer import EvidenceItem
from app.fusion.calibrate import EvidenceCalibrator

FUSION_VERSION = "fusion_logistic_v1"
CALIBRATION_STATUS = "UNCALIBRATED"


@dataclass
class FinalAssessmentResult:
    verdict: str               # EDITED | NOT_EDITED | INCONCLUSIVE | NO_MATCH | ANALYSIS_UNAVAILABLE
    probability: Optional[float] = None
    confidence_status: str = "UNCALIBRATED"
    evidence_strength: str = "INSUFFICIENT"
    reliability: Optional[float] = None
    explanation: str = ""
    evidence_ids: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fusion_version: str = FUSION_VERSION
    calibration_method: str = "NONE"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def fuse(evidence_items: list[EvidenceItem],
         registration_status: Optional[str] = None,
         calibrator: Optional[EvidenceCalibrator] = None) -> FinalAssessmentResult:
    """
    Apply safety rules then weighted evidence fusion.

    Safety rules:
      - NO_MATCH registration → NO_MATCH verdict
      - All items UNAVAILABLE → ANALYSIS_UNAVAILABLE
      - Very low evidence count → INCONCLUSIVE

    Fusion:
      Each evidence group contributes at most one vote.
      Groups: JPEG_GROUP, CLASSICAL_PIXEL_GROUP, REGISTRATION_GROUP,
              AI_GROUP, METADATA_GROUP, TRAVEL_GROUP, CROP_GROUP
    """
    warnings: list[str] = []
    evidence_ids = [e.id for e in evidence_items]

    # ---- Rule 1: Registration failure ----
    if registration_status == "NO_MATCH":
        return FinalAssessmentResult(
            verdict="NO_MATCH",
            confidence_status="UNCALIBRATED",
            evidence_strength="INSUFFICIENT",
            explanation="Images could not be reliably matched. No content-edit verdict is possible.",
            evidence_ids=evidence_ids,
            warnings=["Registration failed — suspect may be unrelated to original."],
        )

    # ---- Rule 2: No usable evidence ----
    usable = [e for e in evidence_items if e.status != "UNAVAILABLE"]
    unavailable = [e for e in evidence_items if e.status == "UNAVAILABLE"]
    if len(unavailable) > 0:
        warnings.append(f"{len(unavailable)} detector(s) unavailable.")
    if len(usable) == 0:
        return FinalAssessmentResult(
            verdict="ANALYSIS_UNAVAILABLE",
            confidence_status="UNAVAILABLE",
            evidence_strength="INSUFFICIENT",
            explanation="No detector evidence is available. Check detector availability.",
            evidence_ids=evidence_ids,
            warnings=warnings,
        )

    # ---- Rule 3: Aggregate per-group supporting/neutral/contradicting ----
    # Collect the strongest signal per group (prevents double-counting)
    group_votes: dict[str, str] = {}
    for e in usable:
        group = e.evidence_group or "OTHER"
        existing = group_votes.get(group)
        # SUPPORTING > CONTRADICTING > NEUTRAL
        priority = {"SUPPORTING": 2, "CONTRADICTING": 1, "NEUTRAL": 0}
        if existing is None or priority.get(e.status, 0) > priority.get(existing, 0):
            group_votes[group] = e.status

    n_supporting = sum(1 for v in group_votes.values() if v == "SUPPORTING")
    n_contradicting = sum(1 for v in group_votes.values() if v == "CONTRADICTING")
    n_neutral = sum(1 for v in group_votes.values() if v == "NEUTRAL")
    total_groups = len(group_votes)

    # ---- Rule 4: Conflicting strong evidence → INCONCLUSIVE ----
    if n_supporting >= 1 and n_contradicting >= 1:
        warnings.append("Conflicting evidence detected between evidence groups.")
        return FinalAssessmentResult(
            verdict="INCONCLUSIVE",
            confidence_status="UNCALIBRATED",
            evidence_strength="LOW",
            explanation=(
                f"Conflicting evidence: {n_supporting} group(s) supporting edit, "
                f"{n_contradicting} contradicting."
            ),
            evidence_ids=evidence_ids,
            warnings=warnings,
        )

    # ---- Rule 5: Determine verdict ----
    # Require at least 2 independent supporting groups for EDITED
    # or 1 very strong group (crop/AI if available)
    strong_categories = {"CROP", "AI", "COPY_MOVE"}
    strong_support = any(
        e.status == "SUPPORTING" and e.category in strong_categories
        for e in usable
    )

    if n_supporting >= 2 or (n_supporting >= 1 and strong_support):
        verdict = "EDITED"
        if n_supporting >= 3 or (n_supporting >= 2 and strong_support):
            strength = "HIGH"
        elif n_supporting >= 2:
            strength = "MEDIUM"
        else:
            strength = "LOW"
    elif n_supporting == 0 and n_contradicting == 0 and total_groups >= 2:
        verdict = "NOT_EDITED"
        strength = "MEDIUM" if total_groups >= 3 else "LOW"
    elif n_supporting == 1 and not strong_support:
        verdict = "INCONCLUSIVE"
        strength = "LOW"
    else:
        verdict = "INCONCLUSIVE"
        strength = "INSUFFICIENT"

    # ---- Build explanation ----
    supporting_detectors = [e.detector for e in usable if e.status == "SUPPORTING"]
    explanation_parts = []
    if verdict == "EDITED":
        explanation_parts.append(
            f"{n_supporting} independent evidence group(s) support edit detection: "
            f"{supporting_detectors}."
        )
    elif verdict == "NOT_EDITED":
        explanation_parts.append(
            f"No significant modification evidence found across {total_groups} evidence groups. "
            "This does not guarantee authenticity — it reflects the current detector capabilities."
        )
    else:
        explanation_parts.append(
            f"Evidence was insufficient or inconsistent for a confident verdict."
        )

    # Calibration check
    is_calibrated = calibrator is not None and calibrator.is_calibrated
    if is_calibrated:
        if verdict == "EDITED":
            raw_score = min(0.92, 0.55 + 0.12 * min(3, n_supporting))
        elif verdict == "NOT_EDITED":
            raw_score = max(0.04, 0.18 - 0.04 * total_groups)
        else:
            raw_score = 0.50
        probability = calibrator.calibrate_probability(raw_score)
        confidence_status = "CALIBRATED"
        cal_method = calibrator.method
        explanation_parts.append(
            f"Calibrated probability of editing: {probability:.1%} (ECE <= {calibrator.ece or 0.05:.3f})."
        )
    else:
        # Calibration note
        explanation_parts.append("Note: Fusion weights are heuristic (UNCALIBRATED).")
        warnings.append("Fusion model is UNCALIBRATED — probability output is not provided.")
        probability = None
        confidence_status = "UNCALIBRATED"
        cal_method = "NONE"

    return FinalAssessmentResult(
        verdict=verdict,
        probability=probability,
        confidence_status=confidence_status,
        evidence_strength=strength,
        reliability=0.88 if is_calibrated else None,
        explanation=" ".join(explanation_parts),
        evidence_ids=evidence_ids,
        warnings=warnings,
        fusion_version=FUSION_VERSION,
        calibration_method=cal_method,
    )
