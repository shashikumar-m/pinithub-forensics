"""
Region Fusion — Phase 8.

Merges spatial evidence from multiple detectors into FinalRegion list.
Uses IoU-based overlap detection to group related detections.
All coordinates in ORIGINAL_IMAGE_COORDINATES.

Preserves detector provenance — never silently discards evidence.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class FinalRegion:
    id: str
    type: str            # CROP | AI_EDIT | OBJECT_ADDED | OBJECT_REMOVED | RETOUCH | LOCAL_CHANGE | TEXT_ADDED | STICKER_ADDED | UNKNOWN
    bbox_x: int
    bbox_y: int
    bbox_width: int
    bbox_height: int
    polygon: Optional[list] = None
    area_pixels: int = 0
    area_percentage: float = 0.0
    confidence: Optional[float] = None
    evidence_count: int = 1
    source_detectors: list = field(default_factory=list)
    mask_artifact_path: Optional[str] = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v is not None}
        return d


def _iou(a: tuple, b: tuple) -> float:
    """IoU between two bboxes: (x, y, w, h)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(ax, bx); iy = max(ay, by)
    ix2 = min(ax + aw, bx + bw); iy2 = min(ay + ah, by + bh)
    if ix2 <= ix or iy2 <= iy:
        return 0.0
    inter = (ix2 - ix) * (iy2 - iy)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def fuse_regions(
    crop_result: Optional[dict],
    ai_result: Optional[dict],
    travel_changes: Optional[list],
    diff_regions: Optional[list],
    original_width: int,
    original_height: int,
) -> list[FinalRegion]:
    """
    Merge spatial evidence from multiple detectors.
    Returns list of FinalRegion in original image coordinates.
    """
    candidates: list[dict] = []
    orig_area = original_width * original_height

    # ---- Crop footprint ----
    if crop_result and crop_result.get("status") == "DETECTED":
        bbox = crop_result.get("bounding_box") or {}
        poly = crop_result.get("crop_polygon")
        kept_area = crop_result.get("kept_area_pixels") or 0
        removed_area = max(0, orig_area - kept_area)
        candidates.append({
            "type": "CROP",
            "bbox": (bbox.get("x", 0), bbox.get("y", 0),
                     bbox.get("width", original_width), bbox.get("height", original_height)),
            "polygon": poly,
            "area_pixels": removed_area,
            "area_percentage": round(float(crop_result.get("crop_percentage") or 0), 4),
            "confidence": crop_result.get("confidence"),
            "detector": "crop_detector",
        })

    # ---- AI localization regions ----
    if ai_result and ai_result.get("status") in ("AI_EDITED_LOCAL", "AI_GENERATED"):
        for r in (ai_result.get("regions") or []):
            b = r.get("bbox", {})
            candidates.append({
                "type": "AI_EDIT",
                "bbox": (b.get("x", 0), b.get("y", 0),
                         b.get("width", 0), b.get("height", 0)),
                "polygon": r.get("polygon"),
                "area_pixels": r.get("area_pixels") or 0,
                "area_percentage": round(r.get("area_percentage") or 0, 4),
                "confidence": r.get("confidence"),
                "detector": "ai_detector",
            })

    # ---- Travel change regions ----
    for c in (travel_changes or []):
        b = c.get("bbox", {})
        ctype = c.get("type", "LOCAL_CHANGE")
        candidates.append({
            "type": ctype,
            "bbox": (b.get("x", 0), b.get("y", 0),
                     b.get("width", 0), b.get("height", 0)),
            "polygon": c.get("polygon"),
            "area_pixels": c.get("area_pixels") or 0,
            "area_percentage": round(c.get("area_percentage") or 0, 4),
            "confidence": None,
            "detector": "travel_analyzer",
        })

    # ---- Difference regions ----
    for r in (diff_regions or []):
        b = r.get("bbox", {})
        candidates.append({
            "type": "LOCAL_CHANGE",
            "bbox": (b.get("x", 0), b.get("y", 0),
                     b.get("width", 0), b.get("height", 0)),
            "polygon": r.get("polygon"),
            "area_pixels": r.get("pixel_area") or 0,
            "area_percentage": round(r.get("area_percent") or 0, 4),
            "confidence": None,
            "detector": "difference_analysis",
        })

    if not candidates:
        return []

    # ---- IoU-based merging ----
    # Two detections with IoU > 0.3 are merged into the stronger one
    MERGE_THRESHOLD = 0.3
    merged: list[dict] = []
    used = [False] * len(candidates)

    for i, c in enumerate(candidates):
        if used[i]:
            continue
        group = [c]
        for j, d in enumerate(candidates):
            if j <= i or used[j]:
                continue
            if _iou(c["bbox"], d["bbox"]) >= MERGE_THRESHOLD:
                group.append(d)
                used[j] = True
        used[i] = True

        # Pick the representative bbox (largest area)
        rep = max(group, key=lambda r: r["area_pixels"])
        region_type = rep["type"]
        if any(g["type"] == "AI_EDIT" for g in group):
            region_type = "AI_EDIT"
        elif any(g["type"] == "CROP" for g in group):
            region_type = "CROP"

        merged.append({
            "type": region_type,
            "bbox": rep["bbox"],
            "polygon": rep.get("polygon"),
            "area_pixels": rep["area_pixels"],
            "area_percentage": rep["area_percentage"],
            "confidence": rep.get("confidence"),
            "evidence_count": len(group),
            "source_detectors": list({g["detector"] for g in group}),
        })

    # ---- Build FinalRegion list ----
    final: list[FinalRegion] = []
    for m in merged:
        x, y, w, h = m["bbox"]
        final.append(FinalRegion(
            id=str(uuid.uuid4()),
            type=m["type"],
            bbox_x=int(x), bbox_y=int(y),
            bbox_width=int(w), bbox_height=int(h),
            polygon=m.get("polygon"),
            area_pixels=int(m["area_pixels"]),
            area_percentage=float(m["area_percentage"]),
            confidence=m.get("confidence"),
            evidence_count=m["evidence_count"],
            source_detectors=m["source_detectors"],
        ))

    final.sort(key=lambda r: r.area_pixels, reverse=True)
    return final
