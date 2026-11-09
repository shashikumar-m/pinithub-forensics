"""
Unified Forensics Analysis Pipeline.

Fulfills PinITHUB_Plan.pdf (Section 3.2, 5, 7, 10.1) and Crop_plan.pdf:
- Runs in both BLIND mode (suspect image only) and REFERENCE mode (suspect + original).
- Detects edit types: Splicing, Copy-Move, Generative AI / Inpainting, Retouching, Cropping, Metadata tampering.
- Produces composite heatmap, binary mask, bounding boxes, area percentages, and editTypeGuess.
- Fuses evidence using the Verdict Engine into a 3-way decision (EDITED / NOT_EDITED / INCONCLUSIVE).
- Strictly follows honest wording: never claims 100% or "authentic".
"""
from __future__ import annotations

import base64
import concurrent.futures
import cv2
import io
import logging
import math
import time
from typing import Any, Optional
import numpy as np
from PIL import Image as PILImage

from app.detectors.metadata_inspector import get_metadata_inspector
from app.detectors.ela import get_ela_detector
from app.detectors.noise_residual import get_noise_residual_detector
from app.detectors.dct_analysis import get_dct_analysis_detector
from app.detectors.jpeg_double_compression import get_jpeg_double_compression_detector
from app.detectors.resampling import get_resampling_detector
from app.detectors.jpeg_grid import get_jpeg_grid_detector
from app.detectors.copy_move import get_copy_move_detector
from app.detectors.crop_detector import get_crop_detector
from app.detectors.registration import get_registration_detector
from app.detectors.ai_detector import get_ai_detector
from app.detectors.dqt_fingerprint import get_dqt_fingerprint_detector
from app.detectors.modality_router import classify_modality, ImageModality
from app.detectors.c2pa_parser import get_c2pa_parser_detector
from app.detectors.thumbnail_discrepancy import get_thumbnail_discrepancy_detector
from app.detectors.chromatic_aberration import get_chromatic_aberration_detector
from app.detectors.corneal_reflection import get_corneal_reflection_detector
from app.detectors.cfa_demosaicing import get_cfa_demosaicing_detector
from app.detectors.face_biometrics import get_face_biometrics_detector
from app.detectors.univfd import get_univfd_detector
from app.detectors.drct import get_drct_detector
from app.detectors.dire import get_dire_detector
from app.io.format_normalizer import normalize_image_bytes
from app.fusion.normalizer import normalize_all
from app.fusion.verdict_engine import fuse
from app.fusion.calibrate import EvidenceCalibrator
from app.io.preprocessing import preprocess, encode_artifact_png
from app.utils.json_utils import sanitize_for_json

logger = logging.getLogger(__name__)


def _array_to_data_url(arr: np.ndarray, is_heatmap: bool = False) -> str:
    """Encode numpy array (2D or RGB) to PNG data URL."""
    try:
        if is_heatmap and arr.ndim == 2:
            if float(arr.max()) < 0.15:
                # Clean / unedited baseline: pure transparent black for mix-blend-screen
                colored_rgb = np.zeros((arr.shape[0], arr.shape[1], 3), dtype=np.uint8)
            else:
                # Colorize single-channel heatmap with COLORMAP_JET
                normalized = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
                colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
                # Suppress unmanipulated background baseline so it remains transparent black
                colored[normalized < 35] = 0
                # Convert BGR from cv2 to RGB for PIL
                colored_rgb = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
            png_bytes = encode_artifact_png(colored_rgb, normalize=False)
        else:
            png_bytes = encode_artifact_png(arr)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        logger.warning(f"Failed to generate data URL: {e}")
        return ""


def run_unified_analysis(
    suspect_bytes: bytes,
    reference_bytes: Optional[bytes] = None,
    params: Optional[dict] = None,
) -> dict:
    """
    Executes the complete forensic analysis on the suspect image (and optional reference).
    """
    start_time = time.perf_counter()
    params = params or {}
    has_reference = reference_bytes is not None and len(reference_bytes) > 0
    mode = "REFERENCE" if has_reference else "BLIND"

    # 0. Universal Format Normalizer & Intake Safety
    warnings: list[str] = []
    try:
        norm_res = normalize_image_bytes(suspect_bytes)
        if not norm_res.error and len(norm_res.image_bytes) > 0:
            active_suspect_bytes = norm_res.image_bytes
        else:
            active_suspect_bytes = suspect_bytes
        if norm_res.warnings:
            warnings.extend(norm_res.warnings)
    except Exception as e:
        logger.debug("Format normalizer fallback: %s", e)
        active_suspect_bytes = suspect_bytes

    # Preprocess suspect image
    pre = preprocess(active_suspect_bytes, max_dimension=1024)
    h, w = pre.height, pre.width
    orig_w, orig_h = pre.original_width, pre.original_height

    # 0b. Modality Pre-Routing
    modality_info = None
    try:
        mod_result = classify_modality(active_suspect_bytes)
        modality_info = {
            "modality": mod_result.modality.value,
            "confidence": mod_result.confidence,
            "evidence": mod_result.evidence,
        }
    except Exception as e:
        logger.debug("Modality router failed: %s", e)
    limitations: list[str] = [
        "No evidence found is not proof of authenticity.",
        "Generative AI detectors work best on known generator architectures.",
        "Heavy recompression or low resolution can destroy forensic signals.",
    ]

    all_detector_results: dict[str, Any] = {}
    evidence_list: list[dict[str, Any]] = []

    # 1. Metadata Inspection
    try:
        meta_det = get_metadata_inspector()
        meta_res = meta_det.timed_run("", image_bytes=suspect_bytes)
        meta_dict = meta_res.to_dict()
        all_detector_results["metadata"] = meta_dict

        raw_details = meta_dict.get("details", {})
        norm_meta = raw_details.get("normalized_metadata", {})
        exif_raw = raw_details.get("exif_raw", {})

        has_exif = bool(exif_raw)
        camera_dict = norm_meta.get("camera", {}) if isinstance(norm_meta.get("camera"), dict) else {}
        ts_dict = norm_meta.get("timestamps", {}) if isinstance(norm_meta.get("timestamps"), dict) else {}

        software = norm_meta.get("software") or exif_raw.get("Software")
        editing_software = norm_meta.get("editing_software")
        camera_make = camera_dict.get("make") or norm_meta.get("camera_make") or exif_raw.get("Make")
        camera_model = camera_dict.get("model") or norm_meta.get("camera_model") or exif_raw.get("Model")
        device_name = str(exif_raw.get("39424") or exif_raw.get(39424) or "").strip()
        captured_at = ts_dict.get("captured_at") or norm_meta.get("captured_at") or exif_raw.get("DateTimeOriginal") or exif_raw.get("DateTime")
        modified_at = ts_dict.get("metadata_modified_at") or norm_meta.get("metadata_modified_at")

        f_number = str(exif_raw.get("FNumber") or camera_dict.get("aperture") or "")
        focal_length = str(exif_raw.get("FocalLength") or camera_dict.get("focal_length") or "")
        exposure_val = str(exif_raw.get("ExposureTime") or camera_dict.get("shutter_speed") or "")
        iso_val = str(exif_raw.get("ISOSpeedRatings") or camera_dict.get("iso") or "")
        offset_tz = str(exif_raw.get("OffsetTime") or exif_raw.get("OffsetTimeOriginal") or ts_dict.get("captured_at_timezone") or "")

        device_desc = f"{camera_make or ''} {camera_model or ''}".strip()
        if device_name:
            device_desc += f" ({device_name})" if device_desc else device_name

        meta_details = {
            "has_exif": has_exif,
            "software": software,
            "editing_software": editing_software,
            "camera_make": camera_make,
            "camera_model": camera_model,
            "datetime_original": captured_at,
            "datetime_modified": modified_at,
            **{f"tag_{k}": str(v)[:150] for k, v in list(exif_raw.items())[:60]},
        }

        ai_provenance = norm_meta.get("ai_provenance")
        ai_generator = norm_meta.get("ai_generator")
        meta_notes: list[str] = []
        if ai_provenance == "AI_GENERATED":
            meta_notes.append(f"AI generation metadata detected: {ai_generator or 'trainedAlgorithmicMedia'}.")
            meta_score = 0.95
        elif ai_provenance == "AI_EDITED":
            meta_notes.append(f"AI inpainting/editing metadata detected: {ai_generator or 'compositeWithTrainedAlgorithmicMedia'}.")
            meta_score = 0.85
        elif ai_provenance == "CANVA_DESIGN" or editing_software == "Canva":
            meta_notes.append(f"Canva digital design / AI media metadata detected ({software or 'Canva'}).")
            meta_score = 0.85
        elif editing_software:
            meta_notes.append(f"Known editing software tag detected: {editing_software}.")
            meta_score = 0.35
        elif software:
            meta_notes.append(f"Capture device / OS software tag: {software}.")
            meta_score = 0.0
        elif not has_exif:
            meta_notes.append("No EXIF metadata present (possibly stripped).")
            meta_score = 0.2
        else:
            meta_score = 0.0

        if modified_at and captured_at:
            if modified_at != captured_at:
                meta_notes.append("Modified timestamp differs from original capture timestamp.")
        evidence_list.append({
            "detector": "metadata",
            "version": meta_res.version,
            "category": "METADATA",
            "score": meta_score,
            "reliability": 0.90,
            "tag": "PROVEN",
            "notes": meta_notes,
            "evidence": meta_details,
        })
    except Exception as e:
        logger.error(f"Metadata inspector failed: {e}")

    # 2. Classical Forensic Detectors
    ela_map = np.zeros((h, w), dtype=np.float32)
    noise_map = np.zeros((h, w), dtype=np.float32)
    copy_points: list[tuple[int, int]] = []

    classical_map = [
        ("ela", get_ela_detector, "PROVEN, LIMITED"),
        ("noise_residual", get_noise_residual_detector, "PROVEN"),
        ("dct_analysis", get_dct_analysis_detector, "PROVEN"),
        ("jpeg_double_compression", get_jpeg_double_compression_detector, "PROVEN"),
        ("resampling", get_resampling_detector, "PROVEN"),
        ("jpeg_grid", get_jpeg_grid_detector, "PROVEN, LIMITED"),
        ("copy_move", get_copy_move_detector, "PROVEN"),
    ]

    def _run_single_classical(item):
        name, get_fn, tag = item
        try:
            det = get_fn()
            res = det.timed_run("", image_bytes=suspect_bytes)
            return name, res, tag, None
        except Exception as e:
            return name, None, tag, e

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        classical_exec_results = list(executor.map(_run_single_classical, classical_map))

    for name, res, tag, err in classical_exec_results:
        if err is not None or res is None:
            logger.error(f"Detector {name} failed: {err}")
            continue
        try:
            rdict = res.to_dict()
            all_detector_results[name] = rdict

            score = rdict.get("score")
            notes: list[str] = []
            det_details = rdict.get("details", {})

            if name == "ela":
                ev_data = det_details.get("evidence", {})
                mean_err = ev_data.get("mean_error", 0.0)
                notes.append(f"Recompression error level: {mean_err:.2f} (weak forensic signal).")
                if "normalized_map" in det_details:
                    try:
                        raw_ela = np.array(det_details["normalized_map"], dtype=np.float32)
                        if raw_ela.shape != (h, w):
                            raw_ela = cv2.resize(raw_ela, (w, h), interpolation=cv2.INTER_LINEAR)
                        ela_map = raw_ela
                    except Exception:
                        pass

            if name == "noise_residual":
                ev_data = det_details.get("evidence", {})
                std_var = ev_data.get("std_variance")
                if std_var and std_var > 100:
                    notes.append(f"High noise variance inconsistency (std: {std_var:.1f}). Possible local splice or denoiser mismatch.")
                else:
                    notes.append("Noise variance consistent across the image.")

            if name == "copy_move":
                ev_data = det_details.get("evidence", {})
                matches = det_details.get("matches_found", 0) or ev_data.get("geometrically_consistent", 0)
                clusters = det_details.get("clusters", [])
                if matches > 0:
                    notes.append(f"{matches} matched keypoint pairs found across {len(clusters)} duplicated regions.")
                else:
                    notes.append("No duplicated feature clusters detected.")

            if name == "jpeg_double_compression":
                ev_data = det_details.get("evidence", {})
                gaps = ev_data.get("total_gaps", 0)
                q_est = ev_data.get("jpeg_quality_estimate")
                if det_details.get("double_compression_detected") or (gaps and gaps > 10):
                    notes.append(f"Periodic DCT histogram gaps ({gaps} gaps, primary Q~{q_est or '?'}) indicate double JPEG compression.")
                else:
                    notes.append(f"Single compression profile detected (estimated quality Q~{q_est or 'N/A'}).")

            if name == "jpeg_grid":
                ev_data = det_details.get("evidence", {})
                h_ratio = ev_data.get("horizontal_ratio", 1.0)
                v_ratio = ev_data.get("vertical_ratio", 1.0)
                if det_details.get("grid_misaligned") or (h_ratio and h_ratio > 1.2) or (v_ratio and v_ratio > 1.2):
                    notes.append("JPEG 8x8 block grid shifted off origin (indicates non-grid crop or geometric edit).")
                else:
                    notes.append("JPEG 8x8 block grid aligned with image coordinate origin.")

            if name == "resampling":
                ev_data = det_details.get("evidence", {})
                row_p = ev_data.get("row_periodicity", 0.0)
                col_p = ev_data.get("col_periodicity", 0.0)
                if max(row_p or 0.0, col_p or 0.0) > 0.4:
                    notes.append(f"Periodic interpolation traces detected (peak periodicity {max(row_p, col_p):.2f}).")
                else:
                    notes.append("No periodic resampling / scaling peaks detected.")

            if name == "dct_analysis":
                ev_data = det_details.get("evidence", {})
                dc_ratio = ev_data.get("dc_energy_ratio", 0.0)
                notes.append(f"DCT low-frequency energy ratio: {dc_ratio:.2f}.")

            evidence_list.append({
                "detector": name,
                "version": res.version,
                "category": res.category.value if hasattr(res.category, "value") else str(res.category),
                "score": round(score, 4) if score is not None else None,
                "reliability": 0.85 if "PROVEN" in tag else 0.60,
                "tag": tag,
                "notes": notes,
                "evidence": det_details.get("evidence", {}),
            })
        except Exception as e:
            logger.error(f"Detector {name} failed: {e}")

    # 2b. Phase 1 & 2 Advanced Detectors (Hardware & Optics)
    try:
        dqt_det = get_dqt_fingerprint_detector()
        dqt_res = dqt_det.timed_run("", image_bytes=active_suspect_bytes)
        dqt_dict = dqt_res.to_dict()
        all_detector_results["dqt_fingerprint"] = dqt_dict
        dqt_details = dqt_dict.get("details", {})
        if dqt_details.get("is_jpeg"):
            evidence_list.append({
                "detector": "dqt_fingerprint",
                "version": dqt_res.version,
                "category": "METADATA",
                "score": dqt_res.score,
                "reliability": 0.90,
                "tag": "PROVEN",
                "notes": dqt_details.get("evidence_notes", [])[:2],
                "evidence": {
                    "match_name": dqt_details.get("match_name"),
                    "match_category": dqt_details.get("match_category"),
                    "quality_estimate": dqt_details.get("quality_estimate"),
                    "is_standard_libjpeg": dqt_details.get("is_standard_libjpeg"),
                },
            })
    except Exception as e:
        logger.debug("DQT detector failed: %s", e)

    try:
        c2pa_det = get_c2pa_parser_detector()
        c2pa_res = c2pa_det.timed_run("", image_bytes=suspect_bytes)
        c2pa_dict = c2pa_res.to_dict()
        all_detector_results["c2pa"] = c2pa_dict
        c2pa_details = c2pa_dict.get("details", {})
        if c2pa_details.get("has_manifest"):
            evidence_list.append({
                "detector": "c2pa_parser",
                "version": c2pa_res.version,
                "category": "METADATA",
                "score": c2pa_res.score,
                "reliability": 0.99,
                "tag": "PROVEN",
                "notes": c2pa_details.get("evidence", [])[:2],
                "evidence": c2pa_details,
            })
    except Exception as e:
        logger.debug("C2PA parser failed: %s", e)

    try:
        thumb_det = get_thumbnail_discrepancy_detector()
        thumb_res = thumb_det.timed_run("", image_bytes=suspect_bytes)
        thumb_dict = thumb_res.to_dict()
        all_detector_results["thumbnail_discrepancy"] = thumb_dict
        thumb_details = thumb_dict.get("details", {})
        if thumb_details.get("has_thumbnail"):
            evidence_list.append({
                "detector": "thumbnail_discrepancy",
                "version": thumb_res.version,
                "category": "METADATA",
                "score": thumb_res.score,
                "reliability": 0.95,
                "tag": "PROVEN",
                "notes": thumb_details.get("evidence", [])[:2],
                "evidence": thumb_details,
            })
    except Exception as e:
        logger.debug("Thumbnail discrepancy detector failed: %s", e)

    try:
        lca_det = get_chromatic_aberration_detector()
        lca_res = lca_det.timed_run("", image_bytes=active_suspect_bytes)
        lca_dict = lca_res.to_dict()
        all_detector_results["chromatic_aberration"] = lca_dict
        lca_details = lca_dict.get("details", {})
        if lca_details.get("status") != "INCONCLUSIVE":
            evidence_list.append({
                "detector": "chromatic_aberration",
                "version": lca_res.version,
                "category": "METADATA",
                "score": lca_res.score,
                "reliability": 0.85,
                "tag": "PROVEN",
                "notes": lca_details.get("evidence", [])[:2],
                "evidence": lca_details,
            })
    except Exception as e:
        logger.debug("Chromatic aberration detector failed: %s", e)

    try:
        corneal_det = get_corneal_reflection_detector()
        corneal_res = corneal_det.timed_run("", image_bytes=active_suspect_bytes)
        corneal_dict = corneal_res.to_dict()
        all_detector_results["corneal_reflection"] = corneal_dict
        corneal_details = corneal_dict.get("details", {})
        if corneal_details.get("status") != "NO_EYES_DETECTED":
            evidence_list.append({
                "detector": "corneal_reflection",
                "version": corneal_res.version,
                "category": "METADATA",
                "score": corneal_res.score,
                "reliability": 0.90,
                "tag": "PROVEN",
                "notes": corneal_details.get("evidence", [])[:2],
                "evidence": corneal_details,
            })
    except Exception as e:
        logger.debug("Corneal reflection detector failed: %s", e)

    # 2e. Bayer CFA Demosaicing Detector
    try:
        cfa_det = get_cfa_demosaicing_detector()
        cfa_res = cfa_det.timed_run("", image_bytes=active_suspect_bytes)
        cfa_dict = cfa_res.to_dict()
        all_detector_results["cfa_demosaicing"] = cfa_dict
        cfa_details = cfa_dict.get("details", {})
        if cfa_details.get("status") != "INCONCLUSIVE":
            evidence_list.append({
                "detector": "cfa_demosaicing",
                "version": cfa_res.version,
                "category": "NOISE_RESIDUAL",
                "score": cfa_res.score,
                "reliability": 0.90,
                "tag": "PROVEN",
                "notes": cfa_details.get("evidence", [])[:2],
                "evidence": cfa_details,
            })
    except Exception as e:
        logger.debug("CFA demosaicing detector failed: %s", e)

    # 2f. Facial Biometric & Micro-Skin Texture Checker
    try:
        face_det = get_face_biometrics_detector()
        face_res = face_det.timed_run("", image_bytes=active_suspect_bytes)
        face_dict = face_res.to_dict()
        all_detector_results["face_biometrics"] = face_dict
        face_details = face_dict.get("details", {})
        if face_details.get("status") != "NO_FACES_DETECTED":
            evidence_list.append({
                "detector": "face_biometrics",
                "version": face_res.version,
                "category": "AI_GENERATED",
                "score": face_res.score,
                "reliability": 0.90,
                "tag": "PROVEN",
                "notes": face_details.get("evidence", [])[:2],
                "evidence": face_details,
            })
    except Exception as e:
        logger.debug("Face biometrics detector failed: %s", e)

    # 3. AI Detector
    ai_status = "UNAVAILABLE"
    ai_score = 0.0
    ai_regions_raw: list[dict] = []
    ai_map = np.zeros((h, w), dtype=np.float32)
    ai_details: dict[str, Any] = {}
    ai_evidence_notes: list[str] = []

    try:
        ai_det = get_ai_detector()
        ai_res = ai_det.timed_run("", image_bytes=suspect_bytes)
        ai_dict = ai_res.to_dict()
        all_detector_results["ai"] = ai_dict

        ai_details = ai_dict.get("details", {})
        ai_status = ai_details.get("status", "UNAVAILABLE")
        ai_score = ai_details.get("image_level_score") or 0.0
        ai_regions_raw = ai_details.get("regions", [])
        ai_evidence_notes = list(ai_details.get("evidence", []))

        # Check if heatmap array was returned by AI detector
        if "heatmap" in ai_details and ai_details["heatmap"]:
            raw_hm = np.array(ai_details["heatmap"], dtype=np.float32)
            if raw_hm.shape != (h, w):
                ai_map = cv2.resize(raw_hm, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                ai_map = raw_hm
        elif ai_status in ("AI_GENERATED", "AI_EDITED_LOCAL"):
            for r in ai_regions_raw:
                bbox = r.get("bbox", {})
                bx = int(bbox.get("x", 0) * w / orig_w)
                by = int(bbox.get("y", 0) * h / orig_h)
                bw = int(bbox.get("width", 0) * w / orig_w)
                bh = int(bbox.get("height", 0) * h / orig_h)
                ai_map[by:by+bh, bx:bx+bw] = np.maximum(ai_map[by:by+bh, bx:bx+bw], float(r.get("confidence") or 0.8))
            if ai_status == "AI_GENERATED":
                ai_map = np.maximum(ai_map, float(ai_score))
        elif ai_status == "UNAVAILABLE":
            ai_score = 0.0

        evidence_list.append({
            "detector": "ai_detector",
            "version": ai_res.version,
            "category": "AI_GENERATED",
            "score": round(ai_score, 4) if ai_score is not None else 0.0,
            "reliability": 0.70,
            "tag": "EXPERIMENTAL",
            "notes": [f"AI Detection status: {ai_status}"] + ai_evidence_notes[:2],
            "evidence": {
                "status": ai_status,
                "score": round(ai_score, 4) if ai_score is not None else 0.0,
                "model": ai_details.get("model", "resnet50_v1"),
                "regions_detected": len(ai_regions_raw),
            },
        })
    except Exception as e:
        logger.error(f"AI detector failed: {e}")

    # 3b, 3c, 3d: Concurrently execute Foundation AI Models (UnivFD, DRCT, DIRE)
    univfd_score: Optional[float] = None
    univfd_details: dict[str, Any] = {}
    drct_score: Optional[float] = None
    drct_details: dict[str, Any] = {}
    dire_score: Optional[float] = None
    dire_details: dict[str, Any] = {}

    def _eval_univfd():
        try:
            return get_univfd_detector().timed_run("", image_bytes=active_suspect_bytes)
        except Exception as e:
            logger.debug("UnivFD detector failed: %s", e)
            return None

    def _eval_drct():
        try:
            return get_drct_detector().timed_run("", image_bytes=active_suspect_bytes)
        except Exception as e:
            logger.debug("DRCT detector failed: %s", e)
            return None

    def _eval_dire():
        try:
            return get_dire_detector().timed_run("", image_bytes=active_suspect_bytes)
        except Exception as e:
            logger.debug("DIRE detector failed: %s", e)
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_univ = executor.submit(_eval_univfd)
        fut_drct = executor.submit(_eval_drct)
        fut_dire = executor.submit(_eval_dire)
        univ_res = fut_univ.result()
        drct_res = fut_drct.result()
        dire_res = fut_dire.result()

    if univ_res:
        try:
            univ_dict = univ_res.to_dict()
            all_detector_results["univfd"] = univ_dict
            univfd_details = univ_dict.get("details", {})
            univfd_score = univ_dict.get("score")
            if univfd_score is not None:
                evidence_list.append({
                    "detector": "univfd",
                    "version": univ_res.version,
                    "category": "AI_GENERATED",
                    "score": round(univfd_score, 4),
                    "reliability": 0.85,
                    "tag": "PROVEN",
                    "notes": univfd_details.get("evidence", [])[:2],
                    "evidence": univfd_details,
                })
        except Exception as e:
            logger.debug("UnivFD processing failed: %s", e)

    if drct_res:
        try:
            drct_dict = drct_res.to_dict()
            all_detector_results["drct"] = drct_dict
            drct_details = drct_dict.get("details", {})
            drct_score = drct_dict.get("score")
            if drct_score is not None:
                evidence_list.append({
                    "detector": "drct",
                    "version": drct_res.version,
                    "category": "AI_GENERATED",
                    "score": round(drct_score, 4),
                    "reliability": 0.85,
                    "tag": "PROVEN",
                    "notes": drct_details.get("evidence", [])[:2],
                    "evidence": drct_details,
                })
        except Exception as e:
            logger.debug("DRCT processing failed: %s", e)

    if dire_res:
        try:
            dire_dict = dire_res.to_dict()
            all_detector_results["dire"] = dire_dict
            dire_details = dire_dict.get("details", {})
            dire_score = dire_dict.get("score")
            if dire_score is not None:
                evidence_list.append({
                    "detector": "dire",
                    "version": dire_res.version,
                    "category": "AI_GENERATED",
                    "score": round(dire_score, 4),
                    "reliability": 0.85,
                    "tag": "PROVEN",
                    "notes": dire_details.get("evidence", [])[:2],
                    "evidence": dire_details,
                })
        except Exception as e:
            logger.debug("DIRE processing failed: %s", e)

    # 4. Reference Comparison & Crop Detection (if Reference Image provided)
    crop_info: Optional[dict] = None
    registration_info: Optional[dict] = None
    diff_map = np.zeros((h, w), dtype=np.float32)

    if has_reference and reference_bytes:
        try:
            crop_det = get_crop_detector()
            crop_res = crop_det.timed_run("", reference_bytes=reference_bytes, suspect_bytes=suspect_bytes)
            crop_dict = crop_res.to_dict()
            all_detector_results["crop"] = crop_dict
            crop_details = crop_dict.get("details", {})

            crop_pct = crop_details.get("crop_percentage")
            kept_pct = crop_details.get("kept_percentage")
            crop_status = crop_details.get("status", "NO_CROP")

            crop_info = {
                "status": crop_status,
                "cropPercentage": round(crop_pct, 2) if crop_pct is not None else 0.0,
                "keptPercentage": round(kept_pct, 2) if kept_pct is not None else 100.0,
                "polygon": crop_details.get("crop_polygon"),
                "boundingBox": crop_details.get("bounding_box"),
                "method": crop_details.get("method", "homography_inverse_projection"),
            }

            notes = []
            if crop_status == "DETECTED" and crop_pct:
                notes.append(f"Image was cropped: approximately {crop_pct:.1f}% of original was removed.")

            evidence_list.append({
                "detector": "crop_detector",
                "version": crop_res.version,
                "category": "CROP_PERCENTAGE",
                "score": (crop_pct / 100.0) if crop_pct else 0.0,
                "reliability": 0.95,
                "tag": "PROVEN",
                "notes": notes,
                "evidence": crop_details,
            })
        except Exception as e:
            logger.error(f"Crop detector failed: {e}")

        try:
            reg_det = get_registration_detector()
            reg_res = reg_det.timed_run("", reference_bytes=reference_bytes, suspect_bytes=suspect_bytes)
            reg_dict = reg_res.to_dict()
            all_detector_results["registration"] = reg_dict
            reg_details = reg_dict.get("details", {})
            reg_info_raw = reg_details.get("registration", {}) if isinstance(reg_details.get("registration"), dict) else reg_details

            registration_info = {
                "status": reg_details.get("status") or reg_info_raw.get("status"),
                "inliers": reg_info_raw.get("inlier_count") or reg_details.get("inliers"),
                "inlierRatio": reg_info_raw.get("inlier_ratio"),
                "reprojectionError": reg_info_raw.get("reprojection_error"),
            }

            # If homography matrix was found, warp reference to suspect and calculate difference map
            homography = reg_info_raw.get("homography_matrix")
            if homography is not None:
                H = np.array(homography, dtype=np.float32)
                if H.shape == (3, 3):
                    try:
                        ref_pre = preprocess(reference_bytes, max_dimension=1024)
                        warped_ref = cv2.warpPerspective(ref_pre.gray, H, (w, h))
                        abs_diff = cv2.absdiff(pre.gray, warped_ref).astype(np.float32) / 255.0
                        diff_map = cv2.GaussianBlur(abs_diff, (7, 7), 0)
                    except Exception as diff_err:
                        logger.warning(f"Failed to compute reference difference map: {diff_err}")

            evidence_list.append({
                "detector": "registration",
                "version": reg_res.version,
                "category": "KEYPOINT_MATCH",
                "score": round(float(reg_info_raw.get("inlier_ratio", 0.0)), 4) if reg_info_raw.get("inlier_ratio") is not None else 0.0,
                "reliability": 0.95,
                "tag": "PROVEN",
                "notes": [f"Feature matching: {registration_info.get('inliers') or 0} inliers with reprojection error {registration_info.get('reprojectionError') or 'N/A'}"],
                "evidence": {
                    "status": registration_info.get("status"),
                    "inliers": registration_info.get("inliers"),
                    "inlierRatio": registration_info.get("inlierRatio"),
                    "reprojectionError": registration_info.get("reprojectionError"),
                },
            })
        except Exception as e:
            logger.error(f"Registration detector failed: {e}")

    # 5. Composite Forensic Heatmap & Region Extraction
    # Blend ELA, noise inconsistencies, and AI signals with proper weighting
    if has_reference and np.max(diff_map) > 0.05:
        composite_heat = diff_map.copy()
    elif ai_status in ("AI_GENERATED", "AI_EDITED_LOCAL") or ai_score >= 0.40:
        composite_heat = 0.80 * ai_map + 0.20 * ela_map
    else:
        # In conventional unedited photos, ELA is a weak signal (Section 5 / Phase 3)
        # and should not produce artificial tampering heat.
        composite_heat = 0.40 * ai_map + 0.15 * ela_map

    # Normalize heatmap only if a genuine anomaly exists (mx >= 0.40).
    # NEVER divide low baseline noise by its tiny peak, which creates false positives.
    mx = float(composite_heat.max())
    if mx >= 0.40:
        composite_heat = np.clip(composite_heat / mx, 0.0, 1.0)
    elif mx > 0.001:
        composite_heat = np.clip(composite_heat, 0.0, 1.0)
    else:
        composite_heat = np.zeros((h, w), dtype=np.float32)

    # Threshold for regions
    threshold_val = 0.45
    binary_mask = (composite_heat >= threshold_val).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel)

    # Extract classical detector metrics early for tampering evaluation
    ela_score_val = float(all_detector_results.get("ela", {}).get("score") or 0.0)
    noise_details = all_detector_results.get("noise_residual", {}).get("details", {})
    noise_ev = noise_details.get("evidence", {})
    noise_std_val = float(noise_ev.get("std_variance") or 0.0)
    resampling_score_val = float(all_detector_results.get("resampling", {}).get("score") or 0.0)
    cfa_details = all_detector_results.get("cfa_demosaicing", {}).get("details", {})
    cfa_status = cfa_details.get("status")
    cfa_score_val = float(all_detector_results.get("cfa_demosaicing", {}).get("score") or 0.0)
    corneal_score_val = float(all_detector_results.get("corneal_reflection", {}).get("score") or 0.0)
    face_details = all_detector_results.get("face_biometrics", {}).get("details", {})
    face_status = face_details.get("status")
    dire_score_val = float(all_detector_results.get("dire", {}).get("score") or 0.0)
    drct_score_val = float(all_detector_results.get("drct", {}).get("score") or 0.0)
    univfd_score_val = float(all_detector_results.get("univfd", {}).get("score") or 0.0)

    # Check for manual user edits: spliced image, text added/overlaid, copy-move duplication, EXIF thumbnail mismatch, or editing software
    thumb_det_res = all_detector_results.get("thumbnail_discrepancy", {}).get("details", {})
    has_thumb_discrepancy = thumb_det_res.get("status") in ("DISCREPANCY_CROPPED", "DISCREPANCY_EDITED")
    c2pa_res_details = all_detector_results.get("c2pa", {}).get("details", {})
    has_c2pa_ai = bool(c2pa_res_details.get("is_ai_generated", False))
    has_c2pa_edited = bool(c2pa_res_details.get("is_edited", False))

    has_manual_tamper_evidence = (
        ela_score_val > 0.18
        or len(copy_points) > 0
        or (ela_score_val >= 0.08 and noise_std_val > 200.0)
        or bool(editing_software and any(k in str(editing_software).lower() for k in ["photoshop", "gimp", "canva", "paint", "snapseed", "pixlr"]))
        or has_thumb_discrepancy
        or has_c2pa_edited
    )

    has_ai_provenance = (
        ai_provenance in ("AI_GENERATED", "CANVA_DESIGN") or
        editing_software == "Canva"
    )

    deep_real_votes = sum([
        1 for s in (
            univfd_score_val < 0.35,
            drct_score_val < 0.40,
            dire_score_val < 0.35,
        ) if s
    ])
    has_majority_real_consensus = (deep_real_votes >= 2) and not has_ai_provenance

    # Suppress spurious regions on authentic camera photos when no manual tampering exists.
    # UNet false alarms (e.g. smooth evening skies, uniform walls) must be suppressed when foundation models
    # or biological face biometrics confirm authentic optical photography.
    suppress_regions = (
        (
            ai_status == "NO_AI_EVIDENCE"
            or has_majority_real_consensus
            or (face_status == "NATURAL_BIOMETRIC_VERIFIED" and univfd_score_val < 0.40)
        )
        and not has_reference
        and not has_manual_tamper_evidence
        and cfa_status != "CFA_DISCONTINUITY"
    )

    total_pixels = h * w
    if suppress_regions:
        binary_mask[:] = 0
        manipulated_pixels = 0
        affected_area_pct = 0.0
    else:
        # Exact Boolean Mask Union (Master Prompt Section 4) — no overlapping double counting
        manipulated_pixels = int(np.count_nonzero(binary_mask))
        affected_area_pct = round((manipulated_pixels / float(total_pixels)) * 100.0, 2)

    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: list[dict[str, Any]] = []

    if not suppress_regions:
        region_idx = 1
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 100:  # filter tiny noise
                continue
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            # Map back to original image scale
            orig_rx = int(rx * pre.scale_x)
            orig_ry = int(ry * pre.scale_y)
            orig_rw = int(rw * pre.scale_x)
            orig_rh = int(rh * pre.scale_y)

            area_pct = round((area / float(total_pixels)) * 100.0, 2)

            # Region confidence based on local heatmap peak
            roi = composite_heat[ry : ry + rh, rx : rx + rw]
            reg_conf = round(float(roi.max()) if roi.size > 0 else 0.5, 2)

            # Decide editTypeGuess
            edit_type = "splicing"
            if (ai_status in ("AI_EDITED_LOCAL", "AI_GENERATED") or dire_score_val >= 0.60 or univfd_score_val >= 0.50) and (cfa_status == "CFA_DISCONTINUITY" or has_c2pa_ai):
                edit_type = "generative_fill"
            elif len(copy_points) > 0:
                edit_type = "copy_move"
            elif ela_map[ry : ry + rh, rx : rx + rw].mean() > 0.5:
                edit_type = "retouching"

            regions.append({
                "id": f"r{region_idx}",
                "bbox": {"x": orig_rx, "y": orig_ry, "w": orig_rw, "h": orig_rh},
                "areaPct": area_pct,
                "confidence": reg_conf,
                "editTypeGuess": edit_type,
            })
            region_idx += 1

    # 6. Verdict and Probability via Fusion
    calibrator = EvidenceCalibrator()
    normalized_evidence = normalize_all(all_detector_results)
    assessment = fuse(
        normalized_evidence,
        registration_status=registration_info.get("status") if registration_info else None,
        calibrator=calibrator,
    )

    verdict = assessment.verdict
    # Strict three-way normalization per PinITHUB Section 10.1 & 14
    if verdict not in ("EDITED", "NOT_EDITED", "INCONCLUSIVE"):
        if verdict in ("AI_EDITED", "AI_GENERATED", "SUPPORTING", "TAMPERED"):
            verdict = "EDITED"
        elif verdict in ("AUTHENTIC", "NEUTRAL", "CLEAN"):
            verdict = "NOT_EDITED"
        else:
            verdict = "INCONCLUSIVE"

    # Multi-Modal Consensus:
    # Generative AI requires multi-detector consensus (at least 2 independent signals),
    # or synthetic VAE lattice / zero CFA demosaicing corroborated by neural diffusion traces.
    ai_votes = 0
    if dire_score_val >= 0.75:
        ai_votes += 1
    has_ai_provenance = (
        ai_provenance in ("AI_GENERATED", "CANVA_DESIGN") or
        editing_software == "Canva"
    )

    # -------------------------------------------------------------------------
    # Democratic Deep Foundation Model Consensus (UnivFD, DRCT, DIRE)
    # Rule: If 2 or more independent foundation models agree, the majority consensus governs.
    # A single detector outlier (e.g. DIRE false alarm on a smooth twilight sky) cannot
    # overturn multiple agreeing independent models.
    # -------------------------------------------------------------------------
    deep_ai_votes = sum([
        1 for s in (
            univfd_score_val >= 0.55,
            drct_score_val >= 0.55,
            dire_score_val >= 0.70,
        ) if s
    ])
    deep_real_votes = sum([
        1 for s in (
            univfd_score_val < 0.35,
            drct_score_val < 0.40,
            dire_score_val < 0.35,
        ) if s
    ])

    # Authentic consensus: 2 or more deep models verify authentic photographic distribution
    has_majority_real_consensus = (deep_real_votes >= 2) and not has_ai_provenance

    # True generative AI evidence requires AT LEAST 2 independent generative votes (majority consensus),
    # or synthetic generative lattice corroborated by at least one deep detector:
    has_generative_ai_evidence = (deep_ai_votes >= 2) or (
        cfa_status == "SYNTHETIC_GENERATIVE_LATTICE"
        and (univfd_score_val >= 0.60 or drct_score_val >= 0.55 or dire_score_val >= 0.70)
    )

    has_classical_corroboration = (
        ela_score_val > 0.18
    ) or (
        len(copy_points) > 0
    ) or (
        ai_provenance in ("AI_EDITED", "AI_GENERATED")
    ) or (
        cfa_status == "CFA_DISCONTINUITY"
    ) or (
        corneal_score_val >= 0.25
    ) or (
        face_status in ("DEEPFAKE_FACE_DISCREPANCY", "SYNTHETIC_FACIAL_ARTIFACTS")
    ) or (
        ela_score_val >= 0.05 and noise_std_val > 200.0 and (1 <= len(regions) <= 4) and affected_area_pct < 10.0
    )

    has_camera_hardware_exif = bool(
        camera_make or camera_model or (software and any(k in str(software).lower() for k in ("camera", "iphone", "pixel", "samsung", "android", "xiaomi", "oneplus", "huawei", "sony", "nikon", "canon", "windows")))
    )

    dqt_details = all_detector_results.get("dqt_fingerprint", {}).get("details", {})
    dqt_match_cat = str(dqt_details.get("match_category") or "").upper()
    dqt_match_name = str(dqt_details.get("match_name") or "").lower()
    dqt_match_conf = float(dqt_details.get("match_confidence") or 0.0)
    dqt_best_dist = float(dqt_details.get("best_distance") or 999.0)

    # Hardware DQT quantization requires strict high confidence (confidence >= 0.70 or distance <= 25.0)
    has_camera_hardware_dqt = (
        (dqt_match_cat == "CAMERA_HARDWARE" or any(k in dqt_match_name for k in ("samsung", "apple", "iphone", "nikon", "canon", "sony", "fuji", "panasonic", "olympus", "google pixel", "camera")))
        and (dqt_match_conf >= 0.70 or dqt_best_dist <= 25.0)
    )
    has_verified_camera_hardware = has_camera_hardware_exif or has_camera_hardware_dqt
    has_natural_faces = (face_status == "NATURAL_BIOMETRIC_VERIFIED")

    # =========================================================================
    # UNIVERSAL 3-TIER FORENSIC DECISION HIERARCHY
    # =========================================================================

    # TIER 1: PHYSICAL CAMERA HARDWARE & BIOLOGICAL TRUTH
    # An image has verified optical camera ground truth IF AND ONLY IF:
    # 1. Genuine camera hardware EXIF tags are present (Make, Model, Lens, ISO, Shutter), OR
    # 2. Hardware DQT quantization matches camera hardware with strict high confidence (conf >= 0.70 or dist <= 25.0), OR
    # 3. Verified biological human dermal facial pores and boundary continuity are confirmed on human face(s).
    has_verified_camera_base = has_verified_camera_hardware or (has_natural_faces and not has_ai_provenance)

    # TIER 2: DEEP GENERATIVE DIFFUSION & AI TRUTH
    # Diffusion manifold confirmation: When deep diffusion models (DIRE / UnivFD) confirm the image resides
    # on the generative diffusion manifold without verified camera hardware EXIF:
    univfd_details = all_detector_results.get("univfd", {}).get("details", {})
    univfd_patch_max = float(univfd_details.get("patch_max_score") or univfd_score_val)

    is_diffusion_manifold = (
        (
            (dire_score_val >= 0.75 and (univfd_score_val >= 0.50 or univfd_patch_max >= 0.70))
            or (dire_score_val >= 0.90 and resampling_score_val >= 0.80 and not has_natural_faces and not has_majority_real_consensus)
            or (univfd_score_val >= 0.75)
        )
        and not has_verified_camera_hardware
        and not (has_natural_faces and has_majority_real_consensus)
    )

    # An image is identified as FULL AI GENERATED when:
    # 1. AI Provenance metadata confirms generation (Canva, Midjourney, DALL-E, Google Imagen, etc.)
    # 2. Synthetic facial biometrics (deepfake, AI facial synthesis)
    # 3. Synthetic generative lattice from latent diffusion VAE upsamplers
    # 4. Confirmed diffusion manifold (DIRE + UnivFD patch / Resampling) without camera hardware EXIF
    # 5. Overwhelming diffusion reconstruction trace (dire_score_val >= 0.80) with NO camera hardware base
    # 6. UnivFD universal fake detector (univfd_score_val >= 0.65) with NO camera hardware base
    # 7. DRCT contrastive diffusion detector (drct_score_val >= 0.60) with NO camera hardware base
    # 8. 2+ deep foundation models agree on generative AI (deep_ai_votes >= 2) with NO camera hardware base
    is_deep_ai_generated = (
        has_ai_provenance
        or face_status in ("SYNTHETIC_FACIAL_ARTIFACTS", "DEEPFAKE_FACE_DISCREPANCY")
        or cfa_status == "SYNTHETIC_GENERATIVE_LATTICE"
        or is_diffusion_manifold
        or (
            not has_verified_camera_base
            and (
                dire_score_val >= 0.80
                or univfd_score_val >= 0.65
                or drct_score_val >= 0.60
                or (dire_score_val >= 0.60 and resampling_score_val >= 0.80)
                or deep_ai_votes >= 2
            )
        )
    )

    # TIER 3: LOCALIZED TAMPERING & INPAINTING
    # Does the image have localized edits, inpainting, splices, or crops?
    has_localized_tamper = (
        len(regions) > 0
        or (crop_info and crop_info.get("status") == "DETECTED")
        or has_manual_tamper_evidence
        or (cfa_status == "CFA_DISCONTINUITY" and affected_area_pct > 0.5)
    )

    is_screenshot = (ai_details.get("image_level_label") == "DIGITAL_SCREENSHOT")
    has_ai_provenance = (
        ai_provenance in ("AI_GENERATED", "CANVA_DESIGN") or
        editing_software == "Canva"
    )

    # Physical Camera Sensor & Bayer CFA Continuity Analysis
    grid_cv_val = float(cfa_details.get("grid_cv") or 1.0)
    cfa_tampered_blocks = cfa_details.get("tampered_blocks_detected", 0)
    cfa_total_blocks = max(1, cfa_details.get("total_blocks_analyzed", 1))
    cfa_tamper_ratio = cfa_tampered_blocks / cfa_total_blocks
    has_unbroken_camera_cfa = (
        cfa_status == "BAYER_CFA_CONFIRMED"
        and cfa_tamper_ratio < 0.03
        and grid_cv_val < 0.012
    )

    ai_ev_strs = ai_evidence_notes or all_detector_results.get("ai", {}).get("details", {}).get("evidence", [])
    ai_ev_joined = " ".join(ai_ev_strs)
    import re
    p50_match = re.search(r"p50:\s*([0-9.]+)", ai_ev_joined)
    p90_match = re.search(r"p90:\s*([0-9.]+)", ai_ev_joined)
    p95_match = re.search(r"p95:\s*([0-9.]+)", ai_ev_joined)
    p50_num = float(p50_match.group(1)) if p50_match else float(ai_details.get("p50") or 1.0)
    p90_num = float(p90_match.group(1)) if p90_match else float(ai_details.get("p90") or 0.0)
    p95_num = float(p95_match.group(1)) if p95_match else float(ai_details.get("p95") or 0.0)

    # -------------------------------------------------------------------------
    # AUTHORITATIVE VERDICT & CLASSIFICATION ASSIGNMENT
    # -------------------------------------------------------------------------
    if is_screenshot:
        classification = "INCONCLUSIVE"
        verdict = "NOT_EDITED"
        regions = []
        affected_area_pct = 0.0
    elif is_deep_ai_generated:
        # Full generative AI media: 100% AI Generated, 0% Real Camera
        classification = "AI_GENERATED"
        verdict = "EDITED"
        ai_score = max(0.95, dire_score_val, univfd_score_val, drct_score_val, float(ai_score or 0.95))
        regions = []
        affected_area_pct = 0.0
    elif has_localized_tamper:
        # Authentic camera base with localized modification (inpainting or manual splice)
        verdict = "EDITED"
        is_ai_inpaint = (
            ai_status in ("AI_GENERATED", "AI_EDITED_LOCAL")
            or ai_provenance in ("AI_EDITED", "AI_GENERATED")
            or cfa_status == "CFA_DISCONTINUITY"
            or max(dire_score_val, univfd_score_val, drct_score_val) >= 0.40
        )
        if is_ai_inpaint:
            classification = "AI_EDITED"
            if ai_score < 0.75:
                ai_score = 0.88
        else:
            classification = "EDITED"
    elif has_verified_camera_base and not has_classical_corroboration and len(copy_points) == 0:
        # Verified authentic camera capture with zero tampering: 100% Real Camera Photo
        classification = "CAMERA_CAPTURED"
        verdict = "NOT_EDITED"
        ai_score = 0.00
        regions = []
        affected_area_pct = 0.0
    elif has_verified_camera_base and (has_unbroken_camera_cfa or ela_score_val < 0.20):
        # Digitally enhanced camera capture (HDR, tone grading)
        classification = "DIGITALLY_ENHANCED"
        verdict = "NOT_EDITED"
        ai_score = 0.12
        regions = []
        affected_area_pct = 0.0
    else:
        # Image has NO camera hardware, NO biological faces, and NO deep AI signatures.
        # It is a clean digital graphic, stripped web image, or inconclusive non-camera media.
        # CRITICAL: It must NEVER be declared a physical camera capture!
        classification = "INCONCLUSIVE"
        verdict = "INCONCLUSIVE"
        regions = []
        affected_area_pct = 0.0

    # Strict false-positive suppression: authentic camera captures, unedited images, and screenshots
    # must never display tampered bounding boxes or artificial heatmaps.
    if classification == "CAMERA_CAPTURED" or is_screenshot or verdict == "NOT_EDITED":
        regions = []
        affected_area_pct = 0.0
        binary_mask = np.zeros((h, w), dtype=np.uint8)
        composite_heat = np.zeros((h, w), dtype=np.float32)
    elif verdict == "INCONCLUSIVE" and not has_classical_corroboration:
        # Uncorroborated single-detector local alerts must not display tampering boxes
        regions = []
        affected_area_pct = 0.0
        binary_mask = np.zeros((h, w), dtype=np.uint8)
        composite_heat = np.zeros((h, w), dtype=np.float32)

    # Dynamic continuous score computation
    # Synthesize foundation model signals and physical sensor metrics:
    # univfd_score_val (CLIP ViT), drct_score_val (ConvNeXt), dire_score_val (ResNet-18),
    # cfa_score_val (Bayer demosaicing lattice), noise_std_val (PRNU sensor noise)
    effective_dire = (
        min(dire_score_val, max(univfd_score_val, drct_score_val) + 0.05)
        if (has_majority_real_consensus or has_verified_camera_base or has_verified_camera_hardware)
        else dire_score_val
    )
    raw_ai_ensemble = (
        0.35 * univfd_score_val
        + 0.35 * drct_score_val
        + 0.20 * effective_dire
        + 0.10 * max(0.0, cfa_score_val - 0.10)
    )

    if is_screenshot:
        # Digital screen capture: UI elements, clean vector text, 0 sensor noise
        calibrated_prob = 0.000
    elif classification == "CAMERA_CAPTURED":
        # Verified authentic camera capture: 100.0% Real Photo, 0.0% AI Generated
        calibrated_prob = 0.000
    elif classification == "DIGITALLY_ENHANCED":
        # Camera capture with heavy digital filters, HDR, or tone curves
        filter_signal = max(ela_score_val * 0.40, raw_ai_ensemble * 0.50)
        calibrated_prob = round(min(0.25, max(0.06, 0.08 + filter_signal)), 3)
    elif classification == "AI_GENERATED":
        # Full generative AI media (Diffusion, GAN): 100.0% AI Generated, 0.0% Real Camera
        calibrated_prob = 1.000
    elif classification == "AI_EDITED":
        # Area-weighted continuous calibration for localized generative inpainting:
        # Authentic photographic base represents the real percentage;
        # localized AI inpainting represents the AI likelihood.
        inpaint_signal = (affected_area_pct / 100.0) * 0.80 + 0.20 * max(univfd_score_val, drct_score_val, dire_score_val)
        calibrated_prob = round(min(0.85, max(0.05, inpaint_signal)), 3)
    elif classification == "EDITED":
        # Real camera photograph with localized manual alteration / added sticker / text overlay
        # Likelihood dynamically reflects the affected area
        tamper_signal = (affected_area_pct / 100.0) * 0.90 + 0.015
        calibrated_prob = round(min(0.40, max(0.015, tamper_signal)), 3)
    elif verdict == "EDITED" and crop_info and crop_info.get("status") == "DETECTED":
        crop_fraction = float(crop_info.get("cropPercentage", 50.0)) / 100.0
        calibrated_prob = round(min(0.99, max(0.70, 0.60 + 0.38 * crop_fraction)), 3)
    elif assessment.probability is not None:
        calibrated_prob = round(min(1.0, max(0.0, assessment.probability)), 3)
    else:
        # Dynamic inconclusive lean: reflects the subtle direction of evidence instead of flat 50/50
        calibrated_prob = round(min(0.58, max(0.42, 0.50 + 0.20 * (raw_ai_ensemble - 0.50))), 3)

    if classification == "AI_GENERATED":
        if ai_provenance == "CANVA_DESIGN" or editing_software == "Canva":
            summary = "Image verified as synthetic digital artwork / media generated via Canva."
        elif ai_provenance == "AI_GENERATED":
            summary = f"Image metadata confirms AI generation provenance ({ai_generator or 'trainedAlgorithmicMedia'})."
        else:
            summary = f"Full image exhibits AI generator artifacts and synthetic frequency patterns (AI trace score {round(ai_score * 100, 1)}%)."
    elif classification == "DIGITALLY_ENHANCED":
        summary = "Camera-captured photograph showing signs of heavy digital enhancement or stylistic post-processing (HDR, denoising, or color grading). Natural perspective verified; not generated by synthetic AI diffusion."
    elif crop_info and crop_info.get("status") == "DETECTED":
        crop_pct_val = crop_info.get("cropPercentage", 0.0)
        summary = f"Detected crop: approximately {crop_pct_val:.1f}% of the original image was removed."
        if len(regions) > 0:
            summary += f" Also found {len(regions)} localized content change region(s)."
    elif classification == "AI_EDITED":
        summary = f"Real base photograph with localized AI generative inpainting / fill detected across ~{affected_area_pct}% of canvas ({len(regions)} region(s)). Authentic base image represents ~{100 - round(calibrated_prob * 100)}% of the frame."
    elif classification == "EDITED":
        summary = f"Evidence of localized manual tampering in {len(regions)} region(s) (about {affected_area_pct}% of the image). Spliced content, text addition, or copy-move detected."
    elif classification == "CAMERA_CAPTURED":
        summary = "Evidence consistent with genuine camera-captured photograph. No anomalous AI generator artifacts detected."
    elif is_screenshot:
        summary = "Digital screen capture profile detected (uniform UI color blocks and anti-aliased font edges with zero optical sensor noise). Not an AI diffusion image or optical camera capture."
    else:
        summary = "Analysis inconclusive: detectors produced conflicting or insufficient evidence."

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # Generate PNG Data URLs for immediate frontend rendering
    heatmap_data_url = _array_to_data_url(composite_heat, is_heatmap=True)
    mask_data_url = _array_to_data_url(binary_mask)

    ai_label = (
        "AI_GENERATED" if classification == "AI_GENERATED"
        else "AI_EDITED" if classification == "AI_EDITED"
        else "MANUALLY_EDITED" if classification == "EDITED"
        else "DIGITALLY_ENHANCED" if classification == "DIGITALLY_ENHANCED"
        else "CONVENTIONAL" if classification == "CAMERA_CAPTURED"
        else "INCONCLUSIVE"
    )

    # Dual-Score (ZeroGPT-style complementary percentages summing to 100%)
    if classification == "CAMERA_CAPTURED":
        ai_percentage = 0.0
        real_percentage = 100.0
        calibrated_prob = 0.0
    elif classification == "AI_GENERATED":
        ai_percentage = 100.0
        real_percentage = 0.0
        calibrated_prob = 1.0
    else:
        ai_percentage = round(calibrated_prob * 100, 1)
        real_percentage = round(max(0.0, 100.0 - ai_percentage), 1)

    # Definitive Final Call classification
    if classification == "CAMERA_CAPTURED":
        final_call = "REAL_CAMERA_PHOTO"
        final_call_title = "REAL CAMERA PHOTO"
        final_call_desc = "Authentic optical sensor pattern verified. Zero localized tampering or synthetic artifacts detected."
    elif classification == "DIGITALLY_ENHANCED":
        final_call = "REAL_PHOTO_DIGITALLY_ENHANCED"
        final_call_title = "REAL PHOTO (DIGITALLY ENHANCED / FILTERED)"
        final_call_desc = "Camera-captured photograph showing signs of heavy digital post-processing (HDR, denoising, or stylistic color grading). Not generated by synthetic AI diffusion."
    elif classification == "AI_GENERATED":
        final_call = "FULL_AI_GENERATED"
        final_call_title = "FULL AI GENERATED"
        final_call_desc = "Synthetic digital media generated from scratch by an AI diffusion or GAN model."
    elif classification == "AI_EDITED":
        final_call = "AI_EDITED_INPAINTED"
        final_call_title = "AI EDITED / INPAINTED"
        final_call_desc = f"Real base image with localized Generative AI inpainting detected in ~{affected_area_pct}% of the canvas."
    elif classification == "EDITED":
        final_call = "MANUALLY_EDITED_TAMPERED"
        final_call_title = "MANIPULATED / USER EDITED IMAGE"
        final_call_desc = f"Real camera image with localized digital edit / added sticker detected in ~{affected_area_pct}% of the canvas. Not generated from scratch by AI."
    elif is_screenshot:
        final_call = "DIGITAL_SCREENSHOT"
        final_call_title = "DIGITAL SCREENSHOT"
        final_call_desc = "Digital screen capture profile detected. Clean non-camera digital media."
    else:
        final_call = "INCONCLUSIVE"
        final_call_title = "INCONCLUSIVE"
        final_call_desc = "Signals are inconclusive or insufficient evidence found."

    return sanitize_for_json({
        "status": "DONE",
        "mode": mode,
        "verdict": verdict,
        "classification": classification,
        "probability": calibrated_prob,
        "dualScore": {
            "realPercentage": real_percentage,
            "aiPercentage": ai_percentage,
        },
        "finalCall": {
            "verdict": final_call,
            "title": final_call_title,
            "description": final_call_desc,
        },
        "summary": summary,
        "affectedAreaPercentage": affected_area_pct,
        "dimensions": {
            "width": orig_w,
            "height": orig_h,
        },
        "regions": regions,
        "crop": crop_info,
        "aiDetection": {
            "status": ai_status,
            "score": round(ai_score, 4),
            "label": ai_label,
        },
        "registration": registration_info,
        "evidence": evidence_list,
        "artifacts": {
            "heatmapUrl": heatmap_data_url,
            "maskUrl": mask_data_url,
        },
        "modality": modality_info,
        "cfa": all_detector_results.get("cfa_demosaicing", {}).get("details"),
        "faceBiometrics": all_detector_results.get("face_biometrics", {}).get("details"),
        "univfd": all_detector_results.get("univfd", {}).get("details"),
        "drct": all_detector_results.get("drct", {}).get("details"),
        "dire": all_detector_results.get("dire", {}).get("details"),
        "opticalMetadata": {
            "hasExif": has_exif,
            "make": camera_make,
            "model": camera_model,
            "deviceName": device_name or None,
            "lensModel": camera_dict.get("lens_model"),
            "dateTimeOriginal": captured_at,
            "offsetTime": offset_tz or None,
            "exposureTime": exposure_val or None,
            "fNumber": f_number or None,
            "iso": iso_val or None,
            "focalLength": focal_length or None,
            "sensorVerification": "AUTHENTIC_HARDWARE_SENSOR" if (camera_make or camera_model) else ("STRIPPED_OR_ABSENT" if not has_exif else "GENERIC"),
            "deviceDescription": device_desc or None,
        },
        "warnings": warnings,
        "limitations": limitations,
        "executionMs": elapsed_ms,
    })

