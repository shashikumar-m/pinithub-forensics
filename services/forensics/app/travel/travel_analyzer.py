"""
Travelled-Copy Analysis Pipeline — Phase 7.

Orchestrates all existing detectors to analyze a suspect copy against
the protected original:

  1. File/metadata analysis (Phase 2)
  2. Reference registration (Phase 4)
  3. Transport transformation detection (JPEG, resize, screenshot)
  4. Crop analysis (Phase 5)
  5. Classical forensic detectors (Phase 3)
  6. AI detection (Phase 6)
  7. Metadata comparison
  8. Change classification and region extraction
  9. Investigation result assembly

CRITICAL:
  Transport-only transformations (compression, resize, metadata strip)
  are NOT automatically classified as malicious content edits.

Version: 1.0.0
"""
from __future__ import annotations

import io
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image as PILImage

from app.detectors.registration import get_registration_detector
from app.detectors.crop_detector import get_crop_detector
from app.detectors.ela import get_ela_detector
from app.detectors.noise_residual import get_noise_residual_detector
from app.detectors.dct_analysis import get_dct_analysis_detector
from app.detectors.jpeg_double_compression import get_jpeg_double_compression_detector
from app.detectors.ai_detector import get_ai_detector
from app.io.preprocessing import preprocess

logger = logging.getLogger(__name__)

ANALYZER_VERSION = "1.0.0"


@dataclass
class MetadataChange:
    field: str
    status: str       # UNCHANGED | REMOVED | MODIFIED | ADDED | UNAVAILABLE
    original_value: Optional[str] = None
    returned_value: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class TravelChangeRegion:
    type: str         # OBJECT_ADDED | OBJECT_REMOVED | LOCAL_CONTENT_CHANGE | AI_EDIT | TEXT_ADDED | STICKER_ADDED
    bbox: dict        # {x, y, width, height}
    polygon: Optional[list] = None
    area_pixels: Optional[int] = None
    area_percentage: Optional[float] = None
    evidence: list = field(default_factory=list)
    reliability: Optional[str] = None
    detector: Optional[str] = None
    detector_version: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class InvestigationResult:
    status: str                    # NO_SIGNIFICANT_CHANGE | TRANSFORMED_COPY | CONTENT_CHANGED | AI_CHANGE_DETECTED | NO_MATCH | INCONCLUSIVE
    transformations: list          # list of detected TravelTransformation strings
    changes: list                  # list of TravelChangeRegion
    metadata_changes: list         # list of MetadataChange
    crop: Optional[dict] = None
    ai_detection: Optional[dict] = None
    registration_quality: Optional[dict] = None
    evidence: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    execution_ms: int = 0
    version: str = ANALYZER_VERSION

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "transformations": self.transformations,
            "changes": [c.to_dict() if isinstance(c, TravelChangeRegion) else c
                        for c in self.changes],
            "metadata_changes": [m.to_dict() if isinstance(m, MetadataChange) else m
                                   for m in self.metadata_changes],
            "crop": self.crop,
            "ai_detection": self.ai_detection,
            "registration_quality": self.registration_quality,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "execution_ms": self.execution_ms,
            "version": self.version,
        }


def analyze_travelled_copy(
    reference_bytes: bytes,
    suspect_bytes: bytes,
    reference_metadata: Optional[dict] = None,
    suspect_metadata: Optional[dict] = None,
) -> InvestigationResult:
    """
    Main travel analysis pipeline.

    Reuses all existing detectors. Never duplicates detection logic.
    Clearly separates transport transformations from content changes.
    """
    start = time.perf_counter()
    transformations = []
    changes: list[TravelChangeRegion] = []
    metadata_changes: list[MetadataChange] = []
    evidence = []
    warnings = []

    # ---- 1. File-level dimension comparison ----
    try:
        ref_pre = preprocess(reference_bytes, max_dimension=2048)
        sus_pre = preprocess(suspect_bytes, max_dimension=2048)
        ref_w, ref_h = ref_pre.original_width, ref_pre.original_height
        sus_w, sus_h = sus_pre.original_width, sus_pre.original_height

        if ref_w != sus_w or ref_h != sus_h:
            scale_x = sus_w / ref_w if ref_w > 0 else 1.0
            scale_y = sus_h / ref_h if ref_h > 0 else 1.0
            avg_scale = (scale_x + scale_y) / 2

            evidence.append(
                f"Dimension change: {ref_w}x{ref_h} → {sus_w}x{sus_h} "
                f"(estimated scale: {avg_scale:.2f})"
            )
            # Dimension-only change is TRANSPORT, not content modification
            transformations.append("RESIZE")
    except Exception as e:
        warnings.append(f"Dimension comparison failed: {e}")

    # ---- 2. Registration (Phase 4) ----
    reg_quality = None
    homography = None
    try:
        reg_det = get_registration_detector()
        reg_result = reg_det.register(reference_bytes, suspect_bytes)
        reg_quality = {
            "status": reg_result.status,
            "inlier_count": reg_result.inlier_count,
            "inlier_ratio": round(reg_result.inlier_ratio, 4),
            "reprojection_error": round(reg_result.reprojection_error, 4) if reg_result.reprojection_error else None,
            "good_matches": reg_result.good_matches,
            "overlap_ratio": round(reg_result.overlap_ratio, 4) if reg_result.overlap_ratio else None,
        }
        if reg_result.status == "COMPLETED":
            homography = reg_result.homography_matrix
            evidence.append(
                f"Registration: COMPLETED | inliers={reg_result.inlier_count} "
                f"ratio={reg_result.inlier_ratio:.3f}"
            )
        elif reg_result.status == "NO_MATCH":
            return InvestigationResult(
                status="NO_MATCH",
                transformations=[], changes=[], metadata_changes=[],
                registration_quality=reg_quality,
                evidence=["Images do not match — cannot perform travel analysis."],
                warnings=warnings,
                execution_ms=int((time.perf_counter() - start) * 1000),
            )
        else:
            evidence.append(f"Registration: {reg_result.status}")
            warnings.extend(reg_result.warnings)
    except Exception as e:
        warnings.append(f"Registration failed: {e}")

    # ---- 3. JPEG / double-compression detection (Phase 3) ----
    try:
        dct_det = get_dct_analysis_detector()
        dct_result = dct_det.run("", image_bytes=suspect_bytes)
        if dct_result.details.get("status") == "COMPLETED":
            evidence.append(
                f"DCT analysis: DC energy ratio={dct_result.score:.4f}"
            )

        double_det = get_jpeg_double_compression_detector()
        double_result = double_det.run("", image_bytes=suspect_bytes)
        d_status = double_result.details.get("status")
        if d_status == "COMPLETED":
            d_score = double_result.score or 0.0
            d_gaps = double_result.details.get("evidence", {}).get("total_gaps", 0)
            evidence.append(
                f"JPEG double-compression evidence: gap_indicator={d_score:.4f} "
                f"(gaps={d_gaps})"
            )
            if d_score > 0.05:
                if "JPEG_RECOMPRESSION" not in transformations:
                    transformations.append("JPEG_RECOMPRESSION")
                evidence.append(
                    "JPEG recompression characteristics detected — consistent with lossy re-encoding."
                )
        elif d_status == "NOT_APPLICABLE":
            evidence.append("Suspect image is not JPEG — double-compression N/A.")
    except Exception as e:
        warnings.append(f"JPEG analysis failed: {e}")

    # ---- 4. Resampling evidence (Phase 3) ----
    try:
        from app.detectors.resampling import get_resampling_detector
        resamp_det = get_resampling_detector()
        resamp_result = resamp_det.run("", image_bytes=suspect_bytes)
        if resamp_result.details.get("status") == "COMPLETED":
            score = resamp_result.score or 0.0
            if score > 0.15:
                evidence.append(f"Resampling evidence: periodicity={score:.4f}")
                if "RESIZE" not in transformations:
                    transformations.append("RESIZE")
    except Exception as e:
        warnings.append(f"Resampling detection failed: {e}")

    # ---- 5. Screenshot detection ----
    screenshot_evidence = _detect_screenshot(suspect_bytes, sus_pre if 'sus_pre' in dir() else None)
    if screenshot_evidence["likely"]:
        transformations.append("SCREENSHOT")
        evidence.extend(screenshot_evidence["evidence"])
    else:
        evidence.append(f"Screenshot likelihood: {screenshot_evidence['label']}")

    # ---- 6. Metadata comparison ----
    if reference_metadata and suspect_metadata:
        metadata_changes = _compare_metadata(reference_metadata, suspect_metadata)
        stripped_fields = [m.field for m in metadata_changes if m.status == "REMOVED"]
        if stripped_fields:
            transformations.append("METADATA_CHANGE")
            evidence.append(f"Metadata removed/changed: {stripped_fields}")

    # ---- 7. ELA (Phase 3) ----
    ela_evidence = []
    try:
        ela_det = get_ela_detector()
        ela_result = ela_det.run("", image_bytes=suspect_bytes)
        if ela_result.details.get("status") == "COMPLETED":
            ela_score = ela_result.score or 0.0
            ela_evidence.append(
                f"ELA recompression error: {ela_score:.4f} (higher = more recompression)"
            )
            evidence.extend(ela_evidence)
    except Exception as e:
        warnings.append(f"ELA failed: {e}")

    # ---- 8. Crop analysis (Phase 5) ----
    crop_result_dict = None
    if homography:
        try:
            crop_det = get_crop_detector()
            crop_result = crop_det.run("",
                reference_bytes=reference_bytes,
                suspect_bytes=suspect_bytes,
                homography=homography,
            )
            d = crop_result.details
            if d.get("status") == "DETECTED":
                pct = float(d.get("crop_percentage") or 0.0)
                # Only flag CROP if meaningful (>2%) — sub-2% is likely registration error noise
                if pct > 2.0:
                    transformations.append("CROP")
                    evidence.append(f"Crop detected: {pct:.2f}% of original removed.")
                else:
                    evidence.append(
                        f"Near-zero crop ({pct:.2f}%) — within registration error tolerance, not classified as crop."
                    )
            crop_result_dict = d
        except Exception as e:
            warnings.append(f"Crop analysis failed: {e}")

    # ---- 9. AI detection (Phase 6) ----
    ai_result_dict = None
    try:
        ai_det = get_ai_detector()
        ai_result = ai_det.run("", image_bytes=suspect_bytes)
        d = ai_result.details
        ai_result_dict = d
        ai_status = d.get("status")

        if ai_status == "AI_GENERATED":
            transformations.append("AI_GENERATED")
            evidence.append(
                "AI detection: whole-image AI-like evidence detected (UNCALIBRATED)."
            )
        elif ai_status == "AI_EDITED_LOCAL":
            transformations.append("AI_EDIT")
            regions = d.get("regions", [])
            evidence.append(
                f"AI detection: localized AI-like evidence in {len(regions)} region(s) (UNCALIBRATED)."
            )
            for r in regions:
                changes.append(TravelChangeRegion(
                    type="AI_EDIT",
                    bbox=r.get("bbox", {}),
                    polygon=r.get("polygon"),
                    area_pixels=r.get("area_pixels"),
                    area_percentage=r.get("area_percentage"),
                    evidence=[f"AI detector confidence: {r.get('confidence', 'N/A')} (UNCALIBRATED)"],
                    reliability="UNCALIBRATED",
                    detector="ai_detector",
                    detector_version="v1.0.0",
                ))
        elif ai_status == "UNAVAILABLE":
            warnings.append("AI detection UNAVAILABLE — model weights not loaded.")
    except Exception as e:
        warnings.append(f"AI detection failed: {e}")

    # ---- 10. Determine overall status ----
    content_change_types = {"CROP", "AI_EDIT", "AI_GENERATED", "TEXT_ADDED",
                              "STICKER_ADDED", "OBJECT_ADDED", "OBJECT_REMOVED"}
    transport_only_types = {"JPEG_RECOMPRESSION", "RESIZE", "METADATA_CHANGE",
                              "SCREENSHOT", "COLOR_CHANGE", "FILTER", "ROTATION", "BRIGHTNESS", "CONTRAST"}

    detected_set = set(transformations)
    has_content = bool(detected_set & content_change_types)
    has_transport = bool(detected_set & transport_only_types)

    if not detected_set:
        status = "NO_SIGNIFICANT_CHANGE"
    elif has_content and ("AI_EDIT" in detected_set or "AI_GENERATED" in detected_set):
        status = "AI_CHANGE_DETECTED"
    elif has_content:
        status = "CONTENT_CHANGED"
    elif has_transport:
        status = "TRANSFORMED_COPY"
    else:
        status = "INCONCLUSIVE"

    return InvestigationResult(
        status=status,
        transformations=list(set(transformations)),
        changes=changes,
        metadata_changes=metadata_changes,
        crop=crop_result_dict,
        ai_detection=ai_result_dict,
        registration_quality=reg_quality,
        evidence=evidence,
        warnings=warnings,
        execution_ms=int((time.perf_counter() - start) * 1000),
    )


def _detect_screenshot(image_bytes: bytes, pre=None) -> dict:
    """
    Multi-signal screenshot detection.
    Returns {likely: bool, label: str, evidence: list}.

    Does NOT classify as screenshot solely on missing EXIF.
    """
    evidence = []
    signals = 0

    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        w, h = img.size

        # Signal 1: Common screen aspect ratios
        common_screen_ratios = [
            (16, 9), (9, 16), (16, 10), (4, 3), (3, 4),
            (2, 1), (1, 2), (19.5, 9), (9, 19.5),
        ]
        ar = w / h if h > 0 else 0
        for rw, rh in common_screen_ratios:
            if abs(ar - rw / rh) < 0.02:
                evidence.append(f"Screen-like aspect ratio: {w}:{h}")
                signals += 1
                break

        # Signal 2: Very common mobile resolutions
        screen_dims = [(1080, 1920), (1080, 2340), (1080, 2400),
                        (720, 1280), (1440, 2560), (1170, 2532),
                        (828, 1792)]
        if (w, h) in screen_dims or (h, w) in screen_dims:
            evidence.append(f"Common screen resolution: {w}x{h}")
            signals += 1

        # Signal 3: PNG format (common for screenshots)
        if img.format == "PNG":
            evidence.append("PNG format — consistent with screenshot encoding")
            signals += 0.5  # weak signal alone

    except Exception as e:
        evidence.append(f"Screenshot detection warning: {e}")

    likely = signals >= 1.5
    label = "SCREENSHOT_LIKELY" if likely else "SCREENSHOT_INCONCLUSIVE"
    return {"likely": likely, "label": label, "evidence": evidence}


def _compare_metadata(
    reference: dict,
    suspect: dict,
) -> list[MetadataChange]:
    """Compare reference and suspect metadata."""
    changes = []
    # Compare key fields
    fields = [
        "cameraMake", "cameraModel", "lensMake", "lensModel",
        "software", "orientation", "colorSpace", "colorProfile",
        "capturedAt", "hasGps", "iso", "aperture",
    ]
    for f in fields:
        ref_val = reference.get(f)
        sus_val = suspect.get(f)
        if ref_val == sus_val:
            status = "UNCHANGED"
        elif ref_val is not None and sus_val is None:
            status = "REMOVED"
        elif ref_val is None and sus_val is not None:
            status = "ADDED"
        else:
            status = "MODIFIED"
        if status != "UNCHANGED":
            changes.append(MetadataChange(
                field=f, status=status,
                original_value=str(ref_val) if ref_val is not None else None,
                returned_value=str(sus_val) if sus_val is not None else None,
            ))
    return changes
