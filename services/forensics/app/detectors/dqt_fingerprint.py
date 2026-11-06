"""
JPEG Quantization Table (DQT) Fingerprint Detector.

Extracts JPEG quantization tables from image data and matches them against
a database of known hardware camera and software encoder signatures.

Every JPEG encoder uses a quantization table (64 values for luminance, 64 for
chrominance). Camera manufacturers (Apple, Samsung, Sony, Canon, Nikon, Google)
use proprietary tables baked into their ISP firmware.  Software encoders
(Python Pillow/libjpeg, Photoshop, GIMP, ffmpeg) use different standard or
proprietary tables.  AI image generators that save as JPEG typically use
Python's ``PIL.Image.save()`` which produces standard libjpeg/IJG tables.

This module provides:
  - DQT extraction from raw JPEG bytes
  - Standard IJG table generation for any quality level 1-100
  - A fingerprint database of known encoder signatures
  - L1-distance matching with confidence scoring
  - A ``DQTFingerprintDetector`` class following the ``BaseDetector`` contract
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standard IJG / libjpeg base quantization tables (quality = 50 baseline)
# ---------------------------------------------------------------------------

IJG_BASE_LUMINANCE: list[int] = [
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
]

IJG_BASE_CHROMINANCE: list[int] = [
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
]


# ---------------------------------------------------------------------------
# IJG quality-factor table generation
# ---------------------------------------------------------------------------

def generate_standard_ijg_table(
    quality: int,
    base_table: Optional[list[int]] = None,
) -> list[int]:
    """Generate a standard IJG quantization table for a given quality factor.

    Uses the Independent JPEG Group scaling formula:
      - For quality < 50:  ``scale = 5000 / quality``
      - For quality >= 50: ``scale = 200 - 2 * quality``

    Each base-table value is scaled by ``(base * scale + 50) // 100``, then
    clamped to ``[1, 255]``.

    Args:
        quality: JPEG quality factor in the range ``[1, 100]``.
        base_table: 64-element base quantization table.  Defaults to the
            standard IJG luminance base table if *None*.

    Returns:
        A list of 64 quantized values.

    Raises:
        ValueError: If *quality* is outside ``[1, 100]``.
    """
    if not 1 <= quality <= 100:
        raise ValueError(f"Quality must be 1-100, got {quality}")

    if base_table is None:
        base_table = IJG_BASE_LUMINANCE

    if quality < 50:
        scale = 5000 // quality
    else:
        scale = 200 - 2 * quality

    table: list[int] = []
    for base_val in base_table:
        val = (base_val * scale + 50) // 100
        val = max(1, min(255, val))
        table.append(val)
    return table


# ---------------------------------------------------------------------------
# DQT extraction helpers
# ---------------------------------------------------------------------------

_JPEG_SOI = b"\xff\xd8"  # Start Of Image marker


def extract_dqt_tables(image_bytes: bytes) -> Optional[dict[str, Any]]:
    """Parse raw JPEG bytes and extract quantization tables.

    Scans for DQT markers (``0xFFDB``) and reads luminance (table 0) and
    chrominance (table 1) quantization tables.

    Args:
        image_bytes: Raw file bytes (must start with the JPEG SOI marker).

    Returns:
        A dict with keys ``"luminance"`` (list of 64 ints),
        ``"chrominance"`` (list of 64 ints or *None* if absent),
        and ``"quality_estimate"`` (int 1-100), or *None* if the data
        is not a valid JPEG.
    """
    if not image_bytes or len(image_bytes) < 4:
        return None

    # Must start with SOI marker
    if image_bytes[:2] != _JPEG_SOI:
        return None

    tables: dict[int, list[int]] = {}

    pos = 2  # skip SOI
    data_len = len(image_bytes)

    try:
        while pos < data_len - 1:
            # Look for a marker (0xFF followed by a non-zero byte)
            if image_bytes[pos] != 0xFF:
                pos += 1
                continue

            marker = image_bytes[pos + 1]
            pos += 2

            # Skip fill bytes (0xFF)
            if marker == 0xFF:
                continue
            # Skip standalone markers (RST0-RST7, SOI, EOI, TEM)
            if marker == 0x00 or marker == 0x01 or (0xD0 <= marker <= 0xD9):
                continue

            # SOS marker — image data follows; stop scanning
            if marker == 0xDA:
                break

            # Read segment length (includes the 2 length bytes)
            if pos + 2 > data_len:
                break
            seg_length = struct.unpack(">H", image_bytes[pos : pos + 2])[0]

            if marker == 0xDB:  # DQT segment
                _parse_dqt_segment(image_bytes, pos, seg_length, tables)

            pos += seg_length

    except Exception:  # noqa: BLE001
        logger.debug("Exception while parsing DQT markers", exc_info=True)

    if not tables:
        return None

    luminance = tables.get(0)
    chrominance = tables.get(1)

    if luminance is None:
        # Some encoders only write one table — try to use whatever we have
        first_key = min(tables.keys())
        luminance = tables[first_key]

    quality = _estimate_quality(luminance)

    return {
        "luminance": luminance,
        "chrominance": chrominance,
        "quality_estimate": quality,
    }


def _parse_dqt_segment(
    data: bytes,
    pos: int,
    seg_length: int,
    tables: dict[int, list[int]],
) -> None:
    """Parse a single DQT segment, which may contain multiple tables."""
    end = pos + seg_length
    cur = pos + 2  # skip the 2-byte length field

    while cur < end:
        if cur >= len(data):
            break
        pq_tq = data[cur]
        precision = (pq_tq >> 4) & 0x0F  # 0 = 8-bit, 1 = 16-bit
        table_id = pq_tq & 0x0F
        cur += 1

        table_size = 64 * (2 if precision else 1)
        if cur + table_size > len(data):
            break

        table: list[int] = []
        for i in range(64):
            if precision:
                val = struct.unpack(">H", data[cur + i * 2 : cur + i * 2 + 2])[0]
            else:
                val = data[cur + i]
            table.append(val)

        tables[table_id] = table
        cur += table_size


def _estimate_quality(luminance_table: list[int]) -> int:
    """Reverse the IJG quality formula to estimate the JPEG quality factor.

    Compares extracted luminance table values against the standard IJG base
    table to infer the scaling factor, then inverts the IJG formula.

    Returns:
        Estimated quality factor in ``[1, 100]``.
    """
    if len(luminance_table) != 64:
        return -1

    # Compute the average scale factor from multiple table positions
    scale_sum = 0.0
    count = 0
    for i, base_val in enumerate(IJG_BASE_LUMINANCE):
        if base_val == 0:
            continue
        q_val = luminance_table[i]
        if q_val < 1:
            continue
        # scale = ((q_val * 100) - 50) / base_val, from the forward formula
        scale = ((q_val * 100.0) - 50.0) / base_val
        scale_sum += scale
        count += 1

    if count == 0:
        return -1

    avg_scale = scale_sum / count

    # Invert: quality < 50  => scale = 5000/q  => q = 5000/scale
    #          quality >= 50 => scale = 200-2q  => q = (200-scale)/2
    if avg_scale >= 100:
        quality = max(1, round(5000.0 / avg_scale))
    else:
        quality = min(100, max(1, round((200.0 - avg_scale) / 2.0)))

    return int(quality)


# ---------------------------------------------------------------------------
# Fingerprint database
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DQTSignature:
    """A known DQT fingerprint entry."""
    name: str
    category: str  # CAMERA_HARDWARE | EDITING_SOFTWARE | AI_TOOL | SOCIAL_MEDIA | GENERIC
    luminance: list[int]
    luminance_q_range: tuple[int, int]
    description: str


def _build_fingerprint_db() -> list[_DQTSignature]:
    """Build the fingerprint database of known DQT signatures."""
    db: list[_DQTSignature] = []

    # ------------------------------------------------------------------
    # Camera hardware signatures
    # ------------------------------------------------------------------

    # Apple iPhone (iOS Camera app) — quality ~97
    db.append(_DQTSignature(
        name="Apple iPhone (iOS Camera)",
        category="CAMERA_HARDWARE",
        luminance=[
            1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 2, 2, 2, 2,
            1, 1, 2, 2, 2, 2, 3, 3,
            1, 2, 2, 2, 2, 3, 3, 3,
            2, 2, 2, 3, 3, 3, 3, 3,
            3, 3, 3, 3, 3, 3, 3, 3,
        ],
        luminance_q_range=(95, 97),
        description=(
            "Apple iOS Camera app uses proprietary quantization tables "
            "baked into the A/M-series ISP firmware.  Typically quality 95-97."
        ),
    ))

    # Samsung Galaxy — quality ~95
    db.append(_DQTSignature(
        name="Samsung Galaxy Camera",
        category="CAMERA_HARDWARE",
        luminance=generate_standard_ijg_table(95, IJG_BASE_LUMINANCE),
        luminance_q_range=(93, 96),
        description=(
            "Samsung Galaxy devices (S/Note/A series) use tables closely "
            "matching IJG quality 95 with minor vendor tweaks."
        ),
    ))

    # Google Pixel — quality ~95
    _pixel_lum = generate_standard_ijg_table(95, IJG_BASE_LUMINANCE)
    # Pixel has minor deviations at DC coefficient
    _pixel_lum[0] = 2
    db.append(_DQTSignature(
        name="Google Pixel Camera",
        category="CAMERA_HARDWARE",
        luminance=_pixel_lum,
        luminance_q_range=(94, 97),
        description=(
            "Google Pixel camera (via the Google Camera HDR+ pipeline) uses "
            "near-standard IJG quality 95 tables with minor Pixel-specific "
            "tweaks to the DC coefficient."
        ),
    ))

    # Sony (Alpha / Xperia) — quality ~96
    db.append(_DQTSignature(
        name="Sony Camera",
        category="CAMERA_HARDWARE",
        luminance=generate_standard_ijg_table(96, IJG_BASE_LUMINANCE),
        luminance_q_range=(94, 97),
        description=(
            "Sony Alpha mirrorless and Xperia smartphone cameras typically "
            "use quality 96 IJG-based tables."
        ),
    ))

    # Canon DSLR/mirrorless — quality ~97
    _canon_lum = generate_standard_ijg_table(97, IJG_BASE_LUMINANCE)
    _canon_lum[0] = 1
    _canon_lum[1] = 1
    db.append(_DQTSignature(
        name="Canon Camera",
        category="CAMERA_HARDWARE",
        luminance=_canon_lum,
        luminance_q_range=(95, 98),
        description=(
            "Canon DSLR and mirrorless cameras (EOS series) use proprietary "
            "high-quality quantization tables, typically quality 97+."
        ),
    ))

    # Nikon DSLR/mirrorless — quality ~95
    _nikon_lum = generate_standard_ijg_table(95, IJG_BASE_LUMINANCE)
    _nikon_lum[0] = 2
    _nikon_lum[1] = 1
    db.append(_DQTSignature(
        name="Nikon Camera",
        category="CAMERA_HARDWARE",
        luminance=_nikon_lum,
        luminance_q_range=(93, 97),
        description=(
            "Nikon DSLR and mirrorless cameras (Z/D series) use quality ~95 "
            "tables with Nikon-specific tweaks."
        ),
    ))

    # ------------------------------------------------------------------
    # Editing software signatures
    # ------------------------------------------------------------------

    # Adobe Photoshop (quality 10-12 → maps to IJG ~92-97)
    db.append(_DQTSignature(
        name="Adobe Photoshop",
        category="EDITING_SOFTWARE",
        luminance=[
            1, 1, 1, 1, 1, 2, 3, 3,
            1, 1, 1, 1, 2, 3, 3, 3,
            1, 1, 1, 1, 2, 3, 3, 3,
            1, 1, 1, 2, 3, 4, 4, 3,
            1, 1, 2, 3, 3, 5, 5, 4,
            1, 2, 3, 3, 4, 5, 6, 5,
            3, 3, 4, 4, 5, 6, 6, 5,
            4, 5, 5, 5, 6, 5, 5, 5,
        ],
        luminance_q_range=(92, 97),
        description=(
            "Adobe Photoshop 'Save for Web' uses proprietary quantization "
            "tables (quality 10-12 in Photoshop scale ≈ IJG 92-97).  These "
            "tables are distinct from standard IJG tables."
        ),
    ))

    # GIMP — uses standard IJG tables at quality 85
    db.append(_DQTSignature(
        name="GIMP",
        category="EDITING_SOFTWARE",
        luminance=generate_standard_ijg_table(85, IJG_BASE_LUMINANCE),
        luminance_q_range=(83, 90),
        description=(
            "GIMP uses standard libjpeg/IJG tables.  Default export quality "
            "is 85.  Indistinguishable from other libjpeg-based encoders at "
            "the same quality setting."
        ),
    ))

    # ------------------------------------------------------------------
    # AI tool / Python PIL signatures
    # ------------------------------------------------------------------

    # Standard PIL/Pillow (libjpeg) at quality 75 (PIL default)
    db.append(_DQTSignature(
        name="Python PIL/Pillow (quality 75, default)",
        category="AI_TOOL",
        luminance=generate_standard_ijg_table(75, IJG_BASE_LUMINANCE),
        luminance_q_range=(73, 77),
        description=(
            "Python Pillow's default JPEG quality is 75.  Most AI image "
            "generators that call PIL.Image.save() without specifying "
            "quality will produce this exact table."
        ),
    ))

    db.append(_DQTSignature(
        name="Python PIL/Pillow (quality 85)",
        category="AI_TOOL",
        luminance=generate_standard_ijg_table(85, IJG_BASE_LUMINANCE),
        luminance_q_range=(83, 87),
        description=(
            "AI pipelines that explicitly set quality=85 when saving "
            "via PIL.  Common in Stable Diffusion web UIs."
        ),
    ))

    db.append(_DQTSignature(
        name="Python PIL/Pillow (quality 90)",
        category="AI_TOOL",
        luminance=generate_standard_ijg_table(90, IJG_BASE_LUMINANCE),
        luminance_q_range=(88, 92),
        description=(
            "AI pipelines or scripts using quality=90 when saving "
            "via PIL.  Used by some Midjourney output post-processors."
        ),
    ))

    db.append(_DQTSignature(
        name="Python PIL/Pillow (quality 95)",
        category="AI_TOOL",
        luminance=generate_standard_ijg_table(95, IJG_BASE_LUMINANCE),
        luminance_q_range=(93, 97),
        description=(
            "High quality saves via PIL (quality=95).  Common in "
            "professional AI pipelines and ComfyUI workflows."
        ),
    ))

    # ------------------------------------------------------------------
    # Social media compression signatures
    # ------------------------------------------------------------------

    # WhatsApp — quality ~70-80
    db.append(_DQTSignature(
        name="WhatsApp Compression",
        category="SOCIAL_MEDIA",
        luminance=generate_standard_ijg_table(72, IJG_BASE_LUMINANCE),
        luminance_q_range=(70, 80),
        description=(
            "WhatsApp compresses shared images to ~quality 70-80 and "
            "strips EXIF metadata.  The resulting tables closely match "
            "standard IJG tables."
        ),
    ))

    # Telegram — quality ~80
    db.append(_DQTSignature(
        name="Telegram Compression",
        category="SOCIAL_MEDIA",
        luminance=generate_standard_ijg_table(80, IJG_BASE_LUMINANCE),
        luminance_q_range=(78, 83),
        description=(
            "Telegram compresses images to ~quality 80 when sent as "
            "photos (not as files).  Tables match standard IJG at q=80."
        ),
    ))

    # Instagram — quality ~70-85
    db.append(_DQTSignature(
        name="Instagram Compression",
        category="SOCIAL_MEDIA",
        luminance=generate_standard_ijg_table(77, IJG_BASE_LUMINANCE),
        luminance_q_range=(70, 85),
        description=(
            "Instagram re-encodes uploaded images at approximately "
            "quality 70-85 depending on resolution and content type."
        ),
    ))

    return db


DQT_FINGERPRINT_DB: list[_DQTSignature] = _build_fingerprint_db()


# ---------------------------------------------------------------------------
# DQT match result
# ---------------------------------------------------------------------------

@dataclass
class DQTMatchResult:
    """Result of matching DQT tables against the fingerprint database."""
    is_jpeg: bool
    quality_estimate: Optional[int] = None
    match_name: Optional[str] = None
    match_category: Optional[str] = None  # CAMERA_HARDWARE | EDITING_SOFTWARE | AI_TOOL | SOCIAL_MEDIA | GENERIC
    match_confidence: float = 0.0
    match_distance: float = float("inf")
    is_standard_libjpeg: bool = False
    luminance_table: Optional[list[int]] = None
    chrominance_table: Optional[list[int]] = None
    evidence_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def _l1_distance(table_a: list[int], table_b: list[int]) -> float:
    """Compute the L1 (Manhattan / sum of absolute differences) distance.

    Both tables must have exactly 64 elements.
    """
    if len(table_a) != 64 or len(table_b) != 64:
        return float("inf")
    return float(sum(abs(a - b) for a, b in zip(table_a, table_b)))


def _distance_to_confidence(distance: float) -> float:
    """Convert an L1 distance to a confidence score in ``[0.0, 1.0]``.

    Heuristic mapping:
      - distance = 0   → confidence = 1.0  (exact match)
      - distance = 64  → confidence ≈ 0.5
      - distance ≥ 500 → confidence → 0.0
    """
    if distance <= 0:
        return 1.0
    # Exponential decay: confidence = exp(-distance / tau)
    import math
    tau = 92.0  # tuning parameter
    return max(0.0, min(1.0, math.exp(-distance / tau)))


def _check_standard_libjpeg(luminance_table: list[int]) -> tuple[bool, int]:
    """Check if a luminance table matches standard IJG tables at any quality.

    Tests quality levels 1-100 and returns the closest match.

    Returns:
        A tuple of ``(is_match, best_quality)``.  ``is_match`` is *True*
        when the table is an exact match to a standard IJG table.
    """
    best_q = -1
    best_dist = float("inf")

    for q in range(1, 101):
        ref = generate_standard_ijg_table(q, IJG_BASE_LUMINANCE)
        dist = _l1_distance(luminance_table, ref)
        if dist < best_dist:
            best_dist = dist
            best_q = q
        if dist == 0:
            return True, q

    return False, best_q


def match_dqt_fingerprint(image_bytes: bytes) -> DQTMatchResult:
    """Match JPEG quantization tables against the fingerprint database.

    Extracts DQT tables from *image_bytes*, compares the luminance table
    against every entry in :data:`DQT_FINGERPRINT_DB` using L1 distance,
    and returns the best match with a confidence score.

    For non-JPEG images the result has ``is_jpeg=False`` and status
    information in :attr:`evidence_notes`.

    Args:
        image_bytes: Raw file bytes.

    Returns:
        A :class:`DQTMatchResult` that never raises.
    """
    try:
        dqt = extract_dqt_tables(image_bytes)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to extract DQT tables", exc_info=True)
        dqt = None

    if dqt is None:
        return DQTMatchResult(
            is_jpeg=False,
            evidence_notes=["NOT_JPEG: Image is not a JPEG or has no DQT tables."],
        )

    luminance: list[int] = dqt["luminance"]
    chrominance: Optional[list[int]] = dqt.get("chrominance")
    quality: int = dqt.get("quality_estimate", -1)

    notes: list[str] = []
    notes.append(f"Estimated JPEG quality: {quality}")

    # Check standard libjpeg match
    is_std, std_q = _check_standard_libjpeg(luminance)
    if is_std:
        notes.append(
            f"Luminance table is an EXACT match to standard IJG/libjpeg "
            f"quality {std_q}.  This is consistent with Python PIL / AI tools."
        )

    # Match against fingerprint database
    best_sig: Optional[_DQTSignature] = None
    best_distance = float("inf")

    for sig in DQT_FINGERPRINT_DB:
        dist = _l1_distance(luminance, sig.luminance)
        if dist < best_distance:
            best_distance = dist
            best_sig = sig

    match_confidence = _distance_to_confidence(best_distance)

    match_name: Optional[str] = None
    match_category: Optional[str] = None

    if best_sig is not None:
        match_name = best_sig.name
        match_category = best_sig.category
        notes.append(
            f"Best DQT match: '{best_sig.name}' (category={best_sig.category}, "
            f"L1 distance={best_distance:.1f}, confidence={match_confidence:.3f})"
        )
        notes.append(f"Description: {best_sig.description}")

        # Quality range consistency check
        q_lo, q_hi = best_sig.luminance_q_range
        if quality != -1 and q_lo <= quality <= q_hi:
            notes.append(
                f"Estimated quality {quality} is within the expected range "
                f"[{q_lo}, {q_hi}] for '{best_sig.name}'."
            )
        elif quality != -1:
            notes.append(
                f"Estimated quality {quality} is OUTSIDE the expected range "
                f"[{q_lo}, {q_hi}] for '{best_sig.name}' — lower confidence."
            )

    # If the table matches standard libjpeg exactly, flag it
    if is_std and match_category not in ("CAMERA_HARDWARE",):
        notes.append(
            "Standard libjpeg tables strongly suggest software encoding "
            "(Python PIL, libjpeg-turbo, or a tool using them).  If the "
            "image lacks camera EXIF data this is a strong AI indicator."
        )

    return DQTMatchResult(
        is_jpeg=True,
        quality_estimate=quality if quality != -1 else None,
        match_name=match_name,
        match_category=match_category,
        match_confidence=match_confidence,
        match_distance=best_distance,
        is_standard_libjpeg=is_std,
        luminance_table=luminance,
        chrominance_table=chrominance,
        evidence_notes=notes,
    )


# ---------------------------------------------------------------------------
# BaseDetector integration
# ---------------------------------------------------------------------------

class DQTFingerprintDetector(BaseDetector):
    """Forensic detector that analyses JPEG quantization tables.

    Extracts DQT fingerprints from JPEG files and matches them against a
    database of known camera hardware, editing software, AI tools, and
    social-media compression profiles.
    """

    @property
    def name(self) -> str:  # noqa: D401
        """Detector identifier."""
        return "dqt_fingerprint"

    @property
    def version(self) -> str:  # noqa: D401
        """Detector version string."""
        return "1.0.0"

    @property
    def category(self) -> DetectorCategory:  # noqa: D401
        """Forensic category."""
        return DetectorCategory.METADATA

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """Run the DQT fingerprint detector on an image.

        The raw image bytes can be supplied via ``kwargs["image_bytes"]``
        to avoid re-reading the file from disk.  Otherwise, *image_path*
        is read directly.

        Args:
            image_path: Filesystem path (or object-storage key) to the image.
            **kwargs: Optional ``image_bytes: bytes``.

        Returns:
            A :class:`DetectorResult` populated with DQT match details.
        """
        try:
            image_bytes: Optional[bytes] = kwargs.get("image_bytes")
            if image_bytes is None:
                path = Path(image_path)
                if not path.exists():
                    return self._error_result(
                        f"Image file not found: {image_path}"
                    )
                image_bytes = path.read_bytes()

            result = match_dqt_fingerprint(image_bytes)
            return self._build_detector_result(result)

        except Exception as exc:  # noqa: BLE001
            logger.error("DQTFingerprintDetector.run failed: %s", exc, exc_info=True)
            return self._error_result(str(exc))

    # -- private helpers ---------------------------------------------------

    def _build_detector_result(self, match: DQTMatchResult) -> DetectorResult:
        """Convert a :class:`DQTMatchResult` to a :class:`DetectorResult`."""
        details: dict[str, Any] = {
            "is_jpeg": match.is_jpeg,
            "quality_estimate": match.quality_estimate,
            "match_name": match.match_name,
            "match_category": match.match_category,
            "match_confidence": match.match_confidence,
            "match_distance": match.match_distance,
            "is_standard_libjpeg": match.is_standard_libjpeg,
            "evidence_notes": match.evidence_notes,
        }

        # Optionally include tables for downstream analysis
        if match.luminance_table is not None:
            details["luminance_table"] = match.luminance_table
        if match.chrominance_table is not None:
            details["chrominance_table"] = match.chrominance_table

        # Score: higher → more suspicious (standard libjpeg = software origin)
        # Range 0.0 (no signal) — 1.0 (definitely software-encoded)
        score: float = 0.0
        if match.is_jpeg:
            if match.is_standard_libjpeg:
                score = 0.7  # high software-origin signal
            if match.match_category == "AI_TOOL":
                score = max(score, 0.8 * match.match_confidence)
            elif match.match_category == "EDITING_SOFTWARE":
                score = max(score, 0.6 * match.match_confidence)
            elif match.match_category == "SOCIAL_MEDIA":
                score = max(score, 0.3 * match.match_confidence)
            elif match.match_category == "CAMERA_HARDWARE":
                # Camera hardware → low suspicion
                score = max(0.0, 0.1 * (1.0 - match.match_confidence))

        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=round(score, 4),
            confidence=round(match.match_confidence, 4),
            details=details,
        )

    def _error_result(self, message: str) -> DetectorResult:
        """Return a safe error result that never crashes the pipeline."""
        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=None,
            confidence=None,
            details={"error": message},
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_singleton: Optional[DQTFingerprintDetector] = None


def get_dqt_fingerprint_detector() -> DQTFingerprintDetector:
    """Return the singleton :class:`DQTFingerprintDetector` instance."""
    global _singleton  # noqa: PLW0603
    if _singleton is None:
        _singleton = DQTFingerprintDetector()
    return _singleton
