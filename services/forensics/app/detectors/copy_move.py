"""
Copy-Move Detection Detector — Phase 3.

Algorithm:
1. Extract ORB keypoints and descriptors from the image.
2. Match descriptors within the same image (kNN with ratio test).
3. Filter out close-proximity matches (neighboring keypoints).
4. Apply RANSAC geometric consistency check.
5. Cluster geometrically consistent matches into region candidates.
6. Generate a copy-move evidence mask.

Score semantics:
  Copy-move score = geometric consistency of duplicated feature matches (0-1).
  NOT a probability of manipulation. High score means many consistent
  duplicated features, which COULD indicate copy-move forgery but can
  also occur in images with natural repeated structures.

Conservative design:
  - Requires minimum match count before reporting.
  - Ratio test threshold is strict.
  - Neighboring matches are rejected.
  - Hard negatives (repeated patterns, bricks, windows) are acknowledged.

Version: 1.0.0
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import cv2

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "copy_move"
DETECTOR_VERSION = "1.0.0"

DEFAULT_PARAMS = {
    "max_dimension": 512,
    "max_keypoints": 500,
    "ratio_threshold": 0.75,       # Lowe's ratio test
    "min_distance": 20,            # minimum pixel distance between matched keypoints
    "min_matches": 10,             # minimum consistent matches to report
    "ransac_threshold": 5.0,       # RANSAC reprojection threshold (pixels)
    "scale_factor": 1.2,
    "n_levels": 8,
}


class CopyMoveDetector(BaseDetector):
    """Copy-move forgery detection using ORB features."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.COPY_MOVE

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        import time
        start = time.perf_counter()

        image_bytes: Optional[bytes] = kwargs.get("image_bytes")
        if not image_bytes:
            return _failed_result("No image data provided")

        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        warnings: list[str] = []

        try:
            pre = preprocess(image_bytes, max_dimension=params["max_dimension"])
            gray = pre.gray

            # Initialize ORB detector
            orb = cv2.ORB_create(
                nfeatures=params["max_keypoints"],
                scaleFactor=params["scale_factor"],
                nlevels=params["n_levels"],
            )

            # Detect keypoints and compute descriptors
            kp, des = orb.detectAndCompute(gray, None)

            if des is None or len(kp) < 4:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=0.0,
                    confidence=None,
                    details={
                        "status": "COMPLETED",
                        "score_semantics": "no sufficient keypoints found",
                        "reliability": "UNCALIBRATED",
                        "parameters": params,
                        "evidence": {
                            "keypoint_count": len(kp) if kp else 0,
                            "match_count": 0,
                            "filtered_match_count": 0,
                            "geometrically_consistent": 0,
                            "region_candidates": [],
                        },
                        "warnings": ["Too few keypoints for meaningful matching"],
                        "limitations": [],
                    },
                    execution_time_ms=elapsed_ms,
                )

            # Match descriptors against themselves using BFMatcher with kNN
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            matches = bf.knnMatch(des, des, k=2)

            # Apply ratio test and distance filter
            ratio_thresh = params["ratio_threshold"]
            min_dist = params["min_distance"]
            good_matches = []

            for match_pair in matches:
                if len(match_pair) < 2:
                    continue
                m, n = match_pair
                # Skip self-matches (same keypoint)
                if m.queryIdx == m.trainIdx:
                    # Check the second best
                    if n.queryIdx != n.trainIdx:
                        good_matches.append(n)
                    continue
                # Ratio test
                if m.distance < ratio_thresh * n.distance:
                    # Filter by spatial distance (reject neighboring keypoints)
                    pt1 = kp[m.queryIdx].pt
                    pt2 = kp[m.trainIdx].pt
                    dist = np.sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)
                    if dist > min_dist:
                        good_matches.append(m)

            match_count = len(good_matches)

            if match_count < params["min_matches"]:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    score=0.0,
                    confidence=None,
                    details={
                        "status": "COMPLETED",
                        "score_semantics": "insufficient matches after filtering",
                        "reliability": "UNCALIBRATED",
                        "parameters": params,
                        "evidence": {
                            "keypoint_count": len(kp),
                            "match_count": match_count,
                            "filtered_match_count": match_count,
                            "geometrically_consistent": 0,
                            "region_candidates": [],
                            "note": "Below minimum match threshold — likely no copy-move detected",
                        },
                        "warnings": [],
                        "limitations": [
                            "Low match count does not guarantee no copy-move exists",
                            "Small or smooth copy-moved regions may not produce enough keypoints",
                        ],
                    },
                    execution_time_ms=elapsed_ms,
                )

            # Extract matched point pairs
            src_pts = np.float32([kp[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            # RANSAC geometric consistency check
            geometrically_consistent = 0
            region_candidates = []
            mask_artifact = None

            if len(src_pts) >= 4:
                # Try to find an affine transformation
                affine_mask = cv2.estimateAffine2D(src_pts, dst_pts, method=cv2.RANSAC,
                                                      ransacReprojThreshold=params["ransac_threshold"],
                                                      maxIters=1000)
                if affine_mask is not None:
                    _, inliers = affine_mask[1], affine_mask[2] if len(affine_mask) > 2 else None
                    if inliers is not None:
                        geometrically_consistent = int(np.sum(inliers))

                        # Score: ratio of geometrically consistent matches to total keypoints
                        score = float(geometrically_consistent / len(kp)) if len(kp) > 0 else 0.0

                        # Generate evidence mask
                        mask = np.zeros((pre.height, pre.width), dtype=np.uint8)
                        for i, m in enumerate(good_matches):
                            if inliers[i]:
                                pt1 = (int(kp[m.queryIdx].pt[0]), int(kp[m.queryIdx].pt[1]))
                                pt2 = (int(kp[m.trainIdx].pt[0]), int(kp[m.trainIdx].pt[1]))
                                cv2.circle(mask, pt1, 5, 255, -1)
                                cv2.circle(mask, pt2, 5, 255, -1)
                                # Draw line between matched pairs
                                cv2.line(mask, pt1, pt2, 128, 1)

                        artifact_bytes = encode_artifact_png(mask, normalize=False)
                        import base64
                        mask_b64 = base64.b64encode(artifact_bytes).decode("ascii")

                        # Extract region candidates (bounding boxes of consistent match clusters)
                        if geometrically_consistent > 0:
                            consistent_pts_src = src_pts[inliers.astype(bool)].reshape(-1, 2)
                            consistent_pts_dst = dst_pts[inliers.astype(bool)].reshape(-1, 2)
                            for pts in [consistent_pts_src, consistent_pts_dst]:
                                if len(pts) > 0:
                                    x_min, y_min = int(pts[:, 0].min()), int(pts[:, 1].min())
                                    x_max, y_max = int(pts[:, 0].max()), int(pts[:, 1].max())
                                    region_candidates.append({
                                        "bbox": {"x": x_min, "y": y_min, "width": x_max - x_min, "height": y_max - y_min},
                                        "point_count": len(pts),
                                    })

                        mask_artifact = {
                            "type": "copy_move_mask",
                            "format": "png",
                            "encoding": "base64",
                            "data": mask_b64[:80] + "...",
                            "full_size_bytes": len(artifact_bytes),
                        }
                    else:
                        score = 0.0
                        warnings.append("RANSAC could not estimate transformation")
                else:
                    score = 0.0
                    warnings.append("Affine estimation failed")
            else:
                score = 0.0
                warnings.append("Insufficient matches for RANSAC")

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=score,
                confidence=None,  # UNCALIBRATED
                details={
                    "status": "COMPLETED",
                    "score_semantics": "geometric consistency ratio (consistent matches / total keypoints, NOT a probability)",
                    "reliability": "UNCALIBRATED",
                    "parameters": params,
                    "evidence": {
                        "keypoint_count": len(kp),
                        "raw_match_count": len(matches),
                        "filtered_match_count": match_count,
                        "geometrically_consistent": geometrically_consistent,
                        "region_candidates": region_candidates,
                    },
                    "image_info": {
                        "analysis_width": pre.width,
                        "analysis_height": pre.height,
                        "original_width": pre.original_width,
                        "original_height": pre.original_height,
                    },
                    "artifact": mask_artifact,
                    "warnings": warnings,
                    "limitations": [
                        "Natural repeated structures (windows, bricks, patterns) can produce matches",
                        "Small or smooth copy-moved regions may not produce enough keypoints",
                        "The detector is conservative — false negatives are preferred over false positives",
                        "High match count does NOT automatically mean manipulation",
                    ],
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning("Copy-move detector failed", exc_info=True)
            return _failed_result(f"Copy-move error: {type(e).__name__}: {e}")


def _failed_result(msg: str) -> DetectorResult:
    return DetectorResult(
        detector=DETECTOR_NAME,
        version=DETECTOR_VERSION,
        category=DetectorCategory.COPY_MOVE,
        details={"status": "FAILED", "error": msg},
    )


_instance: Optional[CopyMoveDetector] = None

def get_copy_move_detector() -> CopyMoveDetector:
    global _instance
    if _instance is None:
        _instance = CopyMoveDetector()
    return _instance
