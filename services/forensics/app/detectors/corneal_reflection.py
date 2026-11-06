"""
Corneal Specular Reflection & Iris Consistency Detector — Phase 2.

Analyzes corneal light reflections (catchlights) and iris symmetry in portrait images
to detect AI-generated synthetic faces and localized face-swap manipulations.

Biometric & Physical Principles:
  - Real human eyes have moist, spherical corneas acting as natural convex mirrors.
  - Distant physical light sources (windows, sun, studio softboxes) project geometrically
    identical specular highlights onto both the left and right corneas.
  - The relative angular position of catchlights within both pupils must align with parallel light rays.
  - Human pupils are smooth circular/elliptical apertures (circularity > 0.80).
  - Diffusion AI models (Midjourney, DALL-E, Flux) synthesize eyes independently, often hallucinating
    conflicting catchlight counts, divergent light source angles, or deformed jagged pupils.

Status Values:
  - CORNEAL_SYMMETRY_VERIFIED: Consistent dual-corneal specular reflections and circular pupils (real photo).
  - CORNEAL_ASYMMETRY_DETECTED: Conflicting specular reflections or deformed pupils (AI synthetic face).
  - NO_EYES_DETECTED: No clear eye pairs found (non-portrait, profile view, or low resolution).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.io.preprocessing import preprocess

logger = logging.getLogger(__name__)

DETECTOR_NAME = "corneal_reflection"
DETECTOR_VERSION = "1.0.0"


@dataclass
class EyeAnalysis:
    bbox: tuple[int, int, int, int]  # (x, y, w, h)
    pupil_center: tuple[float, float]
    pupil_circularity: float
    highlight_count: int
    primary_highlight_offset: tuple[float, float]  # normalized (dx, dy) from pupil center
    light_angle_deg: float


@dataclass
class CornealResult:
    status: str  # CORNEAL_SYMMETRY_VERIFIED | CORNEAL_ASYMMETRY_DETECTED | NO_EYES_DETECTED
    symmetry_score: float  # 0.0 (conflicting) to 1.0 (perfect physical symmetry)
    angular_divergence_deg: float
    pupil_circularity_mean: float
    face_count: int
    evidence: list[str] = field(default_factory=list)


def analyze_eye_patch(eye_gray: np.ndarray) -> Optional[EyeAnalysis]:
    """
    Locates pupil, measures circularity, and extracts specular highlights.
    """
    eh, ew = eye_gray.shape[:2]
    if eh < 24 or ew < 24:
        return None

    # Focus on central 60% of eye where iris resides
    margin_y = int(eh * 0.20)
    margin_x = int(ew * 0.20)
    roi = eye_gray[margin_y : eh - margin_y, margin_x : ew - margin_x]
    rh, rw = roi.shape[:2]

    # Pupil is the darkest region inside the eye ROI
    blurred = cv2.GaussianBlur(roi, (5, 5), 0)
    min_val, _, min_loc, _ = cv2.minMaxLoc(blurred)

    # Threshold for dark pupil
    dark_thresh = min(int(min_val * 1.5 + 20), 80)
    _, pupil_mask = cv2.threshold(blurred, dark_thresh, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(pupil_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Pick largest central contour as candidate pupil
    best_cnt = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(best_cnt)
    perimeter = cv2.arcLength(best_cnt, True)

    if area < 20 or perimeter <= 0:
        return None

    circularity = (4.0 * math.pi * area) / (perimeter * perimeter)
    circularity = float(np.clip(circularity, 0.0, 1.0))

    # Center of mass of pupil
    M = cv2.moments(best_cnt)
    if M["m00"] > 0:
        pc_x = M["m10"] / M["m00"] + margin_x
        pc_y = M["m01"] / M["m00"] + margin_y
    else:
        pc_x = min_loc[0] + margin_x
        pc_y = min_loc[1] + margin_y

    # Specular highlights (brightest glints on cornea, value > 220)
    _, glint_mask = cv2.threshold(roi, 220, 255, cv2.THRESH_BINARY)
    glint_contours, _ = cv2.findContours(glint_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    glint_count = len([c for c in glint_contours if cv2.contourArea(c) >= 2])

    # Find primary highlight closest to pupil
    if glint_contours:
        primary_glint = max(glint_contours, key=cv2.contourArea)
        Mg = cv2.moments(primary_glint)
        if Mg["m00"] > 0:
            gx = Mg["m10"] / Mg["m00"] + margin_x
            gy = Mg["m01"] / Mg["m00"] + margin_y
        else:
            gx, gy = pc_x, pc_y
        dx = (gx - pc_x) / float(ew)
        dy = (gy - pc_y) / float(eh)
        angle = math.degrees(math.atan2(dy, dx))
    else:
        dx, dy = 0.0, 0.0
        angle = 0.0

    return EyeAnalysis(
        bbox=(0, 0, ew, eh),
        pupil_center=(pc_x, pc_y),
        pupil_circularity=circularity,
        highlight_count=glint_count,
        primary_highlight_offset=(dx, dy),
        light_angle_deg=angle,
    )


def analyze_corneal_reflections(gray: np.ndarray) -> CornealResult:
    """
    Detects faces and pairs of eyes to verify physical lighting symmetry.
    """
    evidence: list[str] = []

    try:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(64, 64))

        if len(faces) == 0:
            return CornealResult(
                status="NO_EYES_DETECTED",
                symmetry_score=0.5,
                angular_divergence_deg=0.0,
                pupil_circularity_mean=0.0,
                face_count=0,
                evidence=["No frontal faces detected for corneal reflection analysis."],
            )

        # Evaluate largest face
        largest_face = max(faces, key=lambda f: f[2] * f[3])
        fx, fy, fw, fh = largest_face
        face_roi = gray[fy : fy + fh, fx : fx + fw]

        # Upper 55% of face contains eyes
        upper_face = face_roi[: int(fh * 0.55), :]
        eyes = eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20))

        if len(eyes) < 2:
            return CornealResult(
                status="NO_EYES_DETECTED",
                symmetry_score=0.5,
                angular_divergence_deg=0.0,
                pupil_circularity_mean=0.0,
                face_count=len(faces),
                evidence=["Face detected, but individual eye pupils were not resolved clearly."],
            )

        # Sort eyes left-to-right
        sorted_eyes = sorted(eyes, key=lambda e: e[0])
        left_eye_box = sorted_eyes[0]
        right_eye_box = sorted_eyes[-1]

        # Ensure they are distinct left and right eyes (separated horizontally by at least 15% of face width)
        if (right_eye_box[0] - left_eye_box[0]) < int(fw * 0.15):
            return CornealResult(
                status="NO_EYES_DETECTED",
                symmetry_score=0.5,
                angular_divergence_deg=0.0,
                pupil_circularity_mean=0.0,
                face_count=len(faces),
                evidence=["Detected eye regions overlap; cannot verify dual-corneal reflection."],
            )

        lex, ley, lew, leh = left_eye_box
        rex, rey, rew, reh = right_eye_box
        left_patch = upper_face[ley : ley + leh, lex : lex + lew]
        right_patch = upper_face[rey : rey + reh, rex : rex + rew]

        left_eye = analyze_eye_patch(left_patch)
        right_eye = analyze_eye_patch(right_patch)

        if not left_eye or not right_eye:
            return CornealResult(
                status="NO_EYES_DETECTED",
                symmetry_score=0.5,
                angular_divergence_deg=0.0,
                pupil_circularity_mean=0.0,
                face_count=len(faces),
                evidence=["Pupil apertures could not be isolated from eye regions."],
            )

        # 1. Angular divergence between light vectors
        ang_diff = abs(left_eye.light_angle_deg - right_eye.light_angle_deg)
        if ang_diff > 180:
            ang_diff = 360 - ang_diff

        # 2. Highlight count difference
        count_diff = abs(left_eye.highlight_count - right_eye.highlight_count)

        # 3. Mean pupil circularity
        mean_circ = (left_eye.pupil_circularity + right_eye.pupil_circularity) / 2.0

        # Physical consistency calculation:
        # In real cameras, angular difference is small (< 35 deg), count_diff <= 1, and circularity > 0.70.
        ang_penalty = min(ang_diff / 90.0, 1.0)
        count_penalty = min(count_diff * 0.3, 0.6)
        circ_bonus = 0.2 if mean_circ >= 0.70 else -0.3

        symmetry = float(np.clip(1.0 - (0.5 * ang_penalty + count_penalty) + circ_bonus, 0.0, 1.0))

        if symmetry >= 0.68 and mean_circ >= 0.65:
            status = "CORNEAL_SYMMETRY_VERIFIED"
            evidence.append(
                f"Bilateral corneal catchlights consistent (light angle divergence: {ang_diff:.1f}°, circularity: {mean_circ:.2f}). Natural single/dual illumination verified."
            )
        elif symmetry <= 0.38 or mean_circ < 0.40:
            status = "CORNEAL_ASYMMETRY_DETECTED"
            evidence.append(
                f"Conflicting corneal reflections detected: light vector mismatch {ang_diff:.1f}° with deformed pupils ({mean_circ:.2f} circularity). Consistent with independent AI eye synthesis."
            )
        else:
            status = "CORNEAL_SYMMETRY_VERIFIED"
            evidence.append(
                f"Corneal reflections within acceptable illumination variation (divergence: {ang_diff:.1f}°)."
            )

        return CornealResult(
            status=status,
            symmetry_score=round(symmetry, 4),
            angular_divergence_deg=round(ang_diff, 1),
            pupil_circularity_mean=round(mean_circ, 3),
            face_count=len(faces),
            evidence=evidence,
        )
    except Exception as e:
        logger.debug("Corneal reflection analysis failed: %s", e)
        return CornealResult(
            status="NO_EYES_DETECTED",
            symmetry_score=0.5,
            angular_divergence_deg=0.0,
            pupil_circularity_mean=0.0,
            face_count=0,
            evidence=[f"Eye analysis encountered error: {e}"],
        )


class CornealReflectionDetector(BaseDetector):
    """Forensic detector measuring corneal reflection and pupil symmetry in portraits."""

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.METADATA

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        start = time.perf_counter()
        image_bytes: Optional[bytes] = kwargs.get("image_bytes")

        if not image_bytes and image_path:
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            except OSError as e:
                return DetectorResult(
                    detector=self.name,
                    version=self.version,
                    category=self.category,
                    details={"status": "UNAVAILABLE", "error": str(e)},
                )

        if not image_bytes:
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                details={"status": "UNAVAILABLE", "error": "No image data provided"},
            )

        try:
            pre = preprocess(image_bytes, max_dimension=1024)
            res = analyze_corneal_reflections(pre.gray)
            exec_ms = int((time.perf_counter() - start) * 1000)

            # Score: 0.0 (natural symmetry), 0.95 (conflicting AI highlights), None (no face)
            if res.status == "CORNEAL_ASYMMETRY_DETECTED":
                score = round(1.0 - res.symmetry_score, 4)
                confidence = 0.85
            elif res.status == "CORNEAL_SYMMETRY_VERIFIED":
                score = round(1.0 - res.symmetry_score, 4)
                confidence = 0.90
            else:
                score = None
                confidence = None

            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                score=score,
                confidence=confidence,
                details={
                    "status": res.status,
                    "symmetry_score": res.symmetry_score,
                    "angular_divergence_deg": res.angular_divergence_deg,
                    "pupil_circularity_mean": res.pupil_circularity_mean,
                    "face_count": res.face_count,
                    "evidence": res.evidence,
                },
                execution_time_ms=exec_ms,
            )
        except Exception as e:
            logger.error("Corneal reflection detector failed: %s", e)
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                details={"status": "UNAVAILABLE", "error": str(e)},
            )


_singleton: Optional[CornealReflectionDetector] = None


def get_corneal_reflection_detector() -> CornealReflectionDetector:
    """Return singleton instance of CornealReflectionDetector."""
    global _singleton
    if _singleton is None:
        _singleton = CornealReflectionDetector()
    return _singleton

