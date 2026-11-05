"""
Report Generator & Sealed Record — Phase 8.

Generates:
  1. Canonical JSON report (deterministic, stable field ordering)
  2. Simple plain-text / HTML PDF-like report
  3. SHA-256 tamper-evident seal

The JSON is the canonical source of truth.
The PDF is generated from it — they share the same data.

Tamper-evident: the seal is SHA-256(canonical_json).
Use terminology TAMPER_EVIDENT, not TAMPER_PROOF or blockchain.

Schema version: 1.0
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional


SCHEMA_VERSION = "1.0"
REPORT_VERSION = "1.0"


def build_canonical_report(
    investigation_id: str,
    verdict: str,
    confidence_status: str,
    evidence_strength: str,
    explanation: str,
    warnings: list[str],
    fusion_version: str,
    reference_image: Optional[dict],
    suspect_image: Optional[dict],
    registration: Optional[dict],
    metadata_changes: Optional[list],
    transformations: Optional[list],
    evidence_items: Optional[list],
    regions: Optional[list],
    crop: Optional[dict],
    ai_detection: Optional[dict],
    limitations: Optional[list],
    created_at: Optional[str] = None,
) -> dict:
    """
    Build a deterministic canonical JSON report.

    Requirements:
      - Stable field ordering (via sorted keys where applicable)
      - No random values
      - No signed-URL expiry timestamps
      - Explicit schema version
    """
    if created_at is None:
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "reportVersion": REPORT_VERSION,
        "investigationId": investigation_id,
        "createdAt": created_at,
        "verdict": verdict,
        "confidenceStatus": confidence_status,
        "evidenceStrength": evidence_strength,
        "explanation": explanation,
        "fusionVersion": fusion_version,
        "warnings": sorted(set(warnings)),  # deduplicated, stable order
        "originalImage": _normalize_image_info(reference_image),
        "suspectImage": _normalize_image_info(suspect_image),
        "registration": _normalize_registration(registration),
        "metadataChanges": sorted(metadata_changes or [], key=lambda x: x.get("field", "")),
        "transformations": sorted(set(transformations or [])),
        "evidenceItems": [_normalize_evidence(e) for e in (evidence_items or [])],
        "regions": [_normalize_region(r) for r in (regions or [])],
        "crop": _normalize_crop(crop),
        "aiDetection": _normalize_ai(ai_detection),
        "limitations": sorted(set(limitations or [])),
    }
    return report


def _normalize_image_info(img: Optional[dict]) -> Optional[dict]:
    if not img:
        return None
    return {
        "filename": img.get("originalFilename") or img.get("filename"),
        "mimeType": img.get("mimeType"),
        "format": img.get("format"),
        "sizeBytes": img.get("sizeBytes"),
        "width": img.get("width"),
        "height": img.get("height"),
        "sha256": img.get("sha256"),
    }


def _normalize_registration(reg: Optional[dict]) -> Optional[dict]:
    if not reg:
        return None
    return {
        "status": reg.get("status"),
        "method": reg.get("registrationMethod") or "SIFT",
        "keypointsReference": reg.get("keypointsReference"),
        "keypointsSuspect": reg.get("keypointsSuspect"),
        "goodMatches": reg.get("goodMatches"),
        "inlierCount": reg.get("inlierCount"),
        "inlierRatio": reg.get("inlierRatio"),
        "reprojectionError": reg.get("reprojectionError"),
        "overlapRatio": reg.get("overlapRatio"),
    }


def _normalize_evidence(e: Any) -> dict:
    if hasattr(e, "to_dict"):
        d = e.to_dict()
    elif isinstance(e, dict):
        d = e
    else:
        return {}
    # Stable field order — omit raw_result to keep report compact
    return {
        "id": d.get("id"),
        "category": d.get("category"),
        "detector": d.get("detector"),
        "version": d.get("version"),
        "status": d.get("status"),
        "score": round(d["score"], 6) if d.get("score") is not None else None,
        "description": d.get("description"),
        "evidenceGroup": d.get("evidence_group"),
        "executionMs": d.get("execution_ms"),
    }


def _normalize_region(r: Any) -> dict:
    if hasattr(r, "to_dict"):
        d = r.to_dict()
    elif isinstance(r, dict):
        d = r
    else:
        return {}
    return {
        "id": d.get("id"),
        "type": d.get("type"),
        "bbox": {
            "x": d.get("bbox_x") or d.get("bboxX", 0),
            "y": d.get("bbox_y") or d.get("bboxY", 0),
            "width": d.get("bbox_width") or d.get("bboxWidth", 0),
            "height": d.get("bbox_height") or d.get("bboxHeight", 0),
        },
        "areaPixels": d.get("area_pixels") or d.get("areaPixels", 0),
        "areaPercentage": d.get("area_percentage") or d.get("areaPercentage", 0),
        "confidence": d.get("confidence"),
        "evidenceCount": d.get("evidence_count") or d.get("evidenceCount", 1),
        "sourceDetectors": d.get("source_detectors") or d.get("sourceDetectors", []),
        "coordinateSystem": "ORIGINAL_IMAGE_COORDINATES",
    }


def _normalize_crop(crop: Optional[dict]) -> Optional[dict]:
    if not crop:
        return None
    return {
        "status": crop.get("status"),
        "cropPercentage": round(float(crop["crop_percentage"]), 4) if crop.get("crop_percentage") is not None else None,
        "keptPercentage": round(float(crop["kept_percentage"]), 4) if crop.get("kept_percentage") is not None else None,
        "originalAreaPixels": crop.get("original_area_pixels"),
        "keptAreaPixels": crop.get("kept_area_pixels"),
        "confidence": crop.get("confidence"),
        "reliability": crop.get("reliability"),
        "coordinateSystem": "ORIGINAL_IMAGE_COORDINATES",
    }


def _normalize_ai(ai: Optional[dict]) -> Optional[dict]:
    if not ai:
        return None
    return {
        "status": ai.get("status"),
        "imageLevelScore": round(float(ai["image_level_score"]), 6) if ai.get("image_level_score") is not None else None,
        "imageLevelLabel": ai.get("image_level_label"),
        "editedAreaPercentage": ai.get("edited_area_percentage"),
        "model": ai.get("model"),
        "version": ai.get("version"),
        "calibrationStatus": ai.get("calibration_status", "UNCALIBRATED"),
        "regionCount": len(ai.get("regions") or []),
    }


def canonical_json(report: dict) -> str:
    """Serialize to canonical JSON (sorted keys, no indentation variation)."""
    def _default(o):
        if isinstance(o, (float, int)):
            return o
        # numpy scalars
        if hasattr(o, 'item'):
            return o.item()
        raise TypeError(f'Object of type {type(o).__name__} is not JSON serializable')
    return json.dumps(report, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, default=_default)


def seal_report(report_json_str: str) -> dict:
    """
    Create a tamper-evident seal by hashing the canonical report.

    Returns a sealed record dict.
    TAMPER_EVIDENT: any change to the report bytes changes the hash.
    This is NOT blockchain. This is NOT legally binding unless additional
    infrastructure (timestamping authority, PKI) is added.
    """
    seal_hash = hashlib.sha256(report_json_str.encode("utf-8")).hexdigest()
    return {
        "sealedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schemaVersion": SCHEMA_VERSION,
        "reportHash": seal_hash,
        "algorithm": "SHA-256",
        "tamperEvident": True,
        "note": (
            "TAMPER_EVIDENT (not TAMPER_PROOF). "
            "SHA-256 of the canonical report JSON. "
            "Verify by re-hashing the report and comparing to reportHash."
        ),
    }


def generate_text_report(report: dict) -> str:
    """
    Generate a human-readable text report from the canonical JSON.
    Used as the basis for PDF generation.
    """
    lines = [
        "=" * 60,
        "PINITHUB FORENSICS — INVESTIGATION REPORT",
        f"Schema Version: {report.get('schemaVersion')}",
        f"Investigation ID: {report.get('investigationId')}",
        f"Generated: {report.get('createdAt')}",
        "=" * 60,
        "",
        "## VERDICT",
        f"  Verdict: {report.get('verdict')}",
        f"  Evidence Strength: {report.get('evidenceStrength')}",
        f"  Confidence Status: {report.get('confidenceStatus')}",
        f"  Explanation: {report.get('explanation')}",
        "",
        "## ORIGINAL IMAGE",
    ]
    orig = report.get("originalImage") or {}
    lines += [
        f"  Filename: {orig.get('filename', 'N/A')}",
        f"  Format: {orig.get('format', 'N/A')}",
        f"  Dimensions: {orig.get('width')}x{orig.get('height')}",
        f"  SHA-256: {orig.get('sha256', 'N/A')}",
        "",
        "## SUSPECT IMAGE",
    ]
    susp = report.get("suspectImage") or {}
    lines += [
        f"  Filename: {susp.get('filename', 'N/A')}",
        f"  Format: {susp.get('format', 'N/A')}",
        f"  Dimensions: {susp.get('width')}x{susp.get('height')}",
        f"  SHA-256: {susp.get('sha256', 'N/A')}",
        "",
        "## REGISTRATION",
    ]
    reg = report.get("registration") or {}
    lines += [
        f"  Status: {reg.get('status', 'N/A')}",
        f"  Inliers: {reg.get('inlierCount')} ({reg.get('inlierRatio')})",
        f"  Reprojection Error: {reg.get('reprojectionError')} px",
        "",
        "## DETECTED TRANSFORMATIONS",
    ]
    for t in report.get("transformations") or []:
        lines.append(f"  - {t}")
    lines += [
        "",
        "## METADATA CHANGES",
    ]
    for mc in report.get("metadataChanges") or []:
        lines.append(f"  {mc.get('field')}: {mc.get('status')}")
    lines += [
        "",
        "## CONTENT CHANGES",
    ]
    for region in report.get("regions") or []:
        bbox = region.get("bbox", {})
        lines.append(
            f"  [{region.get('type')}] {bbox.get('width')}x{bbox.get('height')} at "
            f"({bbox.get('x')},{bbox.get('y')}) — {region.get('areaPercentage'):.2f}% "
            f"[evidence count: {region.get('evidenceCount')}]"
        )
    crop = report.get("crop")
    if crop and crop.get("status") == "DETECTED":
        lines += ["", "## CROP", f"  {crop.get('cropPercentage')}% of original removed"]
    ai = report.get("aiDetection")
    if ai:
        lines += [
            "", "## AI DETECTION",
            f"  Status: {ai.get('status')}",
            f"  Calibration: {ai.get('calibrationStatus')}",
            f"  Regions: {ai.get('regionCount')}",
        ]
    lines += [
        "", "## EVIDENCE BREAKDOWN",
    ]
    for ev in report.get("evidenceItems") or []:
        lines.append(
            f"  [{ev.get('status')}] {ev.get('category')} — {ev.get('detector')} v{ev.get('version')}: "
            f"{ev.get('description', '')[:80]}"
        )
    lines += [
        "", "## LIMITATIONS",
    ]
    for lim in report.get("limitations") or []:
        lines.append(f"  - {lim}")
    lines += [
        "", "## WARNINGS",
    ]
    for w in report.get("warnings") or []:
        lines.append(f"  - {w}")
    lines += [
        "", "=" * 60,
        "END OF REPORT",
        "=" * 60,
    ]
    return "\n".join(lines)
