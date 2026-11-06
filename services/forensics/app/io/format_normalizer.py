"""
Universal Input Format Normalizer for Forensic Image Analysis.

This module provides robust, crash-safe normalization of uploaded images into
a standard 3-channel RGB byte stream suitable for consumption by the
forensic preprocessing pipeline (``preprocess()`` in ``preprocessing.py``).

Supported input formats
-----------------------
JPEG, PNG, WebP, BMP, TIFF, GIF (first frame), HEIC/HEIF (optional),
AVIF (via Pillow ≥10 or pillow-avif-plugin), and any other raster format
that Pillow can decode.  Colour modes RGBA, CMYK, L (grayscale), P
(palette), LA, PA, I, and F are all converted to RGB.

Safety guarantees
-----------------
* **Memory guard** – images larger than 8192 × 8192 are downscaled so that
  the longest side is at most 4096 pixels (aspect-ratio preserved).
* **Minimum dimension floor** – images smaller than 64 × 64 are rejected.
* **No exceptions** – every public entry-point returns a ``NormalizedResult``
  with an ``error`` field instead of raising.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from typing import Optional, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_DIMENSION = 8192
_DOWNSCALE_TARGET = 4096
_MIN_DIMENSION = 64
_JPEG_QUALITY = 95

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class NormalizedResult:
    """Container for the result of an image normalization operation.

    Attributes
    ----------
    image_bytes:
        The normalized RGB image encoded as JPEG (quality 95) or PNG bytes.
        Empty on failure.
    original_format:
        Detected source format (e.g. ``"JPEG"``, ``"PNG"``, ``"HEIC"``).
    original_mode:
        Original PIL colour mode before conversion (e.g. ``"RGBA"``).
    original_width:
        Width of the source image in pixels.
    original_height:
        Height of the source image in pixels.
    normalized_width:
        Width after normalization (may differ if downscaled).
    normalized_height:
        Height after normalization (may differ if downscaled).
    was_converted:
        ``True`` when the colour mode or format required conversion.
    was_downscaled:
        ``True`` when the memory guard triggered a resize.
    warnings:
        Non-fatal informational messages collected during processing.
    error:
        ``None`` on success; a human-readable error string on failure.
    """

    image_bytes: bytes = b""
    original_format: str = "UNKNOWN"
    original_mode: str = "UNKNOWN"
    original_width: int = 0
    original_height: int = 0
    normalized_width: int = 0
    normalized_height: int = 0
    was_converted: bool = False
    was_downscaled: bool = False
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Magic-byte format detection
# ---------------------------------------------------------------------------

# Mapping of magic-byte signatures → (format_name, min_header_length)
_MAGIC_TABLE: list[Tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
    (b"RIFF", "WEBP"),          # WebP (need to also check bytes 8-12)
    (b"BM", "BMP"),
    (b"II\x2a\x00", "TIFF"),   # Little-endian TIFF
    (b"MM\x00\x2a", "TIFF"),   # Big-endian TIFF
]


def _detect_heic_avif(raw_bytes: bytes) -> Optional[str]:
    """Detect HEIC/HEIF and AVIF via the ISO-BMFF ``ftyp`` box.

    Parameters
    ----------
    raw_bytes:
        First ≥12 bytes of the file.

    Returns
    -------
    ``"HEIC"``, ``"AVIF"``, or ``None``.
    """
    if len(raw_bytes) < 12:
        return None
    # ftyp box: bytes 4-8 must be b'ftyp'
    if raw_bytes[4:8] != b"ftyp":
        return None
    brand = raw_bytes[8:12].decode("ascii", errors="replace").strip("\x00").lower()
    heic_brands = {"heic", "heix", "hevc", "hevx", "mif1"}
    avif_brands = {"avif", "avis"}
    if brand in heic_brands:
        return "HEIC"
    if brand in avif_brands:
        return "AVIF"
    return None


def is_supported_format(raw_bytes: bytes) -> Tuple[bool, str]:
    """Detect the image format from magic bytes without fully loading the file.

    Parameters
    ----------
    raw_bytes:
        Raw uploaded file content (or at least the first 32 bytes).

    Returns
    -------
    tuple[bool, str]
        ``(True, format_name)`` if recognised, ``(False, "UNKNOWN")`` otherwise.
    """
    if not raw_bytes or len(raw_bytes) < 2:
        return False, "UNKNOWN"

    # --- JPEG: starts with 0xFF 0xD8 ---
    if raw_bytes[:2] == b"\xff\xd8":
        return True, "JPEG"

    # --- Fixed-prefix signatures ---
    for magic, fmt in _MAGIC_TABLE:
        if raw_bytes[: len(magic)] == magic:
            # WebP needs an extra check for the WEBP marker at offset 8
            if fmt == "WEBP":
                if len(raw_bytes) >= 12 and raw_bytes[8:12] == b"WEBP":
                    return True, "WEBP"
                continue
            return True, fmt

    # --- ISO-BMFF container (HEIC / AVIF) ---
    iso_fmt = _detect_heic_avif(raw_bytes)
    if iso_fmt is not None:
        return True, iso_fmt

    return False, "UNKNOWN"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_register_heif() -> bool:
    """Attempt to register the ``pillow-heif`` opener.

    Returns ``True`` if HEIC/HEIF support is now available.
    """
    try:
        from pillow_heif import register_heif_opener  # type: ignore[import-untyped]

        register_heif_opener()
        return True
    except ImportError:
        return False


def _composite_alpha_on_white(img: Image.Image) -> Image.Image:
    """Flatten an RGBA / LA / PA image onto a white background.

    Parameters
    ----------
    img:
        A PIL ``Image`` with an alpha channel.

    Returns
    -------
    Image.Image
        A new image in ``RGB`` mode.
    """
    background = Image.new("RGB", img.size, (255, 255, 255))
    # Ensure source is RGBA for alpha_composite
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    background.paste(img, mask=img.split()[3])
    return background


def _convert_to_rgb(img: Image.Image, warnings: list[str]) -> Image.Image:
    """Convert *any* PIL mode to standard 3-channel RGB.

    Parameters
    ----------
    img:
        Source image in any mode.
    warnings:
        Mutable list to which informational messages are appended.

    Returns
    -------
    Image.Image
        The image in ``RGB`` mode.
    """
    mode = img.mode

    if mode == "RGB":
        return img

    if mode in ("RGBA", "LA", "PA"):
        warnings.append(f"Alpha channel removed (mode {mode} → RGB, composited on white)")
        return _composite_alpha_on_white(img)

    if mode == "CMYK":
        warnings.append("CMYK → RGB colour-space conversion applied")
        return img.convert("RGB")

    if mode == "P":
        # Palette may contain transparency
        if "transparency" in img.info:
            warnings.append("Palette transparency composited on white (P → RGBA → RGB)")
            return _composite_alpha_on_white(img.convert("RGBA"))
        warnings.append("Palette mode (P) → RGB conversion applied")
        return img.convert("RGB")

    if mode == "L":
        warnings.append("Grayscale (L) → RGB conversion applied")
        return img.convert("RGB")

    if mode in ("I", "F"):
        warnings.append(f"Mode {mode} → L → RGB conversion applied")
        return img.convert("L").convert("RGB")

    if mode == "1":
        warnings.append("Bi-level (1) → RGB conversion applied")
        return img.convert("RGB")

    # Fallback for any exotic mode Pillow supports
    warnings.append(f"Uncommon mode '{mode}' → RGB conversion attempted")
    try:
        return img.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Cannot convert mode '{mode}' to RGB: {exc}") from exc


def _apply_memory_guard(
    img: Image.Image,
    warnings: list[str],
) -> Tuple[Image.Image, bool]:
    """Down-scale if either dimension exceeds ``_MAX_DIMENSION``.

    The image is resized so that its longest side equals ``_DOWNSCALE_TARGET``
    while preserving the aspect ratio.

    Parameters
    ----------
    img:
        The image to check.
    warnings:
        Mutable warning list.

    Returns
    -------
    tuple[Image.Image, bool]
        ``(possibly_resized_image, was_downscaled)``
    """
    w, h = img.size
    if w <= _MAX_DIMENSION and h <= _MAX_DIMENSION:
        return img, False

    longest = max(w, h)
    scale = _DOWNSCALE_TARGET / longest
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    warnings.append(
        f"Memory guard: downscaled from {w}×{h} to {new_w}×{new_h} "
        f"(longest side capped at {_DOWNSCALE_TARGET})"
    )
    return img.resize((new_w, new_h), Image.LANCZOS), True


def _encode_output(
    img: Image.Image,
    had_alpha: bool,
) -> bytes:
    """Encode the final RGB image as JPEG or PNG bytes.

    PNG is used when the *source* image had transparency (even though the
    output is opaque RGB composited on white) to signal to downstream
    consumers that transparency was originally present.  Otherwise JPEG at
    quality 95 is used for smaller file size.

    Parameters
    ----------
    img:
        The final ``RGB`` image.
    had_alpha:
        ``True`` if the original source image had an alpha channel.

    Returns
    -------
    bytes
        Encoded image bytes.
    """
    buf = io.BytesIO()
    if had_alpha:
        img.save(buf, format="PNG")
    else:
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_image_bytes(raw_bytes: bytes) -> NormalizedResult:
    """Normalize arbitrary uploaded image bytes into standard 3-channel RGB.

    This is the primary entry-point for the forensic ingestion pipeline.
    It will **never** raise an exception — any failure is reported via the
    ``error`` field of the returned :class:`NormalizedResult`.

    Parameters
    ----------
    raw_bytes:
        The raw bytes of the uploaded image file.

    Returns
    -------
    NormalizedResult
        A fully-populated result dataclass.
    """
    result = NormalizedResult()

    # ------------------------------------------------------------------
    # 0.  Basic input validation
    # ------------------------------------------------------------------
    if not raw_bytes:
        result.error = "Empty input: no image bytes provided."
        return result

    # ------------------------------------------------------------------
    # 1.  Detect format from magic bytes
    # ------------------------------------------------------------------
    supported, detected_format = is_supported_format(raw_bytes)
    result.original_format = detected_format

    # ------------------------------------------------------------------
    # 2.  HEIC / HEIF: attempt to register the pillow-heif opener
    # ------------------------------------------------------------------
    if detected_format == "HEIC":
        if not _try_register_heif():
            result.error = (
                "HEIC/HEIF format detected but 'pillow-heif' is not installed.  "
                "Install it with:  pip install pillow-heif"
            )
            result.warnings.append("HEIC support not available")
            return result

    # ------------------------------------------------------------------
    # 3.  Open with Pillow
    # ------------------------------------------------------------------
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()  # force full decode (catches truncated files)
    except UnidentifiedImageError:
        result.error = (
            f"Pillow cannot identify the image. Detected header format: "
            f"'{detected_format}'.  The file may be corrupt or unsupported."
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result.error = f"Failed to open image: {exc}"
        return result

    # If Pillow identified a format, prefer it over magic-byte detection
    pil_format = (img.format or "").upper()
    if pil_format:
        result.original_format = pil_format

    result.original_mode = img.mode
    result.original_width, result.original_height = img.size

    # ------------------------------------------------------------------
    # 4.  Animated GIF — use first frame only
    # ------------------------------------------------------------------
    try:
        if getattr(img, "is_animated", False):
            img.seek(0)
            result.warnings.append(
                f"Animated image ({getattr(img, 'n_frames', '?')} frames): "
                f"using first frame only"
            )
    except Exception:  # noqa: BLE001
        pass  # seek(0) is a no-op on failure; already on frame 0

    # ------------------------------------------------------------------
    # 5.  EXIF auto-rotation
    # ------------------------------------------------------------------
    try:
        img = ImageOps.exif_transpose(img)  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        result.warnings.append("Could not apply EXIF orientation; image may be rotated")

    # ------------------------------------------------------------------
    # 6.  Minimum dimension check (post-rotation)
    # ------------------------------------------------------------------
    w, h = img.size
    if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
        result.error = (
            f"Image too small ({w}×{h}). "
            f"Minimum accepted dimensions are {_MIN_DIMENSION}×{_MIN_DIMENSION}."
        )
        return result

    # ------------------------------------------------------------------
    # 7.  Track whether the source had alpha
    # ------------------------------------------------------------------
    had_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )

    # ------------------------------------------------------------------
    # 8.  Convert to RGB
    # ------------------------------------------------------------------
    try:
        img = _convert_to_rgb(img, result.warnings)
    except Exception as exc:  # noqa: BLE001
        result.error = f"Colour-mode conversion failed: {exc}"
        return result

    result.was_converted = (
        result.original_mode != "RGB" or result.original_format != pil_format
    )

    # ------------------------------------------------------------------
    # 9.  Memory guard (downscale oversized images)
    # ------------------------------------------------------------------
    try:
        img, was_downscaled = _apply_memory_guard(img, result.warnings)
        result.was_downscaled = was_downscaled
    except Exception as exc:  # noqa: BLE001
        result.error = f"Downscaling failed: {exc}"
        return result

    result.normalized_width, result.normalized_height = img.size

    # ------------------------------------------------------------------
    # 10. Encode output bytes
    # ------------------------------------------------------------------
    try:
        result.image_bytes = _encode_output(img, had_alpha)
    except Exception as exc:  # noqa: BLE001
        result.error = f"Failed to encode normalized image: {exc}"
        return result

    return result
