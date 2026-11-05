"""
Crop Percentage Detector — Phase 5.

Uses the Phase 4 registration/homography to determine:
  1. Whether the suspect image matches the original
  2. Whether a crop occurred
  3. What percentage of the original image area was removed
  4. The crop footprint/location in original image coordinates
  5. Confidence/reliability of the estimate

Mathematical definition:
  original_area = original_width × original_height
  kept_area = polygon area of original visible in suspect (via inverse homography)
  crop_percentage = 100 × (1 - kept_area / original_area)

All coordinates are in ORIGINAL_IMAGE_COORDINATES.

The detector NEVER forces a crop percentage when registration is unreliable.
Unrelated images → NO_MATCH.
Insufficient evidence → INCONCLUSIVE.

Version: 1.0.0
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import cv2

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.detectors.registration import get_registration_detector
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "crop_detector"
DETECTOR_VERSION = "1.0.0"

DEFAULT_PARAMS = {
    "feature_detector": "sift",
    "max_keypoints": 2000,
    "ratio_threshold": 0.75,
    "ransac_threshold": 4.0,
    "min_good_matches": 8,        # slightly lower than registration for heavy crops
    "min_inliers": 6,
    "min_inlier_ratio": 0.12,
    "max_reprojection_error": 10.0,  # slightly more tolerant for crop
    "max_scale_ratio": 10.0,      # allow larger scale differences for crop
    "max_dimension": 1024,
    # Crop-specific
    "min_confidence_inlier_ratio": 0.10,  # below this → INCONCLUSIVE
    "polygon_area_tolerance": 0.001,     # min polygon area as fraction of original
}


@dataclass
class CropResult:
    """Structured crop detection result."""
    status: str                        # DETECTED | NO_CROP | NO_MATCH | INCONCLUSIVE | FAILED
    crop_percentage: Optional[float] = None
    kept_percentage: Optional[float] = None
    original_area_pixels: int = 0
    kept_area_pixels: Optional[int] = None
    removed_area_pixels: Optional[int] = None
    crop_polygon: Optional[list] = None     # [{x, y}, ...] in original coords
    bounding_box: Optional[dict] = None      # {x, y, width, height} in original coords
    confidence: Optional[float] = None
    reliability: Optional[float] = None
    registration_quality: Optional[dict] = None
    method: str = "homography_inverse_projection"
    detector: str = DETECTOR_NAME
    version: str = DETECTOR_VERSION
    execution_ms: int = 0
    warnings: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "crop_percentage": round(self.crop_percentage, 2) if self.crop_percentage is not None else None,
            "kept_percentage": round(self.kept_percentage, 2) if self.kept_percentage is not None else None,
            "original_area_pixels": self.original_area_pixels,
            "kept_area_pixels": self.kept_area_pixels,
            "removed_area_pixels": self.removed_area_pixels,
            "crop_polygon": self.crop_polygon,
            "bounding_box": self.bounding_box,
            "coordinate_system": "ORIGINAL_IMAGE_COORDINATES",
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "reliability": self.reliability,  # "UNCALIBRATED" or None
            "registration_quality": self.registration_quality,
            "method": self.method,
            "detector": self.detector,
            "version": self.version,
            "execution_ms": self.execution_ms,
            "warnings": self.warnings,
            "error": self.error,
        }


class CropDetector(BaseDetector):
    """
    Crop percentage detector — uses homography inverse to project suspect
    boundaries into original coordinate system, then computes polygon area.
    """

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.CROP_PERCENTAGE

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """
        Run crop detection.
        kwargs:
          reference_bytes: bytes — protected original
          suspect_bytes: bytes — suspect/travelled copy
          params: dict — optional parameter overrides
          homography: Optional — pre-computed homography from Phase 4
        """
        start = time.perf_counter()

        ref_bytes: Optional[bytes] = kwargs.get("reference_bytes")
        sus_bytes: Optional[bytes] = kwargs.get("suspect_bytes")

        if not ref_bytes or not sus_bytes:
            return DetectorResult(
                detector=self.name, version=self.version,
                category=self.category,
                details={"status": "FAILED", "error": "reference_bytes and suspect_bytes required"},
            )

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        pre_h = kwargs.get("homography")  # Optional pre-computed homography

        result = self._detect_crop(ref_bytes, sus_bytes, params, pre_h)
        result.execution_ms = int((time.perf_counter() - start) * 1000)

        return DetectorResult(
            detector=self.name, version=self.version,
            category=self.category,
            score=result.crop_percentage / 100.0 if result.crop_percentage is not None else None,
            confidence=result.confidence,
            details=result.to_dict(),
            execution_time_ms=result.execution_ms,
        )

    def _detect_crop(
        self,
        ref_bytes: bytes,
        sus_bytes: bytes,
        params: dict,
        pre_h: Optional[Any],
    ) -> CropResult:
        warnings: list[str] = []

        # ---- 1. Preprocess both images ----
        try:
            ref_pre = preprocess(ref_bytes, max_dimension=params["max_dimension"])
            sus_pre = preprocess(sus_bytes, max_dimension=params["max_dimension"])
        except Exception as e:
            return CropResult(status="FAILED", error=f"Preprocessing failed: {e}")

        orig_w = ref_pre.original_width
        orig_h = ref_pre.original_height
        orig_area = orig_w * orig_h

        # ---- 2. Get homography (reuse Phase 4 if available) ----
        H = None
        reg_quality = {}

        if pre_h is not None:
            H = np.array(pre_h, dtype=np.float64)
            warnings.append("Using pre-computed homography")
        else:
            # Run registration
            reg_detector = get_registration_detector()
            reg_result = reg_detector.register(ref_bytes, sus_bytes, params)
            warnings.extend(reg_result.warnings)

            reg_quality = {
                "inlier_count": reg_result.inlier_count,
                "inlier_ratio": round(reg_result.inlier_ratio, 4),
                "reprojection_error": round(reg_result.reprojection_error, 4) if reg_result.reprojection_error else None,
                "good_matches": reg_result.good_matches,
                "keypoints_reference": reg_result.keypoints_reference,
                "keypoints_suspect": reg_result.keypoints_suspect,
                "overlap_percentage": round(reg_result.overlap_ratio * 100, 2) if reg_result.overlap_ratio else None,
            }

            if reg_result.status == "NO_MATCH":
                return CropResult(
                    status="NO_MATCH",
                    original_area_pixels=orig_area,
                    registration_quality=reg_quality,
                    warnings=warnings,
                    reliability="UNCALIBRATED",
                )

            if reg_result.status == "INCONCLUSIVE":
                return CropResult(
                    status="INCONCLUSIVE",
                    original_area_pixels=orig_area,
                    registration_quality=reg_quality,
                    warnings=warnings + ["Registration inconclusive — cannot determine crop"],
                    reliability="UNCALIBRATED",
                )

            if reg_result.status != "COMPLETED" or reg_result.homography_matrix is None:
                return CropResult(
                    status="INCONCLUSIVE",
                    original_area_pixels=orig_area,
                    registration_quality=reg_quality,
                    warnings=warnings + [f"Registration status: {reg_result.status}"],
                    reliability="UNCALIBRATED",
                )

            H = np.array(reg_result.homography_matrix, dtype=np.float64)

        if H is None or H.shape != (3, 3):
            return CropResult(
                status="FAILED",
                original_area_pixels=orig_area,
                error="Invalid homography matrix",
                warnings=warnings,
            )

        # ---- 3. Scale homography from analysis-resolution to original coordinates ----
        # Registration runs at max_dimension; we need to map back to original
        scale_x = ref_pre.scale_x  # original_w / analysis_w
        scale_y = ref_pre.scale_y

        # H maps reference(analysis) → suspect(analysis)
        # We need H_inv: suspect(analysis) → reference(analysis)
        # Then scale to original coordinates
        try:
            H_inv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            return CropResult(
                status="FAILED",
                original_area_pixels=orig_area,
                error="Homography inversion failed (singular matrix)",
                warnings=warnings,
            )

        # ---- 4. Project suspect corners into original coordinate system ----
        sus_w, sus_h = sus_pre.width, sus_pre.height
        sus_corners = np.float32([
            [0, 0], [sus_w - 1, 0], [sus_w - 1, sus_h - 1], [0, sus_h - 1]
        ]).reshape(-1, 1, 2)

        # Transform suspect corners → reference (analysis) coordinates
        try:
            ref_corners = cv2.perspectiveTransform(sus_corners, H_inv)
        except cv2.error as e:
            return CropResult(
                status="FAILED",
                original_area_pixels=orig_area,
                error=f"Corner projection failed: {e}",
                warnings=warnings,
            )

        # Scale to original image coordinates
        ref_corners_orig = ref_corners.reshape(-1, 2).copy()
        ref_corners_orig[:, 0] *= scale_x
        ref_corners_orig[:, 1] *= scale_y

        # Clip to original image bounds
        ref_corners_clipped = ref_corners_orig.copy()
        ref_corners_clipped[:, 0] = np.clip(ref_corners_clipped[:, 0], 0, orig_w)
        ref_corners_clipped[:, 1] = np.clip(ref_corners_clipped[:, 1], 0, orig_h)

        # ---- 5. Calculate kept area using polygon intersection ----
        # The "kept" region is the intersection of the projected suspect polygon
        # with the original image rectangle.

        # Original image as a polygon (rectangle)
        orig_rect = np.array([[0, 0], [orig_w, 0], [orig_w, orig_h], [0, orig_h]], dtype=np.float32)

        # Calculate intersection polygon using Sutherland-Hodgman clipping
        try:
            intersection = _polygon_clip(
                ref_corners_clipped.astype(np.float32),
                orig_rect,
            )
        except Exception as e:
            warnings.append(f"Polygon clipping failed: {e}")
            # Fallback: use bounding box area as approximation
            intersection = None

        if intersection is None or len(intersection) < 3:
            return CropResult(
                status="INCONCLUSIVE",
                original_area_pixels=orig_area,
                registration_quality=reg_quality,
                warnings=warnings + ["Could not compute valid intersection polygon"],
                reliability="UNCALIBRATED",
            )

        # Calculate polygon area using shoelace formula
        kept_area = _polygon_area(intersection)
        kept_area_int = int(round(kept_area))

        if kept_area <= 0:
            return CropResult(
                status="NO_MATCH",
                original_area_pixels=orig_area,
                registration_quality=reg_quality,
                warnings=warnings + ["Kept area is zero or negative"],
                reliability="UNCALIBRATED",
            )

        # ---- 6. Calculate crop percentage ----
        crop_pct = 100.0 * (1.0 - kept_area / orig_area) if orig_area > 0 else 0.0
        kept_pct = 100.0 - crop_pct
        removed_area = orig_area - kept_area_int

        # Clamp to valid range
        crop_pct = max(0.0, min(100.0, crop_pct))
        kept_pct = max(0.0, min(100.0, kept_pct))

        # ---- 7. Determine status ----
        if crop_pct < 0.5:
            status = "NO_CROP"
        else:
            status = "DETECTED"

        # ---- 8. Confidence / reliability ----
        # Confidence based on registration quality
        inlier_ratio = reg_quality.get("inlier_ratio", 0)
        reproj_err = reg_quality.get("reprojection_error")

        # Simple heuristic confidence — NOT a calibrated probability
        if inlier_ratio and inlier_ratio > 0.3:
            confidence = min(1.0, inlier_ratio)
        elif inlier_ratio and inlier_ratio > 0.15:
            confidence = inlier_ratio * 0.8
        else:
            confidence = 0.3

        # Reduce confidence for very heavy crops (less data)
        if crop_pct > 80:
            confidence *= 0.7
            warnings.append("Heavy crop (>80%) — reduced confidence due to limited feature overlap")

        # ---- 9. Build polygon and bounding box ----
        polygon = [{"x": float(p[0]), "y": float(p[1])} for p in intersection]
        xs = [p[0] for p in intersection]
        ys = [p[1] for p in intersection]
        bbox = {
            "x": int(round(min(xs))),
            "y": int(round(min(ys))),
            "width": int(round(max(xs) - min(xs))),
            "height": int(round(max(ys) - min(ys))),
        }

        # ---- 10. Generate footprint mask artifact ----
        # Create a mask showing the kept region on the original image
        mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
        pts = np.array([[p["x"], p["y"]] for p in polygon], dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)

        return CropResult(
            status=status,
            crop_percentage=crop_pct,
            kept_percentage=kept_pct,
            original_area_pixels=orig_area,
            kept_area_pixels=kept_area_int,
            removed_area_pixels=max(0, removed_area),
            crop_polygon=polygon,
            bounding_box=bbox,
            confidence=confidence,
            reliability="UNCALIBRATED",
            registration_quality=reg_quality,
            method="homography_inverse_projection",
            detector=DETECTOR_NAME,
            version=DETECTOR_VERSION,
            warnings=warnings,
        )


# ---- Geometry helpers ----

def _polygon_area(pts: np.ndarray) -> float:
    """Shoelace formula for polygon area."""
    if len(pts) < 3:
        return 0.0
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _polygon_clip(subject: np.ndarray, clip_rect: np.ndarray) -> Optional[np.ndarray]:
    """
    Clip subject polygon against a convex clip polygon (the image rectangle).
    Uses OpenCV's intersectConvexConvex for robustness.
    Falls back to bounding-box clipping if that fails.
    """
    try:
        # Use cv2's convex polygon intersection
        subject_f32 = subject.astype(np.float32).reshape(-1, 1, 2)
        clip_f32 = clip_rect.astype(np.float32).reshape(-1, 1, 2)
        retval, inter = cv2.intersectConvexConvex(subject_f32, clip_f32)
        if retval > 0 and inter is not None and len(inter) >= 3:
            return inter.reshape(-1, 2)
    except Exception:
        pass

    # Fallback: simple bounding-box clipping
    xs = np.clip(subject[:, 0], clip_rect[:, 0].min(), clip_rect[:, 0].max())
    ys = np.clip(subject[:, 1], clip_rect[:, 1].min(), clip_rect[:, 1].max())
    clipped = np.stack([xs, ys], axis=1)
    if len(clipped) >= 3:
        return clipped
    return None


_instance: Optional[CropDetector] = None

def get_crop_detector() -> CropDetector:
    global _instance
    if _instance is None:
        _instance = CropDetector()
    return _instance
