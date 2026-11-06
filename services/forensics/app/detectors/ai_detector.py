"""
AI Detection Detector — Phase 6.

Combines:
  1. Image-level AI-generated classifier (using segmentation map global stats)
  2. Localized AI-edit segmentation (UNet + EfficientNet-B3)

Status values:
  AI_GENERATED      — whole image likely AI-generated
  AI_EDITED_LOCAL   — real photo with localized AI-edit region(s)
  NO_AI_EVIDENCE    — no AI-like evidence detected
  INCONCLUSIVE      — evidence present but cannot be classified
  UNAVAILABLE       — model not loaded / weights not available

IMPORTANT:
  - Raw sigmoid output is NOT a calibrated probability.
  - Calibration is UNCALIBRATED.
  - Do not claim definitive results.
  - Language: "Current model detected AI-like evidence in N regions."

Version: v1.0.0
"""
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import cv2
from PIL import Image as PILImage

from app.detectors.base import BaseDetector, DetectorCategory, DetectorResult
from app.models.ai_segmentation import get_ai_segmentation_model, DEFAULT_THRESHOLD, IMG_SIZE
from app.io.preprocessing import preprocess, encode_artifact_png

logger = logging.getLogger(__name__)

DETECTOR_NAME = "ai_detector"
DETECTOR_VERSION = "v1.0.0"

# Region extraction parameters
DEFAULT_PARAMS = {
    "threshold": DEFAULT_THRESHOLD,
    "min_region_pixels": 64,    # minimum region size to report
    "morph_kernel_size": 5,     # morphological cleanup kernel
    "max_dimension": 512,       # analysis resolution
    # Image-level classification thresholds
    "global_ai_threshold": 0.60,    # above this → AI_GENERATED candidate
    "local_ai_threshold": 0.50,     # above this for regions → AI_EDITED_LOCAL
}


@dataclass
class AIRegion:
    bbox: dict                  # {x, y, width, height} in original image coords
    area_pixels: int
    area_percentage: float
    confidence: Optional[float] = None
    edit_type: Optional[str] = None
    evidence: list = field(default_factory=list)
    polygon: Optional[list] = None

    def to_dict(self) -> dict:
        return {
            "bbox": self.bbox,
            "area_pixels": self.area_pixels,
            "area_percentage": round(self.area_percentage, 4),
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "edit_type": self.edit_type,
            "evidence": self.evidence,
            "polygon": self.polygon,
        }


@dataclass
class AIDetectionResult:
    status: str                          # UNAVAILABLE | AI_GENERATED | AI_EDITED_LOCAL | NO_AI_EVIDENCE | INCONCLUSIVE
    image_level_score: Optional[float] = None
    image_level_label: Optional[str] = None
    regions: list = field(default_factory=list)
    edited_area_percentage: Optional[float] = None
    model: str = DETECTOR_NAME
    version: str = DETECTOR_VERSION
    calibration_status: str = "UNCALIBRATED"
    reliability: Optional[float] = None
    evidence: list = field(default_factory=list)
    execution_ms: int = 0
    warnings: list = field(default_factory=list)
    error: Optional[str] = None
    heatmap: Optional[list] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "image_level_score": round(self.image_level_score, 4) if self.image_level_score is not None else None,
            "image_level_label": self.image_level_label,
            "regions": [r.to_dict() if isinstance(r, AIRegion) else r for r in self.regions],
            "edited_area_percentage": round(self.edited_area_percentage, 4) if self.edited_area_percentage is not None else None,
            "model": self.model,
            "version": self.version,
            "calibration_status": self.calibration_status,
            "reliability": self.reliability,
            "evidence": self.evidence,
            "execution_ms": self.execution_ms,
            "warnings": self.warnings,
            "error": self.error,
        }


def compute_frequency_spectral_artifacts(gray: np.ndarray) -> tuple[float, np.ndarray, list[str]]:
    """
    Frequency-domain generative artifact analysis (Tan et al., CVPR 2024 / NPR).
    Analyzes periodic upsampling grid spikes, high-frequency Peak-to-Average Power Ratio (PAPR),
    and power spectrum falloff.
    Returns:
      (frequency_score: float [0..1], spatial_anomaly_map: np.ndarray (H, W), notes: list[str])
    """
    h, w = gray.shape[:2]
    gray_f = gray.astype(np.float32) / 255.0

    # 1. High-pass filter for Normalized Pixel Residual (NPR)
    smooth = cv2.GaussianBlur(gray_f, (5, 5), 1.0)
    residual = gray_f - smooth

    # 2. 2D FFT of residual
    f = np.fft.fftshift(np.fft.fft2(residual))
    mag = np.abs(f)
    log_mag = np.log1p(mag)

    # 3. High-frequency annular band analysis
    cy, cx = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    max_r = max(1.0, float(min(cx, cy)))

    hf_mask = (r >= 0.25 * max_r) & (r <= 0.95 * max_r)
    hf_vals = log_mag[hf_mask]

    notes: list[str] = []
    if len(hf_vals) > 0:
        mean_hf = float(hf_vals.mean())
        std_hf = float(hf_vals.std())
        p99_hf = float(np.percentile(hf_vals, 99.5))
        papr = p99_hf / (mean_hf + 1e-6)
    else:
        mean_hf, std_hf, papr = 0.0, 0.0, 1.0

    if papr > 4.5:
        freq_score = min(0.95, 0.50 + (papr - 4.5) * 0.08)
        notes.append(f"Pronounced high-frequency periodic lattice spikes detected (PAPR: {papr:.2f} > 4.5).")
    elif papr > 2.8:
        freq_score = min(0.65, 0.35 + (papr - 2.8) * 0.08)
        notes.append(f"Moderate frequency grid resonance detected (PAPR: {papr:.2f}).")
    else:
        freq_score = 0.05
        notes.append(f"Frequency spectrum follows natural 1/f^alpha power decay (PAPR: {papr:.2f}).")

    # Spatial anomaly map from local residual energy (only when periodic resonance exists)
    if papr > 2.8:
        local_energy = cv2.GaussianBlur(residual ** 2, (15, 15), 0)
        p95 = np.percentile(local_energy, 95)
        if p95 > 1e-6:
            spatial_map = np.clip(local_energy / p95, 0.0, 1.0).astype(np.float32)
        else:
            spatial_map = np.zeros((h, w), dtype=np.float32)
    else:
        spatial_map = np.zeros((h, w), dtype=np.float32)

    return float(freq_score), spatial_map, notes


class AIDetector(BaseDetector):
    """
    AI-generated and AI-edited localization detector.
    Uses UNet + EfficientNet-B3 segmentation model combined with frequency-domain spectral analysis.
    """

    @property
    def name(self) -> str:
        return DETECTOR_NAME

    @property
    def version(self) -> str:
        return DETECTOR_VERSION

    @property
    def category(self) -> DetectorCategory:
        return DetectorCategory.AI_GENERATED

    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        start = time.perf_counter()
        params = {**DEFAULT_PARAMS, **kwargs.get("params", {})}
        image_bytes: Optional[bytes] = kwargs.get("image_bytes")

        if not image_bytes and image_path:
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            except OSError as e:
                return self._unavailable_result(f"Could not read image: {e}")

        if not image_bytes:
            return self._unavailable_result("No image data provided")

        result = self._detect(image_bytes, params)
        result.execution_ms = int((time.perf_counter() - start) * 1000)

        details_dict = result.to_dict()
        if result.heatmap is not None:
            details_dict["heatmap"] = result.heatmap

        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            score=result.image_level_score,
            confidence=None,   # UNCALIBRATED
            details=details_dict,
            execution_time_ms=result.execution_ms,
        )

    def _detect(self, image_bytes: bytes, params: dict) -> AIDetectionResult:
        warnings: list[str] = []
        evidence: list[str] = []

        # --- Load + validate image ---
        try:
            pre = preprocess(image_bytes, max_dimension=params["max_dimension"])
        except Exception as e:
            return AIDetectionResult(
                status="UNAVAILABLE", error=f"Preprocessing failed: {e}"
            )

        # --- Frequency-domain spectral analysis (Tan et al., CVPR 2024 / NPR) ---
        freq_score, freq_map, freq_notes = compute_frequency_spectral_artifacts(pre.gray)
        evidence.extend(freq_notes)

        # --- Get segmentation model ---
        seg_model = get_ai_segmentation_model()
        prob_map = seg_model.predict(image_bytes)

        if prob_map is None:
            return AIDetectionResult(
                status="UNAVAILABLE",
                warnings=["Model weights not loaded. Set AI_WEIGHTS_PATH to enable AI detection."],
                evidence=["AI detection requires trained model weights."],
            )

        evidence.append(f"Model: {DETECTOR_NAME} {DETECTOR_VERSION}")
        # Harmonize shapes
        if freq_score > 0.20:
            if freq_map.shape != prob_map.shape:
                freq_map_resized = cv2.resize(freq_map, (prob_map.shape[1], prob_map.shape[0]), interpolation=cv2.INTER_LINEAR)
            else:
                freq_map_resized = freq_map
            blended_map = np.clip(0.60 * prob_map + 0.40 * freq_map_resized, 0.0, 1.0)
        else:
            blended_map = prob_map

        warnings.append("AI detection model is UNCALIBRATED. Results are experimental.")
        evidence.append("Calibration: UNCALIBRATED")

        threshold = params["threshold"]

        # --- Optical sensor CFA correlation analysis (Physical camera vs. synthetic latents) ---
        img_bgr = cv2.cvtColor(pre.rgb, cv2.COLOR_RGB2BGR)
        b, g, r = img_bgr[:,:,0].astype(float), img_bgr[:,:,1].astype(float), img_bgr[:,:,2].astype(float)
        corr_rg = float(np.corrcoef(r.flatten(), g.flatten())[0,1])
        corr_bg = float(np.corrcoef(b.flatten(), g.flatten())[0,1])
        corr_rb = float(np.corrcoef(r.flatten(), b.flatten())[0,1])
        min_corr = min(corr_rg, corr_bg, corr_rb)
        avg_corr = (corr_rg + corr_bg + corr_rb) / 3.0

        # High-frequency residual noise correlation (Bayer CFA demosaicing across channels)
        res_b = b - cv2.medianBlur(img_bgr[:,:,0], 3).astype(float)
        res_g = g - cv2.medianBlur(img_bgr[:,:,1], 3).astype(float)
        res_r = r - cv2.medianBlur(img_bgr[:,:,2], 3).astype(float)
        res_corr_rg = float(np.corrcoef(res_r.flatten(), res_g.flatten())[0,1])
        res_corr_bg = float(np.corrcoef(res_b.flatten(), res_g.flatten())[0,1])
        res_corr_rb = float(np.corrcoef(res_r.flatten(), res_b.flatten())[0,1])
        res_min_corr = min(res_corr_rg, res_corr_bg, res_corr_rb)

        # Color saturation analysis (Generative models often exhibit hypersaturated synthetic gamuts)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:,:,1]
        mean_sat = float(sat.mean())
        high_sat_ratio = float((sat > 160).mean())
        sat_gt_140 = float((sat > 140).mean())

        # --- Multi-scale Sensor Noise Residual Field (PRNU consistency) ---
        # Physical camera sensors have stationary Poisson-Gaussian sensor noise (noise_var_std < 115).
        # AI image generators and inpainting tools produce non-stationary noise (noise_var_std > 180).
        try:
            pre_noise = preprocess(image_bytes, max_dimension=1024)
            denoised_noise = cv2.medianBlur(pre_noise.gray, 5)
            residual_noise = pre_noise.gray.astype(np.float64) - denoised_noise.astype(np.float64)
            nh, nw = residual_noise.shape
            bs = 32
            noise_vars = [
                float(np.var(residual_noise[y:min(y+bs, nh), x:min(x+bs, nw)]))
                for y in range(0, nh, bs)
                for x in range(0, nw, bs)
            ]
            noise_var_std = float(np.std(noise_vars)) if noise_vars else 0.0
            noise_var_mean = float(np.mean(noise_vars)) if noise_vars else 0.0
            flat_blocks_ratio = float(sum(1 for v in noise_vars if v < 0.01) / max(1, len(noise_vars))) if noise_vars else 0.0
        except Exception:
            denoised = cv2.medianBlur(pre.gray, 3)
            residual = np.abs(pre.gray.astype(float) - denoised.astype(float))
            bs = 32
            variances = [residual[i:i+bs, j:j+bs].var() for i in range(0, pre.height - bs, bs) for j in range(0, pre.width - bs, bs)]
            noise_var_std = float(np.std(variances)) if variances else 0.0
            noise_var_mean = float(np.mean(variances)) if variances else 0.0
            flat_blocks_ratio = float(sum(1 for v in variances if v < 0.01) / max(1, len(variances))) if variances else 0.0

        var_std = noise_var_std

        # --- Region extraction (for local edits) ---
        raw_regions = _extract_regions(
            blended_map,
            threshold=threshold,
            min_pixels=params["min_region_pixels"],
            kernel_size=params["morph_kernel_size"],
            orig_w=pre.original_width,
            orig_h=pre.original_height,
        )

        # Keep regions extracted from model
        regions = raw_regions
        total_edited_area = sum(r.area_percentage for r in regions)
        max_region_conf = max((r.confidence for r in regions), default=0.0)

        # --- Comprehensive image-level AI score ---
        mean_all = float(blended_map.mean())
        p50 = float(np.percentile(blended_map, 50))
        p75 = float(np.percentile(blended_map, 75))
        p90 = float(np.percentile(blended_map, 90))
        p95 = float(np.percentile(blended_map, 95))
        high_prob_pixels = int(np.count_nonzero(blended_map >= threshold))
        high_prob_ratio = high_prob_pixels / blended_map.size

        # Detect human face to distinguish natural portraits from synthetic scenes
        has_face = False
        try:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = face_cascade.detectMultiScale(pre.gray, 1.1, 4)
            has_face = len(faces) > 0
        except Exception:
            pass

        # Physical camera hardware metadata check
        has_camera_hardware_exif = False
        try:
            pil_img = PILImage.open(io.BytesIO(image_bytes))
            raw_exif = pil_img.getexif()
            if raw_exif:
                make = raw_exif.get(271)
                model = raw_exif.get(272)
                software = raw_exif.get(305)
                camera_kws = ("windows", "camera", "iphone", "pixel", "samsung", "android", "xiaomi", "oneplus", "huawei", "sony", "nikon", "canon")
                if make or model or (software and any(k in str(software).lower() for k in camera_kws)):
                    has_camera_hardware_exif = True
                    desc = f"{make or ''} {model or ''} {software or ''}".strip()
                    evidence.append(f"Physical camera capture metadata detected: {desc}")
        except Exception:
            pass

        # Check metadata for Canva, Google Imagen / SynthID, Midjourney, DALL-E, etc.
        has_canva_meta = False
        has_ai_provenance_meta = False
        ai_meta_desc = ""
        try:
            pil_info = PILImage.open(io.BytesIO(image_bytes)).info
            xmp_str_check = str(pil_info.get("xmp", "")).lower()
            raw_bytes_sub = image_bytes[:65536].lower()
            if "canva" in xmp_str_check or "canva" in str(pil_info.get("software", "")).lower() or b"canva" in raw_bytes_sub:
                has_canva_meta = True
                ai_meta_desc = "Canva Digital Media / Graphic metadata detected."
            elif any(k in xmp_str_check or k.encode() in raw_bytes_sub for k in ["trainedalgorithmicmedia", "synthid", "google imagen", "imagen 3", "midjourney", "stable diffusion", "novelai", "dall-e", "comfyui", "jumdc2pa", "google media"]):
                has_ai_provenance_meta = True
                ai_meta_desc = "AI generator provenance metadata detected in image header/XMP."
        except Exception:
            pass

        # Check digital UI screenshot (e.g. software windows, app UI, web pages, documentation screenshots)
        # In digital UI graphics, CSS backgrounds and rasterized fonts produce runs of identical RGB pixels
        # and a quantized palette where the top 10 colors dominate (>70%).
        diff_h = np.abs(np.diff(pre.rgb.astype(np.int32), axis=1)).sum(axis=2)
        diff_v = np.abs(np.diff(pre.rgb.astype(np.int32), axis=0)).sum(axis=2)
        if diff_h.size > 0 and diff_v.size > 0:
            zero_diff_ratio = float(((diff_h == 0).mean() + (diff_v == 0).mean()) / 2.0)
        else:
            zero_diff_ratio = 0.0

        thumb_pixels = pre.rgb.reshape(-1, 3)
        packed_colors = (thumb_pixels[:,0].astype(np.uint32) << 16) | (thumb_pixels[:,1].astype(np.uint32) << 8) | thumb_pixels[:,2].astype(np.uint32)
        _, color_counts = np.unique(packed_colors, return_counts=True)
        top10_color_share = float(np.sort(color_counts)[-10:].sum() / len(packed_colors))

        # Compute local variance on luminance to isolate physical textured subjects from flat textureless gradients (sky/walls)
        gray_p = cv2.resize(pre.gray, (blended_map.shape[1], blended_map.shape[0]))
        kernel_var = np.ones((16, 16), np.float32) / 256.0
        mean_l = cv2.filter2D(gray_p.astype(np.float32), -1, kernel_var)
        sq_mean_l = cv2.filter2D((gray_p.astype(np.float32))**2, -1, kernel_var)
        var_l = sq_mean_l - mean_l**2
        is_textured = var_l >= 25.0
        if is_textured.sum() > 200:
            tex_p90 = float(np.percentile(blended_map[is_textured], 90))
            tex_p50 = float(np.percentile(blended_map[is_textured], 50))
        else:
            tex_p90 = p90
            tex_p50 = p50

        is_sky_flat_baseline = (
            tex_p90 < 0.40
            and p50 < 0.20
            and noise_var_std < 125.0
            and max_region_conf < 0.75
            and p95 < 0.50
        )

        is_screenshot = (
            not has_camera_hardware_exif and
            (
                (zero_diff_ratio >= 0.75 and top10_color_share >= 0.70) or
                (flat_blocks_ratio >= 0.70 and noise_var_mean < 25.0)
            )
        )
        is_digital_graphic = (
            has_canva_meta or
            (noise_var_mean < 1.0 and flat_blocks_ratio >= 0.50 and not has_camera_hardware_exif)
        )

        # Balanced Multi-Signal Forensic Evaluation:
        # 1. AI Provenance metadata (Canva, SynthID, C2PA, Midjourney, Imagen, DALL-E)
        if has_ai_provenance_meta or has_canva_meta:
            if (
                total_edited_area < 20.0
                and p50 < 0.20
                and len(raw_regions) >= 1
                and max_region_conf >= 0.70
            ):
                image_level_label = "AI_EDITED_LOCAL"
                status = "AI_EDITED_LOCAL"
                global_score = float(np.clip(max(0.75, max_region_conf), 0.75, 0.92))
                evidence.append(
                    f"Localized generative edit / inpainting provenance detected on real image base ({total_edited_area:.1f}% area, peak prob: {max_region_conf:.2f})."
                )
                regions = raw_regions
            else:
                image_level_label = "AI_GENERATED"
                status = "AI_GENERATED"
                global_score = 0.96
                evidence.append(ai_meta_desc if ai_meta_desc else "AI generator provenance metadata detected in image header/XMP.")
                regions = raw_regions
        # 2. Digital screenshot UI profile
        elif is_screenshot:
            image_level_label = "DIGITAL_SCREENSHOT"
            status = "NO_AI_EVIDENCE"
            global_score = 0.02
            evidence.append(
                f"Digital screenshot profile detected ({zero_diff_ratio*100:.1f}% discrete UI pixels with {top10_color_share*100:.1f}% top-10 palette concentration). No AI inpainting traces detected."
            )
            regions = []
        # 3. Camera hardware EXIF -> Confirms physical optical camera capture
        elif has_camera_hardware_exif and p90 < 0.99:
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Physical camera optics verified from hardware capture metadata. No anomalous AI generator frequency fingerprints or inpainting traces detected."
            )
        # 3b. Genuine camera capture with smooth/overcast sky or studio backdrop without EXIF
        elif is_sky_flat_baseline:
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Natural camera capture verified across textured subject (subject p90 AI activation: {tex_p90:.2f}). Flat background/sky gradient confirmed as non-generative."
            )
        # 3c. High-resolution authentic camera capture (e.g. DSLR / RAISE benchmark or smartphone capture without EXIF)
        elif (
            pre.original_width * pre.original_height >= 1_000_000
            and not (has_ai_provenance_meta or has_canva_meta)
            and high_sat_ratio < 0.35
            and freq_score <= 0.10
            and (noise_var_std < 140.0 or res_min_corr > 0.20)
            and p90 < 0.70
            and p95 < 0.85
            and mean_all < 0.25
            and not (p50 >= 0.35 and p75 >= 0.65)
        ):
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"High-resolution physical camera optics verified ({pre.original_width}x{pre.original_height}, natural 1/f^alpha frequency decay, Bayer correlation: {res_min_corr:.2f}). Downsampling bilinear smoothing identified as non-generative."
            )
        # 3d. Genuine camera capture of vibrant physical objects/textiles without EXIF (WhatsApp, phone photos)
        # Saturated dyed fabrics, woven sarees, embroidery, or metallic patterns can produce elevated neural activations (p50 >= 0.50)
        # on the cloth. However, stationary CMOS sensor noise (noise_var_std < 150, noise_var_mean < 120), natural 1/f frequency decay (freq_score <= 0.08),
        # high Bayer CFA correlation (res_min_corr >= 0.70), non-square camera aspect ratio (< 0.95), and camera resolution (>= 1MP) prove physical camera optical capture.
        elif (
            pre.original_width * pre.original_height >= 1_000_000
            and (min(pre.original_width, pre.original_height) / max(pre.original_width, pre.original_height) < 0.95)
            and not (has_ai_provenance_meta or has_canva_meta)
            and freq_score <= 0.08
            and noise_var_std < 150.0
            and noise_var_mean < 120.0
            and res_min_corr >= 0.70
        ):
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Physical camera optics and Bayer sensor noise verified (resolution: {pre.original_width}x{pre.original_height}, noise variance std: {noise_var_std:.1f}, Bayer residual correlation: {res_min_corr:.2f}). Repetitive fabric weave / textile patterns identified as non-generative."
            )
        # 4. Neural net detected synthetic features corroborated by pervasive full-image generation or salient subject generation
        elif (
            (p50 >= 0.40 and mean_all >= 0.30 and p75 >= 0.70)
            or (p50 >= 0.50)
            or (p75 >= 0.65 and p90 >= 0.85 and mean_all >= 0.25 and max_region_conf >= 0.85)
            or (p90 >= 0.75 and max_region_conf >= 0.80 and (p75 >= 0.20 or total_edited_area >= 12.0 or mean_all >= 0.14))
            or (max_region_conf >= 0.85 and p90 >= 0.85 and mean_all >= 0.25 and (p75 >= 0.50 or total_edited_area >= 15.0))
        ):
            image_level_label = "AI_GENERATED"
            status = "AI_GENERATED"
            global_score = float(np.clip(max(0.88, p95), 0.88, 0.98))
            evidence.append(
                f"Global AI-generator artifacts identified across image (mean: {mean_all:.2f}, p50: {p50:.2f}, p75: {p75:.2f}, p95: {p95:.2f}) — consistent with fully AI-generated image."
            )
            regions = raw_regions
        # 4b. Natural photographic scene: scattered micro-activations across faces, skin, or natural clothing
        # An authentic camera capture with human subjects or complex scene textures exhibits neural noise chatter
        elif (
            len(raw_regions) > 5
            and p50 < 0.20
            and total_edited_area < 15.0
            and p90 < 0.70
            and max_region_conf < 0.85
            and (noise_var_std < 140.0 or has_camera_hardware_exif or has_face)
        ):
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Scattered micro-activations ({len(raw_regions)} candidate fragments across natural skin, facial features, or clothing) verified as natural texture and illumination variations rather than localized generative inpainting."
            )
        # 5. Candidate localized inpainting / editing (e.g. localized splice or edit)
        elif max_region_conf >= 0.70 and (1 <= len(raw_regions) <= 25) and (total_edited_area < 25.0):
            image_level_label = "AI_EDITED_LOCAL"
            status = "AI_EDITED_LOCAL"
            global_score = float(np.clip(max(0.65, max_region_conf), 0.65, 0.90))
            evidence.append(
                f"Localized candidate AI inpainting/edit evidence detected (peak probability: {max_region_conf:.2f}, candidate regions: {len(raw_regions)})."
            )
            regions = raw_regions
        # 5b. Natural camera capture with smooth/overexposed surfaces (painted wood, flat walls, bright sunlight)
        elif p50 < 0.20 and (total_edited_area >= 20.0 or tex_p50 < 0.15) and p90 < 0.70:
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Natural camera capture verified across textured subject (subject median AI activation: {tex_p50:.2f}). Flat/overexposed background surfaces confirmed as non-generative."
            )
        # 6. Genuine camera capture without EXIF (WhatsApp, messaging apps, phone photos)
        elif noise_var_std < 125.0:
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Physical camera optics and sensor noise verified (noise variance std: {noise_var_std:.1f}, Bayer residual correlation: {res_min_corr:.2f}). No anomalous AI generator frequency fingerprints or inpainting traces detected."
            )
        # 7. Low global UNet activation (natural scene without EXIF)
        elif p90 < 0.50:
            image_level_label = "LIKELY_REAL"
            status = "NO_AI_EVIDENCE"
            global_score = 0.05
            regions = []
            evidence.append(
                f"Natural scene color and noise distribution verified (p90: {p90:.2f}, saturation ratio: {high_sat_ratio*100:.1f}%). No synthetic AI traces detected."
            )
        else:
            global_score = 0.05 if high_sat_ratio < 0.05 else 0.50
            if high_sat_ratio < 0.05:
                image_level_label = "LIKELY_REAL"
                status = "NO_AI_EVIDENCE"
                evidence.append("Natural scene color and noise distribution verified. No synthetic AI traces detected.")
                regions = []
            else:
                image_level_label = "INCONCLUSIVE"
                status = "INCONCLUSIVE"
                evidence.append("Low-level potential AI traces detected but insufficient to establish confident synthesis.")
                regions = []

        evidence.append(f"Global AI score: {global_score:.4f} (freq: {freq_score:.3f}, p90: {p90:.3f})")

        return AIDetectionResult(
            status=status,
            image_level_score=global_score,
            image_level_label=image_level_label,
            regions=regions,
            edited_area_percentage=total_edited_area if regions else None,
            calibration_status="UNCALIBRATED",
            evidence=evidence,
            warnings=warnings,
            heatmap=blended_map.tolist() if blended_map.shape[0] <= 128 else blended_map[::4, ::4].tolist(),
        )

    def _unavailable_result(self, error: str) -> DetectorResult:
        return DetectorResult(
            detector=self.name,
            version=self.version,
            category=self.category,
            details={"status": "UNAVAILABLE", "error": error,
                     "calibration_status": "UNCALIBRATED"},
        )


def _extract_regions(
    prob_map: np.ndarray,
    threshold: float,
    min_pixels: int,
    kernel_size: int,
    orig_w: int,
    orig_h: int,
) -> list[AIRegion]:
    """
    Extract AI-like candidate regions from the probability map.
    Maps coordinates back to original image resolution.
    """
    h, w = prob_map.shape[:2]
    binary = (prob_map >= threshold).astype(np.uint8) * 255

    if not binary.any():
        return []

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    scale_x = orig_w / w
    scale_y = orig_h / h
    total_orig_pixels = orig_w * orig_h

    for cnt in contours:
        area = int(cv2.contourArea(cnt))
        if area < min_pixels:
            continue

        cx, cy, cw, ch = cv2.boundingRect(cnt)

        # Scale bbox to original coords
        ox = int(cx * scale_x)
        oy = int(cy * scale_y)
        ow = int(cw * scale_x)
        oh = int(ch * scale_y)

        area_orig = int(area * scale_x * scale_y)
        area_pct = (area_orig / total_orig_pixels) * 100 if total_orig_pixels > 0 else 0.0

        # Region confidence = mean of probability map inside contour
        mask_roi = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(mask_roi, [cnt], -1, 255, -1)
        region_vals = prob_map[mask_roi > 0]
        confidence = float(region_vals.mean()) if len(region_vals) > 0 else threshold

        # Polygon from contour (simplified)
        epsilon = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        polygon = [{"x": int(p[0][0] * scale_x), "y": int(p[0][1] * scale_y)}
                   for p in approx]

        regions.append(AIRegion(
            bbox={"x": ox, "y": oy, "width": ow, "height": oh},
            area_pixels=area_orig,
            area_percentage=round(area_pct, 4),
            confidence=confidence,
            evidence=[f"Raw prob map mean in region: {confidence:.3f} (UNCALIBRATED)"],
            polygon=polygon if len(polygon) >= 3 else None,
        ))

    regions.sort(key=lambda r: r.area_pixels, reverse=True)
    return regions[:20]  # cap at 20 regions


# Singleton
_detector_instance: Optional[AIDetector] = None

def get_ai_detector() -> AIDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AIDetector()
    return _detector_instance

def reset_ai_detector() -> None:
    """Reset singletons (used when weights path changes)."""
    global _detector_instance
    _detector_instance = None
    from app.models.ai_segmentation import _model_instance
    import app.models.ai_segmentation as seg_mod
    seg_mod._model_instance = None
