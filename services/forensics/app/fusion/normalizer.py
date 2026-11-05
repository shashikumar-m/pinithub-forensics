"""
Evidence Normalizer — Phase 8.

Converts raw detector outputs (from Phases 2–7) into a common
EvidenceItem structure for fusion.

Every item preserves:
  - detector identity and version
  - raw score (NOT treated as a probability)
  - interpretation
  - reliability
  - known limitations

Evidence grouping prevents obvious double-counting.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# Evidence groups to prevent double-counting
EVIDENCE_GROUPS = {
    "ELA":       "JPEG_GROUP",
    "DCT":       "JPEG_GROUP",
    "JPEG_DOUBLE_COMPRESSION": "JPEG_GROUP",
    "JPEG_GRID": "JPEG_GROUP",
    "NOISE":     "CLASSICAL_PIXEL_GROUP",
    "COPY_MOVE": "CLASSICAL_PIXEL_GROUP",
    "RESAMPLING": "CLASSICAL_PIXEL_GROUP",
    "AI":        "AI_GROUP",
    "REGISTRATION": "REGISTRATION_GROUP",
    "DIFFERENCE":   "REGISTRATION_GROUP",
    "CROP":      "CROP_GROUP",
    "METADATA":  "METADATA_GROUP",
    "TRAVEL":    "TRAVEL_GROUP",
}


@dataclass
class EvidenceItem:
    id: str
    category: str          # METADATA | REGISTRATION | JPEG | ELA | NOISE | DCT | ...
    detector: str
    version: str
    status: str            # SUPPORTING | NEUTRAL | CONTRADICTING | UNAVAILABLE
    score: Optional[float] = None
    reliability: Optional[float] = None
    description: str = ""
    raw_result: Optional[dict] = None
    evidence_group: Optional[str] = None
    execution_ms: Optional[int] = None
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _mk(category: str, detector: str, version: str,
        status: str, score: Optional[float],
        description: str, raw: Optional[dict] = None,
        execution_ms: Optional[int] = None,
        warnings: Optional[list] = None) -> EvidenceItem:
    return EvidenceItem(
        id=str(uuid.uuid4()),
        category=category,
        detector=detector,
        version=version,
        status=status,
        score=score,
        description=description,
        raw_result=raw,
        evidence_group=EVIDENCE_GROUPS.get(category),
        execution_ms=execution_ms,
        warnings=warnings or [],
    )


def normalize_all(all_results: dict) -> list[EvidenceItem]:
    """
    Convert all detector results into EvidenceItem list.

    all_results keys (all optional):
      metadata, registration, crop, ai, travel,
      ela, noise, dct, double_compression, resampling, jpeg_grid, copy_move
    """
    items: list[EvidenceItem] = []

    # ---- Metadata ----
    meta = all_results.get("metadata")
    if meta:
        items.append(_mk("METADATA", "metadata_inspector", "1.0.0",
            "NEUTRAL",  # metadata alone is evidence, not verdict
            None,
            f"Metadata extraction: c2pa={meta.get('c2pa_status', 'ABSENT')}, "
            f"software={meta.get('software') or 'unknown'}, "
            f"hasGps={meta.get('has_gps', False)}",
            raw=meta,
        ))

    # ---- Registration ----
    reg = all_results.get("registration")
    if reg:
        reg_status = reg.get("status")
        inlier_ratio = reg.get("inlier_ratio", 0)
        if reg_status == "COMPLETED" and inlier_ratio > 0.5:
            status = "NEUTRAL"
        elif reg_status in ("NO_MATCH",):
            status = "CONTRADICTING"
        else:
            status = "UNAVAILABLE"
        items.append(_mk("REGISTRATION", "registration", "1.0.0",
            status, inlier_ratio,
            f"Registration {reg_status}: inliers={reg.get('inlier_count')}, "
            f"ratio={inlier_ratio:.3f}, reproj_err={reg.get('reprojection_error')}",
            raw=reg,
        ))

    # ---- Crop ----
    crop = all_results.get("crop")
    if crop:
        crop_status = crop.get("status")
        pct = crop.get("crop_percentage")
        if crop_status == "DETECTED" and pct and pct > 2.0:
            status = "SUPPORTING"
            desc = f"Crop detected: {pct:.2f}% of original removed"
        elif crop_status == "NO_CROP":
            status = "NEUTRAL"
            desc = "No significant crop detected"
        else:
            status = "UNAVAILABLE"
            desc = f"Crop: {crop_status}"
        items.append(_mk("CROP", "crop_detector", "1.0.0",
            status, pct,
            desc, raw=crop,
        ))

    # ---- AI Detection ----
    ai = all_results.get("ai")
    if ai:
        ai_status = ai.get("status")
        score = ai.get("image_level_score")
        if ai_status == "UNAVAILABLE":
            status = "UNAVAILABLE"
            desc = "AI detection unavailable (model not trained)"
        elif ai_status == "AI_GENERATED":
            status = "SUPPORTING"
            desc = f"AI-generated evidence (global score {score:.3f}, UNCALIBRATED)"
        elif ai_status == "AI_EDITED_LOCAL":
            status = "SUPPORTING"
            n_regions = len(ai.get("regions") or [])
            desc = f"AI-like localized evidence in {n_regions} region(s) (UNCALIBRATED)"
        elif ai_status == "NO_AI_EVIDENCE":
            status = "NEUTRAL"
            desc = "No significant AI-like evidence (UNCALIBRATED)"
        else:
            status = "UNAVAILABLE"
            desc = f"AI: {ai_status}"
        items.append(_mk("AI", "ai_detector", "v1.0.0",
            status, score,
            desc, raw=ai,
            warnings=["UNCALIBRATED — requires trained model weights"],
        ))

    # ---- Travel analysis ----
    travel = all_results.get("travel")
    if travel:
        travel_status = travel.get("status")
        transforms = travel.get("transformations", [])
        if travel_status == "CONTENT_CHANGED":
            status = "SUPPORTING"
        elif travel_status == "TRANSFORMED_COPY":
            status = "NEUTRAL"
        elif travel_status == "NO_SIGNIFICANT_CHANGE":
            status = "NEUTRAL"
        else:
            status = "UNAVAILABLE"
        items.append(_mk("TRAVEL", "travel_analyzer", "1.0.0",
            status, None,
            f"Travel analysis: {travel_status} | transforms={transforms}",
            raw=travel,
        ))

    # ---- Classical detectors ----
    def _classical(key: str, cat: str, detector: str, version: str,
                   threshold: float = 0.1, invert: bool = False):
        result = all_results.get(key)
        if not result:
            return
        d_status = result.get("status") if isinstance(result, dict) else result.details.get("status") if hasattr(result, 'details') else None
        score = result.get("score") if isinstance(result, dict) else getattr(result, 'score', None)
        if d_status in ("NOT_APPLICABLE", "FAILED", None):
            stat = "UNAVAILABLE"
            desc = f"{cat}: {d_status or 'no result'}"
        else:
            val = (score or 0)
            if invert:
                val = 1 - val
            if val > threshold:
                stat = "SUPPORTING"
                desc = f"{cat}: score={score:.4f} (above threshold {threshold})"
            else:
                stat = "NEUTRAL"
                desc = f"{cat}: score={score:.4f} (below threshold)"
        items.append(_mk(cat, detector, version, stat, score, desc, raw=result))

    _classical("ela", "ELA", "ela", "1.0.0", threshold=0.12)
    _classical("noise", "NOISE", "noise_residual", "1.0.0", threshold=0.15)
    _classical("dct", "DCT", "dct_analysis", "1.0.0", threshold=0.3)
    _classical("double_compression", "JPEG_DOUBLE_COMPRESSION", "jpeg_double_compression", "1.0.0", threshold=0.06)
    _classical("resampling", "RESAMPLING", "resampling", "1.0.0", threshold=0.15)
    _classical("jpeg_grid", "DCT", "jpeg_grid", "1.0.0", threshold=0.1)
    _classical("copy_move", "COPY_MOVE", "copy_move", "1.0.0", threshold=0.01)

    return items
