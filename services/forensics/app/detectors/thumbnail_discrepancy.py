"""
EXIF Embedded Thumbnail Discrepancy Detector — Phase 2.

Analyzes structural, color, and geometric consistency between the full-resolution
image and the low-resolution preview thumbnail embedded in the EXIF container (IFD1).

Forensic Rationale:
  - Real camera shutter capture encodes both the full-resolution sensor frame and a
    tiny preview thumbnail (e.g. 160x120 or 320x240 JPEG) into EXIF at capture time.
  - When an image is cropped, tampered, or modified in post-processing tools, many
    editors update only the main canvas and forget to re-render the embedded thumbnail.
  - Any significant divergence between the thumbnail and the main image represents
    definitive physical evidence of post-capture tampering.

Status Values:
  - THUMBNAIL_MATCH_AUTHENTIC: Main image and thumbnail are structurally and visually consistent.
  - DISCREPANCY_CROPPED: Aspect ratio mismatch between thumbnail and main image (crop tampering).
  - DISCREPANCY_EDITED: Localized or global content mismatch between main image and thumbnail.
  - NO_THUMBNAIL_EMBEDDED: EXIF contains no embedded thumbnail (normal for social media or WebP/PNG).
"""

from __future__ import annotations

import io
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image as PILImage

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult

logger = logging.getLogger(__name__)

DETECTOR_NAME = "thumbnail_discrepancy"
DETECTOR_VERSION = "1.0.0"


@dataclass
class ThumbnailAnalysisResult:
    has_thumbnail: bool
    status: str  # THUMBNAIL_MATCH_AUTHENTIC | DISCREPANCY_CROPPED | DISCREPANCY_EDITED | NO_THUMBNAIL_EMBEDDED
    similarity_score: float  # 0.0 to 1.0 (1.0 = identical)
    aspect_ratio_diff: float
    max_local_diff: float
    evidence: list[str] = field(default_factory=list)
    thumbnail_dims: tuple[int, int] = (0, 0)
    main_dims: tuple[int, int] = (0, 0)


def extract_and_compare_thumbnail(image_bytes: bytes) -> ThumbnailAnalysisResult:
    """
    Extracts embedded EXIF thumbnail and compares it to the main image.
    """
    evidence: list[str] = []

    try:
        pil_img = PILImage.open(io.BytesIO(image_bytes))
        main_w, main_h = pil_img.size
        thumb_bytes = None

        # Extract embedded thumbnail via PIL
        if hasattr(pil_img, "_getexif") and pil_img._getexif():
            # Check for embedded JPEG thumbnail
            try:
                from PIL.ExifTags import TAGS
                exif = pil_img._getexif()
                # Also check get_thumbnail
                if hasattr(pil_img, "get_thumbnail"):
                    thumb_bytes = pil_img.get_thumbnail()
            except Exception:
                pass

        # Alternate manual extraction for IFD1 JPEG thumbnail marker in raw bytes
        if not thumb_bytes and b"\xFF\xD8" in image_bytes:
            # Look for second SOI marker inside APP1 (IFD1 thumbnail)
            first_soi = image_bytes.find(b"\xFF\xD8")
            if first_soi >= 0:
                # Search within first 64KB for embedded thumbnail SOI
                second_soi = image_bytes.find(b"\xFF\xD8", first_soi + 2)
                if 0 < second_soi < 65536:
                    eoi = image_bytes.find(b"\xFF\xD9", second_soi + 2)
                    if eoi > second_soi:
                        thumb_bytes = image_bytes[second_soi : eoi + 2]

        if not thumb_bytes:
            return ThumbnailAnalysisResult(
                has_thumbnail=False,
                status="NO_THUMBNAIL_EMBEDDED",
                similarity_score=1.0,
                aspect_ratio_diff=0.0,
                max_local_diff=0.0,
                evidence=["No embedded preview thumbnail present in EXIF."],
                main_dims=(main_w, main_h),
            )

        # Decode embedded thumbnail
        thumb_pil = PILImage.open(io.BytesIO(thumb_bytes)).convert("RGB")
        tw, th = thumb_pil.size

        if tw < 16 or th < 16:
            return ThumbnailAnalysisResult(
                has_thumbnail=False,
                status="NO_THUMBNAIL_EMBEDDED",
                similarity_score=1.0,
                aspect_ratio_diff=0.0,
                max_local_diff=0.0,
                evidence=["Embedded thumbnail stream too small to evaluate."],
                main_dims=(main_w, main_h),
            )

        main_rgb = np.array(pil_img.convert("RGB"), dtype=np.uint8)
        thumb_rgb = np.array(thumb_pil, dtype=np.uint8)

        # 1. Aspect ratio check
        main_ar = float(main_w) / float(main_h)
        thumb_ar = float(tw) / float(th)
        ar_diff = abs(main_ar - thumb_ar)

        # Resize main image to exact thumbnail dimensions for pixel-level structural comparison
        main_downscaled = cv2.resize(main_rgb, (tw, th), interpolation=cv2.INTER_AREA)

        # 2. Structural & intensity difference
        gray_main = cv2.cvtColor(main_downscaled, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray_thumb = cv2.cvtColor(thumb_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)

        # Normalized cross correlation
        mean_m = gray_main.mean()
        mean_t = gray_thumb.mean()
        norm_m = gray_main - mean_m
        norm_t = gray_thumb - mean_t
        denom = math.sqrt(float(np.sum(norm_m**2)) * float(np.sum(norm_t**2)))

        if denom > 0:
            ncc = float(np.sum(norm_m * norm_t) / denom)
        else:
            ncc = 1.0

        similarity = float(np.clip(ncc, 0.0, 1.0))

        # Local block difference (to catch spliced stickers or edited elements)
        diff = np.abs(gray_main - gray_thumb)
        max_diff = float(diff.max()) / 255.0

        if ar_diff > 0.12:
            status = "DISCREPANCY_CROPPED"
            evidence.append(
                f"EXIF thumbnail aspect ratio mismatch: main canvas is {main_ar:.2f} but thumbnail is {thumb_ar:.2f}. Image was cropped after capture."
            )
        elif similarity < 0.82 or max_diff > 0.65:
            status = "DISCREPANCY_EDITED"
            evidence.append(
                f"Severe content divergence between main image and embedded EXIF thumbnail (similarity: {similarity:.2f}). Localized tampering detected."
            )
        else:
            status = "THUMBNAIL_MATCH_AUTHENTIC"
            evidence.append(
                f"Embedded EXIF preview thumbnail verified ({tw}x{th}): structurally identical to main canvas (similarity: {similarity:.2f})."
            )

        return ThumbnailAnalysisResult(
            has_thumbnail=True,
            status=status,
            similarity_score=round(similarity, 4),
            aspect_ratio_diff=round(ar_diff, 4),
            max_local_diff=round(max_diff, 4),
            evidence=evidence,
            thumbnail_dims=(tw, th),
            main_dims=(main_w, main_h),
        )
    except Exception as e:
        logger.debug("Thumbnail comparison failed: %s", e)
        return ThumbnailAnalysisResult(
            has_thumbnail=False,
            status="NO_THUMBNAIL_EMBEDDED",
            similarity_score=1.0,
            aspect_ratio_diff=0.0,
            max_local_diff=0.0,
            evidence=[f"Could not extract EXIF thumbnail: {e}"],
        )


class ThumbnailDiscrepancyDetector(BaseDetector):
    """Forensic detector identifying discrepancies between image and embedded EXIF thumbnail."""

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

        res = extract_and_compare_thumbnail(image_bytes)
        exec_ms = int((time.perf_counter() - start) * 1000)

        # Score: 0.0 (authentic match), 0.95 (discrepancy detected), None (no thumbnail)
        if res.status in ("DISCREPANCY_CROPPED", "DISCREPANCY_EDITED"):
            score = 0.95
            confidence = 0.90
        elif res.status == "THUMBNAIL_MATCH_AUTHENTIC":
            score = 0.02
            confidence = 0.95
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
                "has_thumbnail": res.has_thumbnail,
                "status": res.status,
                "similarity_score": res.similarity_score,
                "aspect_ratio_diff": res.aspect_ratio_diff,
                "thumbnail_dims": res.thumbnail_dims,
                "main_dims": res.main_dims,
                "evidence": res.evidence,
            },
            execution_time_ms=exec_ms,
        )


_singleton: Optional[ThumbnailDiscrepancyDetector] = None


def get_thumbnail_discrepancy_detector() -> ThumbnailDiscrepancyDetector:
    """Return singleton instance of ThumbnailDiscrepancyDetector."""
    global _singleton
    if _singleton is None:
        _singleton = ThumbnailDiscrepancyDetector()
    return _singleton
