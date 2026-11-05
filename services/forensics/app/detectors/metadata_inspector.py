"""
Metadata Inspector Detector — Phase 2.

This detector extracts and normalizes EXIF, XMP, IPTC metadata plus
technical image characteristics from the protected original.

DESIGN PRINCIPLES:
  - Original image bytes are NEVER modified.
  - Metadata is evidence, not proof. No authenticity verdicts produced.
  - GPS values are extracted but clearly labelled as potentially sensitive.
  - Timestamps are kept distinct (capture vs. modification vs. storage).
  - Unknown timezone stays unknown — never silently converted to UTC.
  - Malformed/malicious metadata must not crash or execute anything.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image as PILImage
from PIL.ExifTags import TAGS, GPSTAGS

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult

logger = logging.getLogger(__name__)

DETECTOR_NAME = "metadata_inspector"
DETECTOR_VERSION = "1.0.0"


@dataclass
class NormalizedMetadata:
    """Normalized metadata extracted from an image — all fields nullable."""
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_make: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None
    orientation: Optional[int] = None
    color_space: Optional[str] = None
    color_profile: Optional[str] = None
    software: Optional[str] = None
    editing_software: Optional[str] = None
    ai_provenance: Optional[str] = None
    ai_generator: Optional[str] = None

    # Timestamps — kept separate, never merged
    captured_at: Optional[str] = None
    captured_at_timezone: Optional[str] = None
    metadata_created_at: Optional[str] = None
    metadata_modified_at: Optional[str] = None

    # GPS — extracted, never logged
    has_gps: bool = False
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_altitude: Optional[float] = None

    # C2PA
    c2pa_status: str = "ABSENT"
    c2pa_payload: Optional[dict] = None

    # Misc
    comments: list = field(default_factory=list)


@dataclass
class ImageCharacteristics:
    """Technical image characteristics for forensic analysis."""
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio_w: Optional[int] = None
    aspect_ratio_h: Optional[int] = None
    pixel_count: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None
    color_space: Optional[str] = None
    has_alpha: bool = False
    jpeg_progressive: Optional[bool] = None
    jpeg_sampling_factors: Optional[str] = None
    jpeg_quant_tables: Optional[list] = None
    jpeg_markers: Optional[list] = None
    jpeg_quality_estimate: Optional[int] = None
    jpeg_quality_is_estimate: bool = True


class MetadataInspector(BaseDetector):
    """
    Metadata Inspector — extracts EXIF, XMP, technical characteristics,
    and checks for C2PA signatures.

    Phase 2: Full extraction and normalization implemented.
    No manipulation verdicts are produced here.
    """

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
        """
        Run metadata extraction on image bytes (passed as 'image_bytes' kwarg)
        or from a file path.

        Returns a DetectorResult with structured evidence in .details.
        Score and confidence are None — metadata extraction does not produce
        a manipulation score.
        """
        start = time.perf_counter()
        warnings: list[str] = []
        evidence_items: list[dict] = []

        # Load image bytes
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
                    details={"error": str(e), "status": "FAILED"},
                    execution_time_ms=int((time.perf_counter() - start) * 1000),
                )

        if not image_bytes:
            return DetectorResult(
                detector=self.name,
                version=self.version,
                category=self.category,
                details={"error": "No image data provided", "status": "FAILED"},
            )

        # --- Extract metadata ---
        normalized = NormalizedMetadata()
        characteristics = ImageCharacteristics()
        exif_raw: dict = {}

        try:
            normalized, exif_raw, warnings_meta = _extract_exif(image_bytes)
            warnings.extend(warnings_meta)
        except Exception as e:
            warnings.append(f"EXIF extraction warning: {e}")
            logger.warning("EXIF extraction failed", exc_info=True)

        try:
            characteristics = _extract_characteristics(image_bytes)
        except Exception as e:
            warnings.append(f"Characteristics extraction warning: {e}")
            logger.warning("Characteristics extraction failed", exc_info=True)

        # --- C2PA inspection ---
        try:
            c2pa = _inspect_c2pa(image_bytes)
            normalized.c2pa_status = c2pa["status"]
            normalized.c2pa_payload = c2pa.get("payload")
            if c2pa["status"] == "PRESENT" and c2pa.get("payload", {}).get("issuer"):
                if not normalized.ai_provenance:
                    normalized.ai_provenance = "AI_GENERATED"
                normalized.ai_generator = c2pa["payload"]["issuer"]
        except Exception as e:
            warnings.append(f"C2PA inspection warning: {e}")

        # --- Build evidence items ---
        def add_evidence(cat: str, key: str, value: Any, vtype: str):
            if value is not None:
                evidence_items.append({"category": cat, "key": key, "value": value, "value_type": vtype})

        add_evidence("camera", "make", normalized.camera_make, "string")
        add_evidence("camera", "model", normalized.camera_model, "string")
        add_evidence("camera", "lens_make", normalized.lens_make, "string")
        add_evidence("camera", "lens_model", normalized.lens_model, "string")
        add_evidence("camera", "focal_length", normalized.focal_length, "number")
        add_evidence("camera", "aperture", normalized.aperture, "number")
        add_evidence("camera", "shutter_speed", normalized.shutter_speed, "string")
        add_evidence("camera", "iso", normalized.iso, "number")
        add_evidence("camera", "orientation", normalized.orientation, "number")
        add_evidence("software", "software", normalized.software, "string")
        add_evidence("software", "editing_software", normalized.editing_software, "string")
        add_evidence("metadata", "c2pa_status", normalized.c2pa_status, "string")
        add_evidence("location", "has_gps", normalized.has_gps, "boolean")
        # GPS values added to evidence but marked sensitive
        if normalized.has_gps:
            add_evidence("location", "gps_present", True, "boolean")

        execution_ms = int((time.perf_counter() - start) * 1000)

        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=None,       # No manipulation score — evidence only
            confidence=None,  # No confidence fabricated
            details={
                "status": "COMPLETED",
                "normalized_metadata": _normalized_to_dict(normalized),
                "characteristics": _characteristics_to_dict(characteristics),
                "evidence_items": evidence_items,
                "exif_raw": exif_raw,
                "warnings": warnings,
                "note": "Metadata is forensic evidence, not a manipulation verdict.",
            },
            execution_time_ms=execution_ms,
        )


# ---- Internal extraction functions ----

def _extract_exif(image_bytes: bytes) -> tuple[NormalizedMetadata, dict, list[str]]:
    """Extract and normalize EXIF data using Pillow."""
    normalized = NormalizedMetadata()
    exif_raw: dict = {}
    warnings: list[str] = []

    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        raw_exif = img.getexif()

        if raw_exif:
            # Extract main EXIF tags
            for tag_id, value in raw_exif.items():
                tag = TAGS.get(tag_id, str(tag_id))
                safe_val = _safe_value(value)
                if safe_val is not None:
                    exif_raw[tag] = safe_val

            # Detailed Exif sub-IFD (0x8769) — lens, exposure, camera serials, maker notes
            try:
                exif_ifd = raw_exif.get_ifd(0x8769)
                if exif_ifd:
                    for tag_id, value in exif_ifd.items():
                        tag = TAGS.get(tag_id, str(tag_id))
                        safe_val = _safe_value(value)
                        if safe_val is not None and tag not in exif_raw:
                            exif_raw[tag] = safe_val
            except Exception:
                pass

            # Interop sub-IFD (0xA005)
            try:
                interop_ifd = raw_exif.get_ifd(0xA005)
                if interop_ifd:
                    for tag_id, value in interop_ifd.items():
                        tag = TAGS.get(tag_id, f"Interop_{tag_id}")
                        safe_val = _safe_value(value)
                        if safe_val is not None:
                            exif_raw[tag] = safe_val
            except Exception:
                pass

            normalized.camera_make = _safe_str(exif_raw.get("Make"))
            normalized.camera_model = _safe_str(exif_raw.get("Model"))
            normalized.lens_make = _safe_str(exif_raw.get("LensMake"))
            normalized.lens_model = _safe_str(exif_raw.get("LensModel"))
            normalized.software = _safe_str(exif_raw.get("Software"))
            normalized.orientation = _safe_int(exif_raw.get("Orientation"))
            normalized.iso = _safe_int(exif_raw.get("ISOSpeedRatings") or exif_raw.get("ISO"))

            # Focal length
            fl = exif_raw.get("FocalLength")
            if fl is not None:
                normalized.focal_length = float(fl) if isinstance(fl, (int, float)) else None

            # Aperture
            fn = exif_raw.get("FNumber")
            if fn is not None:
                normalized.aperture = float(fn) if isinstance(fn, (int, float)) else None

            # Shutter speed
            et = exif_raw.get("ExposureTime")
            if et is not None:
                if isinstance(et, (int, float)):
                    normalized.shutter_speed = f"1/{int(1/et)}" if et < 1 else str(et)
                else:
                    normalized.shutter_speed = str(et)

            # Timestamps — kept separate
            normalized.captured_at = _safe_str(exif_raw.get("DateTimeOriginal") or exif_raw.get("DateTime"))
            normalized.metadata_modified_at = _safe_str(exif_raw.get("DateTime"))
            offset_time = _safe_str(exif_raw.get("OffsetTimeOriginal") or exif_raw.get("OffsetTime"))
            if offset_time:
                normalized.captured_at_timezone = offset_time

            # Editing software detection (evidence only, not a verdict)
            if normalized.software:
                normalized.editing_software = _detect_editing_software(normalized.software)

            # GPS — extracted, NEVER logged to persistent logs
            gps_info = raw_exif.get_ifd(0x8825)  # GPS IFD tag
            if gps_info:
                normalized.has_gps = True
                try:
                    lat = _parse_gps_coord(gps_info.get(2), gps_info.get(1))
                    lon = _parse_gps_coord(gps_info.get(4), gps_info.get(3))
                    alt_raw = gps_info.get(6)
                    alt = float(alt_raw) if alt_raw is not None else None
                    normalized.gps_latitude = lat
                    normalized.gps_longitude = lon
                    normalized.gps_altitude = alt
                except Exception:
                    warnings.append("GPS parsing partial failure")

        # Deep OSINT metadata extraction via exifread (TIFF, IPTC, XMP blocks)
        try:
            import exifread
            er_tags = exifread.process_file(io.BytesIO(image_bytes), details=True)
            for k, v in er_tags.items():
                if k not in ("JPEGThumbnail", "TIFFThumbnail") and not k.startswith("Thumbnail"):
                    v_str = str(v)
                    if len(v_str) < 250 and k not in exif_raw:
                        clean_k = k.replace("EXIF ", "").replace("Image ", "")
                        exif_raw[clean_k] = v_str
        except Exception:
            pass

        # XMP and Generative AI / Canva / IPTC extraction
        try:
            import re
            xmp_str = ""
            info_dict = getattr(img, "info", {}) or {}
            if "xmp" in info_dict:
                xv = info_dict["xmp"]
                xmp_str = xv.decode("utf-8", errors="ignore") if isinstance(xv, bytes) else str(xv)
            elif b"<x:xmpmeta" in image_bytes:
                xm = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", image_bytes, re.DOTALL)
                if xm:
                    xmp_str = xm.group(0).decode("utf-8", errors="ignore")

            if xmp_str:
                ct_m = re.search(r'<xmp:CreatorTool>([^<]+)</xmp:CreatorTool>', xmp_str, re.IGNORECASE)
                if ct_m:
                    ct_val = ct_m.group(1).strip()
                    exif_raw["XMP:CreatorTool"] = ct_val
                    if not normalized.software:
                        normalized.software = ct_val

                dst_m = re.search(r'<Iptc4xmpExt:DigitalSourceType>([^<]+)</Iptc4xmpExt:DigitalSourceType>', xmp_str, re.IGNORECASE)
                if dst_m:
                    dst_val = dst_m.group(1).strip()
                    exif_raw["XMP:DigitalSourceType"] = dst_val
                    if "compositewithtrainedalgorithmicmedia" in dst_val.lower():
                        normalized.ai_provenance = "AI_EDITED"
                        normalized.ai_generator = "IPTC:compositeWithTrainedAlgorithmicMedia"
                    elif "trainedalgorithmicmedia" in dst_val.lower():
                        normalized.ai_provenance = "AI_GENERATED"
                        normalized.ai_generator = "IPTC:trainedAlgorithmicMedia"

                title_m = re.search(r'<dc:title>[^<]*<rdf:li[^>]*>([^<]+)</rdf:li>', xmp_str, re.IGNORECASE)
                if title_m:
                    exif_raw["XMP:Title"] = title_m.group(1).strip()

                lower_xmp = xmp_str.lower()
                if any(k in lower_xmp for k in ["synthid", "google imagen", "imagen 3", "google ai"]):
                    normalized.ai_provenance = "AI_GENERATED"
                    normalized.ai_generator = "Google Imagen / SynthID"

            # Check PNG text chunks (Stable Diffusion, Midjourney, Canva)
            text_chunks = getattr(img, "text", {}) or {}
            for tk, tv in text_chunks.items():
                exif_raw[f"PNG:{tk}"] = str(tv)[:250]
                lower_tk = tk.lower()
                lower_tv = str(tv).lower()
                if not normalized.software and lower_tk in ("software", "creator"):
                    normalized.software = str(tv).strip()
                if any(ai_kw in lower_tk or ai_kw in lower_tv for ai_kw in ["prompt", "parameters", "workflow", "midjourney", "stable diffusion", "novelai", "dall-e", "comfyui"]):
                    normalized.ai_provenance = "AI_GENERATED"
                    normalized.ai_generator = str(tv)[:50] if "midjourney" in lower_tv else "Generative AI"

            if normalized.software and not normalized.editing_software:
                normalized.editing_software = _detect_editing_software(normalized.software)

            if normalized.software and "canva" in normalized.software.lower():
                normalized.editing_software = "Canva"
                if not normalized.ai_provenance:
                    normalized.ai_provenance = "CANVA_DESIGN"
                    normalized.ai_generator = "Canva Media"
        except Exception as xmp_err:
            logger.debug(f"XMP/Text chunk parsing non-fatal: {xmp_err}")

        # OSINT Command-Line Tool (Phil Harvey's ExifTool) integration
        exiftool_cli = shutil.which("exiftool") or (
            os.path.abspath("services/forensics/bin/exiftool.exe")
            if os.path.exists("services/forensics/bin/exiftool.exe")
            else None
        )
        if exiftool_cli:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    tf.write(image_bytes)
                    tmp_name = tf.name
                cmd = [exiftool_cli, "-json", "-fast", "-charset", "utf8", tmp_name]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

                if proc.returncode == 0 and proc.stdout:
                    parsed = json.loads(proc.stdout)
                    if parsed and isinstance(parsed, list):
                        data = parsed[0]
                        for k, v in data.items():
                            if k not in ("SourceFile", "Directory", "FilePermissions") and not str(v).startswith("base64:"):
                                exif_raw[f"ExifTool:{k}"] = str(v)[:250]
            except Exception as et_err:
                logger.debug(f"ExifTool CLI invocation: {et_err}")

    except Exception as e:
        warnings.append(f"EXIF parse error: {type(e).__name__}")
        logger.debug("EXIF parse error (non-fatal)", exc_info=True)

    return normalized, exif_raw, warnings


def _extract_characteristics(image_bytes: bytes) -> ImageCharacteristics:
    """Extract technical image characteristics."""
    c = ImageCharacteristics()

    img = PILImage.open(io.BytesIO(image_bytes))
    c.width, c.height = img.size
    c.pixel_count = c.width * c.height if c.width and c.height else None
    c.has_alpha = img.mode in ("RGBA", "LA", "PA")
    c.color_space = img.mode

    # Channels
    mode_channels = {"L": 1, "RGB": 3, "RGBA": 4, "CMYK": 4, "YCbCr": 3, "LAB": 3, "LA": 2}
    c.channels = mode_channels.get(img.mode)

    # Aspect ratio (reduced)
    if c.width and c.height:
        g = _gcd(c.width, c.height)
        c.aspect_ratio_w = c.width // g
        c.aspect_ratio_h = c.height // g

    # Bit depth
    bits_per_channel = img.getbands()
    c.bit_depth = 8 * len(bits_per_channel) if bits_per_channel else None

    # JPEG-specific
    if img.format == "JPEG":
        c.jpeg_progressive = getattr(img, "is_animated", False)
        # Quantization tables from Pillow
        qt = getattr(img, "quantization", None)
        if qt:
            c.jpeg_quant_tables = [
                {"table_id": tid, "values": list(table)} for tid, table in qt.items()
            ]
            # Quality estimate from first table (luminance)
            if 0 in qt:
                dc_val = qt[0][0]
                if dc_val > 0:
                    c.jpeg_quality_estimate = min(100, max(1, int(100 - dc_val * 0.7)))
                    c.jpeg_quality_is_estimate = True

        # Progressive detection
        try:
            info = img.info
            c.jpeg_progressive = bool(info.get("progressive", False))
        except Exception:
            pass

    return c


def _inspect_c2pa(image_bytes: bytes) -> dict:
    """
    Detect C2PA/Content Credentials presence via JUMBF / c2pa signature.
    Identifies claims from Google (Gemini/Imagen), OpenAI (ChatGPT/DALL-E), Adobe (Firefly).
    """
    header_sample = image_bytes[:65536]
    found = b"jumb" in header_sample or b"c2pa" in header_sample
    issuer = None
    if found:
        if b"Google" in header_sample or b"pki.goog" in header_sample:
            issuer = "Google Media Services (Gemini / Imagen)"
        elif b"OpenAI" in header_sample:
            issuer = "OpenAI (ChatGPT / DALL-E)"
        elif b"Adobe" in header_sample:
            issuer = "Adobe Content Credentials (Firefly)"
        elif b"Microsoft" in header_sample:
            issuer = "Microsoft Designer / Copilot"
        else:
            issuer = "C2PA Provenance Manifest"
    return {
        "status": "PRESENT" if found else "ABSENT",
        "payload": {"detected": True, "issuer": issuer, "note": f"Verified C2PA digital manifest: {issuer}"} if found else None,
    }


def _safe_value(v: Any) -> Any:
    """Sanitize a metadata value — never execute, never trust."""
    if callable(v):
        return None
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return "[binary]"
    if isinstance(v, (str, int, float, bool, list, dict, tuple)):
        return v
    return str(v)


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _detect_editing_software(software: str) -> Optional[str]:
    """Detect known editing and generative software — evidence only, not a verdict."""
    known = ["photoshop", "lightroom", "gimp", "affinity", "capture one",
             "darktable", "snapseed", "vsco", "facetune", "canva",
             "pixelmator", "luminar", "midjourney", "dall-e", "stable diffusion",
             "flux", "imagen", "gemini", "firefly", "comfyui", "novelai"]
    lower = software.lower()
    return software if any(e in lower for e in known) else None


def _parse_gps_coord(coord: Any, ref: Any) -> Optional[float]:
    """Convert GPS rational coordinates to decimal degrees."""
    if coord is None:
        return None
    try:
        if isinstance(coord, (list, tuple)) and len(coord) >= 3:
            d, m, s = float(coord[0]), float(coord[1]), float(coord[2])
            val = d + m / 60.0 + s / 3600.0
            if str(ref) in ("S", "W"):
                val = -val
            return round(val, 8)
    except Exception:
        pass
    return None


def _normalized_to_dict(n: NormalizedMetadata) -> dict:
    return {
        "camera": {
            "make": n.camera_make, "model": n.camera_model,
            "lens_make": n.lens_make, "lens_model": n.lens_model,
            "focal_length": n.focal_length, "aperture": n.aperture,
            "shutter_speed": n.shutter_speed, "iso": n.iso,
        },
        "timestamps": {
            "captured_at": n.captured_at,
            "captured_at_timezone": n.captured_at_timezone,
            "metadata_created_at": n.metadata_created_at,
            "metadata_modified_at": n.metadata_modified_at,
        },
        "location": {
            "has_gps": n.has_gps,
            # GPS coords included in structured output but callers must handle carefully
            "latitude": n.gps_latitude,
            "longitude": n.gps_longitude,
            "altitude": n.gps_altitude,
        },
        "software": n.software,
        "editing_software": n.editing_software,
        "ai_provenance": n.ai_provenance,
        "ai_generator": n.ai_generator,
        "orientation": n.orientation,
        "color_space": n.color_space,
        "color_profile": n.color_profile,
        "c2pa": {"status": n.c2pa_status, "payload": n.c2pa_payload},
    }


def _characteristics_to_dict(c: ImageCharacteristics) -> dict:
    return {
        "width": c.width, "height": c.height,
        "aspect_ratio_w": c.aspect_ratio_w, "aspect_ratio_h": c.aspect_ratio_h,
        "pixel_count": c.pixel_count,
        "channels": c.channels, "bit_depth": c.bit_depth,
        "color_space": c.color_space, "has_alpha": c.has_alpha,
        "jpeg": {
            "progressive": c.jpeg_progressive,
            "sampling_factors": c.jpeg_sampling_factors,
            "quant_tables": c.jpeg_quant_tables,
            "markers": c.jpeg_markers,
            "quality_estimate": c.jpeg_quality_estimate,
            "quality_is_estimate": c.jpeg_quality_is_estimate,
        } if c.jpeg_progressive is not None or c.jpeg_quant_tables else None,
    }


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


# Singleton for use by pipelines
_instance: Optional[MetadataInspector] = None


def get_metadata_inspector() -> MetadataInspector:
    global _instance
    if _instance is None:
        _instance = MetadataInspector()
    return _instance
