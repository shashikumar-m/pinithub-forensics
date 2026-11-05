"""
PINITHUB Forensics — FastAPI application entry point.

Phase 4: Image registration & comparison pipeline added.
"""
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load root .env
root_env = Path(__file__).resolve().parents[3] / ".env"
if root_env.is_file():
    load_dotenv(root_env)
else:
    load_dotenv()

# Automatically configure AI weights path if file exists in models directory
if not os.environ.get("AI_WEIGHTS_PATH"):
    default_model = Path(__file__).resolve().parents[3] / "models" / "ai_detector_v1.pth"
    if default_model.is_file():
        os.environ["AI_WEIGHTS_PATH"] = str(default_model)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.config import get_settings
from app.models.schemas import HealthResponse, ReadyResponse, AvailableDetectorSchema
from app.detectors.metadata_inspector import get_metadata_inspector
from app.detectors.ela import get_ela_detector
from app.detectors.noise_residual import get_noise_residual_detector
from app.detectors.dct_analysis import get_dct_analysis_detector
from app.detectors.jpeg_double_compression import get_jpeg_double_compression_detector
from app.detectors.resampling import get_resampling_detector
from app.detectors.jpeg_grid import get_jpeg_grid_detector
from app.detectors.copy_move import get_copy_move_detector
from app.detectors.registration import get_registration_detector
from app.detectors.crop_detector import get_crop_detector
from app.detectors.ai_detector import get_ai_detector
from app.pipelines.classical_pipeline import run_classical_pipeline
from app.pipelines.comparison_pipeline import run_comparison_pipeline
from app.pipelines.unified_analysis import run_unified_analysis
from app.utils.json_utils import sanitize_for_json

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("pinithub-forensics")

app = FastAPI(
    title="PINITHUB Forensics Service",
    description="Image forensics detection and analysis service",
    version="0.4.0",
)


class InspectRequest(BaseModel):
    """Request body for detector inspection (bytes as hex string)."""
    image_hex: str
    image_id: Optional[str] = None
    stored_sha256: Optional[str] = None
    params: Optional[dict] = None


class ComparisonRequest(BaseModel):
    """Request body for image comparison."""
    reference_hex: str
    suspect_hex: str
    params: Optional[dict] = None


class AnalyzeRequest(BaseModel):
    """Unified forensic analysis request body."""
    image_hex: str
    reference_hex: Optional[str] = None
    params: Optional[dict] = None


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/ready", response_model=ReadyResponse)
async def ready():
    return ReadyResponse(
        status="ok",
        checks={
            "detectors": "ok",
            "metadata_inspector": "ok",
            "classical_pipeline": "ok",
            "storage": "skipped",
            "database": "skipped",
        },
    )


@app.get("/detectors", response_model=list[AvailableDetectorSchema])
async def list_detectors():
    """Lists all available detectors with their implementation status."""
    detectors = [
        get_metadata_inspector(),
        get_ela_detector(),
        get_noise_residual_detector(),
        get_dct_analysis_detector(),
        get_jpeg_double_compression_detector(),
        get_resampling_detector(),
        get_jpeg_grid_detector(),
        get_copy_move_detector(),
        get_registration_detector(),
        get_crop_detector(),
        get_ai_detector(),
    ]
    return [
        AvailableDetectorSchema(
            name=d.name,
            version=d.version,
            category=d.category.value,
            implemented=True,
        )
        for d in detectors
    ]


@app.post("/v1/inspect/metadata")
async def inspect_metadata(req: InspectRequest):
    """Run metadata inspection."""
    try:
        image_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    inspector = get_metadata_inspector()
    result = inspector.timed_run("", image_bytes=image_bytes)
    return result.to_dict()


@app.post("/v1/inspect/classical-pipeline")
async def inspect_classical_pipeline(req: InspectRequest):
    """
    Run all classical forensic detectors in one call.
    Returns independent results — no fusion or final verdict.
    """
    try:
        image_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    kwargs = {}
    if req.params:
        kwargs["params"] = req.params

    return run_classical_pipeline(image_bytes, **kwargs)


@app.post("/v1/inspect/{detector_name}")
async def inspect_single_detector(detector_name: str, req: InspectRequest):
    """Run a single specific detector on the image."""
    try:
        image_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    kwargs = {}
    if req.params:
        kwargs["params"] = req.params

    detector_map = {
        "ela": get_ela_detector,
        "noise_residual": get_noise_residual_detector,
        "dct_analysis": get_dct_analysis_detector,
        "jpeg_double_compression": get_jpeg_double_compression_detector,
        "resampling": get_resampling_detector,
        "jpeg_grid": get_jpeg_grid_detector,
        "copy_move": get_copy_move_detector,
        "metadata_inspector": get_metadata_inspector,
    }

    getter = detector_map.get(detector_name)
    if getter is None:
        raise HTTPException(status_code=404, detail=f"Unknown detector: {detector_name}")

    detector = getter()
    result = detector.timed_run("", image_bytes=image_bytes, **kwargs)
    return result.to_dict()


@app.get("/")
async def root():
    return {
        "service": "pinithub-forensics",
        "version": "0.4.0",
        "phase": "Phase 4 — Image Registration & Reference Comparison",
        "detectors": ["ela", "noise_residual", "dct_analysis",
                       "jpeg_double_compression", "resampling",
                       "jpeg_grid", "copy_move", "metadata_inspector",
                       "registration", "crop_detector", "ai_detector"],
        "endpoints": ["/health", "/ready", "/detectors",
                       "/v1/inspect/{detector_name}", "/v1/inspect/classical-pipeline",
                       "/v1/compare", "/v1/crop-detect", "/v1/ai-detect"],
    }


@app.post("/v1/analyze")
async def analyze_full(req: AnalyzeRequest):
    """
    Unified forensic analysis endpoint (Phase 2-8 + Crop_plan.pdf).
    Accepts suspect image (and optional reference image) as hex strings.
    Runs classical, AI, metadata, and (if reference provided) crop detection.
    Returns the complete Section 10.1 result shape.
    """
    try:
        suspect_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded suspect image data")
    if len(suspect_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty suspect image data")

    ref_bytes = None
    if req.reference_hex:
        try:
            ref_bytes = bytes.fromhex(req.reference_hex)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid hex-encoded reference image data")

    try:
        result = run_unified_analysis(suspect_bytes, reference_bytes=ref_bytes, params=req.params)
        return sanitize_for_json(result)
    except Exception as e:
        logger.error("Unified analysis failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {type(e).__name__}")


@app.post("/v1/compare")
async def compare_images(req: ComparisonRequest):
    """
    Register and compare a suspect image against a protected reference.

    Both images are passed as hex-encoded byte strings.
    Returns registration evidence and difference analysis.
    No final authenticity verdict is produced.
    """
    try:
        reference_bytes = bytes.fromhex(req.reference_hex)
        suspect_bytes = bytes.fromhex(req.suspect_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")

    if len(reference_bytes) == 0 or len(suspect_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    try:
        result = run_comparison_pipeline(reference_bytes, suspect_bytes, req.params)
    except Exception as e:
        logger.error("Comparison pipeline failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {type(e).__name__}")

    return sanitize_for_json(result)


@app.post("/v1/crop-detect")
async def detect_crop(req: ComparisonRequest):
    """
    Detect crop percentage between a protected original and suspect copy.

    Uses Phase 4 registration (homography) to project suspect boundaries
    into original coordinates, then computes polygon area to determine
    the percentage of the original that was removed.

    All coordinates are in ORIGINAL_IMAGE_COORDINATES.
    No final authenticity verdict is produced.
    """
    try:
        reference_bytes = bytes.fromhex(req.reference_hex)
        suspect_bytes = bytes.fromhex(req.suspect_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")

    if len(reference_bytes) == 0 or len(suspect_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    detector = get_crop_detector()
    try:
        result = detector.timed_run(
            "",
            reference_bytes=reference_bytes,
            suspect_bytes=suspect_bytes,
            params=req.params,
        )
    except Exception as e:
        logger.error("Crop detection failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Crop detection failed: {type(e).__name__}")

    return sanitize_for_json(result.to_dict())


@app.post("/v1/ai-detect")
async def detect_ai(req: InspectRequest):
    """
    Run AI-generated / AI-edited detection on an image.

    Returns:
      status: AI_GENERATED | AI_EDITED_LOCAL | NO_AI_EVIDENCE | INCONCLUSIVE | UNAVAILABLE
      image_level_score: raw sigmoid mean (UNCALIBRATED, NOT a probability)
      regions: list of candidate AI-edited regions
      model / version / calibration_status

    IMPORTANT: Model weights must be trained before meaningful results are produced.
    Without weights, status = UNAVAILABLE.
    Results are experimental and UNCALIBRATED.
    """
    try:
        image_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")

    detector = get_ai_detector()
    try:
        result = detector.timed_run("", image_bytes=image_bytes,
                                     params=req.params or {})
    except Exception as e:
        logger.error("AI detection failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI detection failed: {type(e).__name__}")

    return sanitize_for_json(result.to_dict())


# ---- Phase 7: Travel analysis ----

class TravelAnalysisRequest(BaseModel):
    """Request body for travelled-copy analysis."""
    reference_hex: str
    suspect_hex: str
    reference_metadata: Optional[dict] = None
    suspect_metadata: Optional[dict] = None


class TravelGenerateRequest(BaseModel):
    """Request body for generating a travelled copy."""
    image_hex: str
    profile: str = "WHATSAPP_LIKE"


@app.post("/v1/travel-analyze")
async def travel_analyze(req: TravelAnalysisRequest):
    """
    Analyze a suspect copy against the protected reference.
    Detects transport and content transformations.
    Does NOT produce a final verdict.
    """
    from app.travel.travel_analyzer import analyze_travelled_copy
    try:
        ref_bytes = bytes.fromhex(req.reference_hex)
        sus_bytes = bytes.fromhex(req.suspect_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")

    try:
        result = analyze_travelled_copy(
            ref_bytes, sus_bytes,
            req.reference_metadata, req.suspect_metadata,
        )
        return result.to_dict()
    except Exception as e:
        logger.error("Travel analysis failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Travel analysis failed: {type(e).__name__}")


@app.post("/v1/travel-generate")
async def travel_generate(req: TravelGenerateRequest):
    """
    Generate a travelled copy using a platform-like profile.
    Returns hex-encoded output + manifest.
    """
    from app.travel.generator import generate_travelled_copy
    from app.travel.platform_profiles import get_profile
    try:
        image_bytes = bytes.fromhex(req.image_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded image data")

    try:
        profile = get_profile(req.profile)
        output_bytes, manifest = generate_travelled_copy(
            image_bytes, profile["steps"],
            severity="TRANSPORT",
        )
        return {
            "output_hex": output_bytes.hex(),
            "manifest": manifest.to_dict(),
            "profile": req.profile,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Travel generation failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Travel generation failed: {type(e).__name__}")


@app.get("/v1/travel-profiles")
async def list_travel_profiles():
    """List available platform-like transformation profiles."""
    from app.travel.platform_profiles import PLATFORM_PROFILES
    return {
        "profiles": [
            {"name": k, "description": v["description"], "disclaimer": v["disclaimer"]}
            for k, v in PLATFORM_PROFILES.items()
        ]
    }


# ---- Phase 8: Investigation / Evidence Fusion ----

class InvestigateRequest(BaseModel):
    """Full investigation request — runs all available detectors and fuses results."""
    reference_hex: str
    suspect_hex: str
    reference_metadata: Optional[dict] = None
    suspect_metadata: Optional[dict] = None
    investigation_id: Optional[str] = None


@app.post("/v1/investigate")
async def investigate(req: InvestigateRequest):
    """
    Full investigation pipeline: runs all available detectors,
    normalizes evidence, fuses into a verdict, and returns a
    canonical investigation result + tamper-evident seal.

    No final probability is returned unless calibration is validated.
    """
    from app.fusion.normalizer import normalize_all
    from app.fusion.verdict_engine import fuse
    from app.fusion.region_fusion import fuse_regions
    from app.fusion.report_generator import (
        build_canonical_report, canonical_json, seal_report, generate_text_report
    )
    from app.travel.travel_analyzer import analyze_travelled_copy
    import hashlib, uuid, io as _io

    try:
        ref_bytes = bytes.fromhex(req.reference_hex)
        sus_bytes = bytes.fromhex(req.suspect_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hex-encoded data")

    inv_id = req.investigation_id or str(uuid.uuid4())
    limitations = [
        "AI detection is experimental and UNCALIBRATED — requires trained model weights.",
        "Classical forensic signals are not individually definitive.",
        "Metadata is evidence, not proof of authenticity.",
        "Platform simulation profiles are approximate, not exact reproductions.",
        "Heavy crops may produce INCONCLUSIVE results.",
        "Compression can destroy forensic signals.",
        "Fusion weights are heuristic (UNCALIBRATED) — no calibrated probability is produced.",
    ]

    # ---- 1. Travel analysis (orchestrates Phase 3–7 detectors) ----
    travel_result = analyze_travelled_copy(
        ref_bytes, sus_bytes,
        req.reference_metadata, req.suspect_metadata,
    )

    # ---- 2. Individual classical detectors for evidence normalization ----
    all_results = {
        "registration": travel_result.registration_quality,
        "crop": travel_result.crop,
        "ai": travel_result.ai_detection,
        "travel": travel_result.to_dict(),
        "metadata": req.reference_metadata,
    }

    # Run individual detectors for richer evidence
    for name, get_fn in [
        ("ela", get_ela_detector),
        ("noise", get_noise_residual_detector),
        ("dct", get_dct_analysis_detector),
        ("double_compression", get_jpeg_double_compression_detector),
    ]:
        try:
            det = get_fn()
            r = det.run("", image_bytes=sus_bytes)
            all_results[name] = r.to_dict()
        except Exception:
            pass

    # ---- 3. Normalize evidence ----
    evidence_items = normalize_all(all_results)

    # ---- 4. Fuse into verdict ----
    reg_status = (travel_result.registration_quality or {}).get("status")
    assessment = fuse(evidence_items, registration_status=reg_status)

    # ---- 5. Fuse regions ----
    travel_changes = travel_result.changes
    diff_regions = None  # would come from comparison diff map in production
    ai_res = travel_result.ai_detection or {}

    # Try to get original dimensions
    try:
        from app.io.preprocessing import preprocess
        ref_pre = preprocess(ref_bytes, max_dimension=2048)
        orig_w, orig_h = ref_pre.original_width, ref_pre.original_height
    except Exception:
        orig_w, orig_h = 1, 1

    final_regions = fuse_regions(
        crop_result=travel_result.crop,
        ai_result=ai_res,
        travel_changes=[c.to_dict() if hasattr(c, 'to_dict') else c for c in (travel_changes or [])],
        diff_regions=diff_regions,
        original_width=orig_w,
        original_height=orig_h,
    )

    # ---- 6. Build canonical report ----
    meta_changes = [m.to_dict() if hasattr(m, 'to_dict') else m
                    for m in (travel_result.metadata_changes or [])]

    report = build_canonical_report(
        investigation_id=inv_id,
        verdict=assessment.verdict,
        confidence_status=assessment.confidence_status,
        evidence_strength=assessment.evidence_strength,
        explanation=assessment.explanation,
        warnings=assessment.warnings,
        fusion_version=assessment.fusion_version,
        reference_image=req.reference_metadata,
        suspect_image=req.suspect_metadata,
        registration=travel_result.registration_quality,
        metadata_changes=meta_changes,
        transformations=travel_result.transformations,
        evidence_items=evidence_items,
        regions=final_regions,
        crop=travel_result.crop,
        ai_detection=ai_res,
        limitations=limitations,
    )

    # ---- 7. Seal ----
    report_json_str = canonical_json(report)
    seal = seal_report(report_json_str)
    report_hash = seal["reportHash"]

    # ---- 8. Build text report ----
    text_report = generate_text_report(report)

    return sanitize_for_json({
        "investigationId": inv_id,
        "verdict": assessment.verdict,
        "confidenceStatus": assessment.confidence_status,
        "evidenceStrength": assessment.evidence_strength,
        "explanation": assessment.explanation,
        "warnings": assessment.warnings,
        "evidenceItems": [e.to_dict() for e in evidence_items],
        "regions": [r.to_dict() for r in final_regions],
        "transformations": travel_result.transformations,
        "metadataChanges": meta_changes,
        "crop": travel_result.crop,
        "aiDetection": ai_res,
        "registrationQuality": travel_result.registration_quality,
        "reportHash": report_hash,
        "seal": seal,
        "report": report,
        "textReport": text_report,
        "limitations": limitations,
    })
