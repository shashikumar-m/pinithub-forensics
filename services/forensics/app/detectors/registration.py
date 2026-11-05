"""
Image Registration Detector — Phase 4.

Registers a suspect image against a protected original using:
  1. SIFT feature extraction (with ORB fallback)
  2. FLANN/BFMatcher descriptor matching with Lowe ratio test
  3. RANSAC homography estimation (cv2.findHomography)
  4. Multi-factor registration quality evaluation
  5. Image warping (cv2.warpPerspective) to original coordinate system
  6. Overlap mask calculation

Score semantics:
  inlier_ratio = consistent matches / good matches (0–1).
  NOT an authenticity probability.

Critical design rule:
  If registration is unreliable, status = INCONCLUSIVE or NO_MATCH.
  A failed registration must NEVER be converted into a forensic conclusion.

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
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "registration"
DETECTOR_VERSION = "1.0.0"

DEFAULT_PARAMS = {
    "feature_detector": "sift",       # "sift", "orb", "akaze"
    "max_keypoints": 2000,
    "ratio_threshold": 0.75,          # Lowe's ratio test
    "ransac_threshold": 4.0,          # reprojection error threshold (pixels)
    "min_good_matches": 10,
    "min_inliers": 8,
    "min_inlier_ratio": 0.15,
    "max_reprojection_error": 8.0,
    "max_scale_ratio": 5.0,           # reject extreme scale changes
    "max_dimension": 1024,
}

# Thresholds for quality decisions
QUALITY_THRESHOLDS = {
    "min_good_matches": 10,
    "min_inliers": 8,
    "min_inlier_ratio": 0.15,
    "max_reprojection_error": 8.0,
    "max_scale_ratio": 5.0,
}


@dataclass
class RegistrationResult:
    """Result of image registration between reference and suspect."""
    status: str                             # ComparisonStatus
    detector: str = DETECTOR_NAME
    detector_version: str = DETECTOR_VERSION
    keypoints_reference: int = 0
    keypoints_suspect: int = 0
    raw_matches: int = 0
    good_matches: int = 0
    inlier_count: int = 0
    outlier_count: int = 0
    inlier_ratio: float = 0.0
    reprojection_error: Optional[float] = None
    homography_matrix: Optional[list] = None
    projected_corners: Optional[list] = None
    overlap_ratio: Optional[float] = None
    execution_time_ms: int = 0
    warnings: list = field(default_factory=list)
    error: Optional[str] = None
    quality_checks: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detector": self.detector,
            "detector_version": self.detector_version,
            "keypoints_reference": self.keypoints_reference,
            "keypoints_suspect": self.keypoints_suspect,
            "raw_matches": self.raw_matches,
            "good_matches": self.good_matches,
            "inlier_count": self.inlier_count,
            "outlier_count": self.outlier_count,
            "inlier_ratio": round(self.inlier_ratio, 4),
            "reprojection_error": round(self.reprojection_error, 4) if self.reprojection_error is not None else None,
            "homography_matrix": self.homography_matrix,
            "projected_corners": self.projected_corners,
            "overlap_ratio": round(self.overlap_ratio, 4) if self.overlap_ratio is not None else None,
            "execution_time_ms": self.execution_time_ms,
            "warnings": self.warnings,
            "error": self.error,
            "quality_checks": self.quality_checks,
            "parameters": self.parameters,
        }


class RegistrationDetector(BaseDetector):
    """
    Image registration — aligns a suspect image to a reference original.
    Uses SIFT keypoints, FLANN matching, and RANSAC homography.
    """

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.KEYPOINT_MATCH

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """
        Run registration between reference_bytes and suspect_bytes.
        Both must be provided as kwargs.
        """
        start = time.perf_counter()

        ref_bytes: Optional[bytes] = kwargs.get("reference_bytes")
        sus_bytes: Optional[bytes] = kwargs.get("suspect_bytes")

        if not ref_bytes or not sus_bytes:
            return _failed_detector_result("reference_bytes and suspect_bytes are required")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        result = self.register(ref_bytes, sus_bytes, params)
        result.execution_time_ms = int((time.perf_counter() - start) * 1000)

        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=result.inlier_ratio,
            confidence=None,  # UNCALIBRATED
            details={
                "status": result.status,
                "registration": result.to_dict(),
                "score_semantics": "inlier_ratio (0-1, NOT an authenticity probability)",
                "reliability": "UNCALIBRATED",
            },
            execution_time_ms=result.execution_time_ms,
        )

    def register(
        self,
        reference_bytes: bytes,
        suspect_bytes: bytes,
        params: Optional[dict] = None,
    ) -> RegistrationResult:
        """
        Full registration pipeline.
        Returns RegistrationResult with status set appropriately.
        """
        if params is None:
            params = DEFAULT_PARAMS

        start = time.perf_counter()
        warnings: list[str] = []

        # ---- 1. Preprocess ----
        try:
            ref_pre = preprocess(reference_bytes, max_dimension=params["max_dimension"])
            sus_pre = preprocess(suspect_bytes, max_dimension=params["max_dimension"])
        except Exception as e:
            return RegistrationResult(
                status="FAILED", error=f"Preprocessing failed: {e}", parameters=params
            )

        ref_gray = ref_pre.gray
        sus_gray = sus_pre.gray

        # ---- 2. Feature extraction ----
        try:
            kp_ref, des_ref, kp_sus, des_sus = _extract_features(
                ref_gray, sus_gray, params, warnings
            )
        except Exception as e:
            return RegistrationResult(
                status="FAILED", error=f"Feature extraction failed: {e}", parameters=params
            )

        kp_ref_count = len(kp_ref) if kp_ref else 0
        kp_sus_count = len(kp_sus) if kp_sus else 0

        if des_ref is None or des_sus is None or kp_ref_count < 4 or kp_sus_count < 4:
            return RegistrationResult(
                status="NO_MATCH",
                keypoints_reference=kp_ref_count,
                keypoints_suspect=kp_sus_count,
                good_matches=0,
                warnings=warnings + ["Insufficient keypoints for matching"],
                parameters=params,
                quality_checks={"sufficientMatches": False, "overallPass": False},
            )

        # ---- 3. Feature matching ----
        good_matches, raw_count = _match_features(des_ref, des_sus, params, warnings)
        good_count = len(good_matches)

        if good_count < params["min_good_matches"]:
            return RegistrationResult(
                status="NO_MATCH",
                keypoints_reference=kp_ref_count,
                keypoints_suspect=kp_sus_count,
                raw_matches=raw_count,
                good_matches=good_count,
                warnings=warnings + [f"Only {good_count} good matches (need {params['min_good_matches']})"],
                parameters=params,
                quality_checks={
                    "sufficientMatches": False,
                    "overallPass": False,
                    "note": "Possible unrelated images or very heavily cropped copy",
                },
            )

        # ---- 4. RANSAC homography ----
        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_sus[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        try:
            H, mask = cv2.findHomography(
                src_pts, dst_pts,
                cv2.RANSAC,
                params["ransac_threshold"],
                maxIters=2000,
                confidence=0.995,
            )
        except cv2.error as e:
            return RegistrationResult(
                status="FAILED",
                keypoints_reference=kp_ref_count,
                keypoints_suspect=kp_sus_count,
                raw_matches=raw_count,
                good_matches=good_count,
                error=f"Homography estimation failed: {e}",
                parameters=params,
            )

        if H is None or mask is None:
            return RegistrationResult(
                status="INCONCLUSIVE",
                keypoints_reference=kp_ref_count,
                keypoints_suspect=kp_sus_count,
                raw_matches=raw_count,
                good_matches=good_count,
                warnings=warnings + ["RANSAC could not find homography"],
                parameters=params,
                quality_checks={"homographyNotDegenerate": False, "overallPass": False},
            )

        inlier_mask = mask.ravel().astype(bool)
        inlier_count = int(inlier_mask.sum())
        outlier_count = good_count - inlier_count
        inlier_ratio = inlier_count / good_count if good_count > 0 else 0.0

        # ---- 5. Compute reprojection error ----
        reprojection_error = None
        if inlier_count > 0:
            inlier_src = src_pts[inlier_mask]
            inlier_dst = dst_pts[inlier_mask]
            projected = cv2.perspectiveTransform(inlier_src, H)
            errors = np.linalg.norm(projected - inlier_dst, axis=2)
            reprojection_error = float(errors.mean())

        # ---- 6. Quality evaluation ----
        qc = _evaluate_quality(H, inlier_count, inlier_ratio, reprojection_error,
                                ref_pre.width, ref_pre.height, params)

        if not qc["overallPass"]:
            return RegistrationResult(
                status="INCONCLUSIVE",
                keypoints_reference=kp_ref_count,
                keypoints_suspect=kp_sus_count,
                raw_matches=raw_count,
                good_matches=good_count,
                inlier_count=inlier_count,
                outlier_count=outlier_count,
                inlier_ratio=inlier_ratio,
                reprojection_error=reprojection_error,
                homography_matrix=H.tolist() if H is not None else None,
                warnings=warnings + [f"Quality check failed: {qc}"],
                parameters=params,
                quality_checks=qc,
            )

        # ---- 7. Project corners ----
        h, w = ref_gray.shape
        corners_src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]).reshape(-1, 1, 2)
        projected_corners = cv2.perspectiveTransform(corners_src, H)
        corners_list = projected_corners.reshape(-1, 2).tolist()

        # ---- 8. Overlap ratio ----
        overlap_ratio = _compute_overlap_ratio(H, ref_gray.shape, sus_gray.shape)

        # Scale factor for mapping back to original dimensions
        h_scaled = H.copy()
        h_scaled[0, :] *= ref_pre.scale_x
        h_scaled[1, :] *= ref_pre.scale_y

        exec_ms = int((time.perf_counter() - start) * 1000)

        return RegistrationResult(
            status="COMPLETED",
            detector=DETECTOR_NAME,
            detector_version=DETECTOR_VERSION,
            keypoints_reference=kp_ref_count,
            keypoints_suspect=kp_sus_count,
            raw_matches=raw_count,
            good_matches=good_count,
            inlier_count=inlier_count,
            outlier_count=outlier_count,
            inlier_ratio=inlier_ratio,
            reprojection_error=reprojection_error,
            homography_matrix=H.tolist(),
            projected_corners=corners_list,
            overlap_ratio=overlap_ratio,
            execution_time_ms=exec_ms,
            warnings=warnings,
            quality_checks=qc,
            parameters=params,
        )


# ---- Internal helpers ----

def _extract_features(
    ref_gray: np.ndarray,
    sus_gray: np.ndarray,
    params: dict,
    warnings: list,
) -> tuple:
    """Extract keypoints and descriptors. SIFT preferred, ORB fallback."""
    detector_name = params.get("feature_detector", "sift").lower()
    max_kp = params.get("max_keypoints", 2000)

    if detector_name == "sift":
        try:
            det = cv2.SIFT_create(nfeatures=max_kp)
        except (AttributeError, cv2.error):
            warnings.append("SIFT unavailable, falling back to ORB")
            detector_name = "orb"

    if detector_name == "orb":
        det = cv2.ORB_create(nfeatures=max_kp)
    elif detector_name == "akaze":
        det = cv2.AKAZE_create()
    elif detector_name == "sift":
        pass  # already created above
    else:
        warnings.append(f"Unknown detector '{detector_name}', using ORB")
        det = cv2.ORB_create(nfeatures=max_kp)

    kp_ref, des_ref = det.detectAndCompute(ref_gray, None)
    kp_sus, des_sus = det.detectAndCompute(sus_gray, None)
    return kp_ref, des_ref, kp_sus, des_sus


def _match_features(
    des_ref: np.ndarray,
    des_sus: np.ndarray,
    params: dict,
    warnings: list,
) -> tuple[list, int]:
    """Match descriptors with ratio test."""
    ratio_threshold = params.get("ratio_threshold", 0.75)

    # Choose matcher based on descriptor type
    if des_ref.dtype == np.uint8:
        # Binary descriptors (ORB, AKAZE) — Hamming distance
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    else:
        # Float descriptors (SIFT) — FLANN
        try:
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            bf = cv2.FlannBasedMatcher(index_params, search_params)
        except Exception:
            warnings.append("FLANN unavailable, using BFMatcher L2")
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

    matches = bf.knnMatch(des_ref, des_sus, k=2)
    raw_count = len(matches)

    # Lowe's ratio test
    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < ratio_threshold * n.distance:
                good.append(m)

    return good, raw_count


def _evaluate_quality(
    H: Optional[np.ndarray],
    inlier_count: int,
    inlier_ratio: float,
    reprojection_error: Optional[float],
    ref_w: int,
    ref_h: int,
    params: dict,
) -> dict:
    """Multi-factor registration quality evaluation."""
    checks = {
        "sufficientMatches": True,  # already checked before calling
        "sufficientInliers": inlier_count >= params["min_inliers"],
        "inlierRatioAboveThreshold": inlier_ratio >= params["min_inlier_ratio"],
        "reprojectionErrorAcceptable": (
            reprojection_error is not None
            and reprojection_error <= params["max_reprojection_error"]
        ),
        "homographyNotDegenerate": False,
        "cornersProjectedValidly": False,
        "scaleReasonable": False,
    }

    if H is not None and H.shape == (3, 3):
        # Check if homography is degenerate (near-zero determinant)
        det = np.linalg.det(H)
        checks["homographyNotDegenerate"] = abs(det) > 1e-6

        # Scale check — estimate scale from homography
        try:
            scale_x = np.sqrt(H[0, 0] ** 2 + H[1, 0] ** 2)
            scale_y = np.sqrt(H[0, 1] ** 2 + H[1, 1] ** 2)
            avg_scale = (scale_x + scale_y) / 2
            max_scale = params["max_scale_ratio"]
            checks["scaleReasonable"] = (1.0 / max_scale) < avg_scale < max_scale
        except Exception:
            checks["scaleReasonable"] = False

        # Project corners and check validity
        try:
            corners = np.float32([[0, 0], [ref_w, 0], [ref_w, ref_h], [0, ref_h]]).reshape(-1, 1, 2)
            projected = cv2.perspectiveTransform(corners, H)
            pts = projected.reshape(-1, 2)
            # Check no corner collapses to infinity
            checks["cornersProjectedValidly"] = (
                not np.any(np.isinf(pts)) and
                not np.any(np.isnan(pts)) and
                np.max(np.abs(pts)) < 1e5
            )
        except Exception:
            checks["cornersProjectedValidly"] = False

    # Overall pass — all critical checks must pass
    critical = ["sufficientInliers", "inlierRatioAboveThreshold",
                 "reprojectionErrorAcceptable", "homographyNotDegenerate",
                 "cornersProjectedValidly", "scaleReasonable"]
    checks["overallPass"] = all(checks[k] for k in critical)
    return checks


def _compute_overlap_ratio(H: np.ndarray, ref_shape: tuple, sus_shape: tuple) -> float:
    """Estimate overlap ratio between reference and aligned suspect."""
    try:
        ref_h, ref_w = ref_shape[:2]
        sus_h, sus_w = sus_shape[:2]

        # Create masks
        ref_mask = np.ones((ref_h, ref_w), dtype=np.uint8) * 255
        sus_mask = np.ones((sus_h, sus_w), dtype=np.uint8) * 255

        # Warp reference mask into suspect space
        ref_warped = cv2.warpPerspective(ref_mask, H, (sus_w, sus_h))

        # Overlap
        overlap = cv2.bitwise_and(sus_mask, ref_warped)
        ref_pixels = int(np.count_nonzero(ref_mask))
        sus_pixels = int(np.count_nonzero(sus_mask))
        overlap_pixels = int(np.count_nonzero(overlap))

        min_area = min(ref_pixels, sus_pixels)
        if min_area == 0:
            return 0.0
        return float(overlap_pixels / min_area)
    except Exception:
        return 0.0


def _failed_detector_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.KEYPOINT_MATCH,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[RegistrationDetector] = None

def get_registration_detector() -> RegistrationDetector:
    global _instance
    if _instance is None:
        _instance = RegistrationDetector()
    return _instance
