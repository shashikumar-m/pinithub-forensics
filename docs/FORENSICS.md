# Forensics Service

## Core Principle

**Every detector produces evidence — not verdicts.**

No detector is allowed to claim "100% edited" or "100% authentic". Each detector
returns an independent forensic signal. No fusion or final authenticity verdict exists
until Phase 6.

---

## Architecture

```
services/forensics/
├── app/
│   ├── main.py                    — FastAPI app v0.3.0
│   ├── config.py                  — pydantic-settings config
│   ├── models/schemas.py          — Pydantic API schemas
│   ├── io/
│   │   └── preprocessing.py       — ✅ Phase 3: image loading, resize, artifact encoding
│   ├── detectors/
│   │   ├── base.py                — BaseDetector + DetectorResult abstract contract
│   │   ├── metadata_inspector.py  — ✅ Phase 2: EXIF + characteristics
│   │   ├── ela.py                 — ✅ Phase 3: Error Level Analysis
│   │   ├── noise_residual.py      — ✅ Phase 3: Noise/residual analysis
│   │   ├── dct_analysis.py        — ✅ Phase 3: DCT/JPEG coefficient analysis
│   │   ├── jpeg_double_compression.py — ✅ Phase 3: Recompression evidence
│   │   ├── resampling.py          — ✅ Phase 3: Interpolation/resize detection
│   │   ├── jpeg_grid.py           — ✅ Phase 3: JPEG 8×8 grid/blocking analysis
│   │   └── copy_move.py           — ✅ Phase 3: Copy-move detection (ORB)
│   └── pipelines/
│       └── classical_pipeline.py  — ✅ Phase 3: Runs all 7 classical detectors
├── tests/
│   ├── test_classical_detectors.py — ✅ 33 tests
│   ├── test_metadata_inspector.py  — ✅ 21 tests
│   └── test_health/ready/detector  — ✅ 9 tests
└── requirements.txt               — Pillow, numpy, opencv-headless, scipy
```

---

## Implemented Detectors (Phase 3)

| Detector | Version | Category | Score Semantics |
|----------|---------|----------|-----------------|
| `ela` | 1.0.0 | ELA | Mean normalized recompression error (0–1) |
| `noise_residual` | 1.0.0 | NOISE_RESIDUAL | Mean local residual variance (0–1) |
| `dct_analysis` | 1.0.0 | DCT | DC energy ratio (0–1) |
| `jpeg_double_compression` | 1.0.0 | JPEG_DOUBLE_COMPRESSION | Histogram gap indicator (0–1) |
| `resampling` | 1.0.0 | KEYPOINT_MATCH | Periodicity strength (0–1) |
| `jpeg_grid` | 1.0.0 | DCT | Normalized blocking strength (0–1) |
| `copy_move` | 1.0.0 | COPY_MOVE | Geometric consistency ratio (0–1) |
| `metadata_inspector` | 1.0.0 | METADATA | No score — evidence only |

**All scores are UNCALIBRATED.** They are not probabilities.

---

## Detector Descriptions

### ELA — Error Level Analysis
Saves a re-decoded image at controlled JPEG quality (default 85), then computes the
absolute pixel error between original and recompressed. Bright regions in the ELA map
can indicate areas that were saved at a different quality level.

**Limitations:** Sensitive to original JPEG quality. Natural high-frequency regions
produce high ELA. Does not prove manipulation.

### Noise Residual Analysis
Applies a median filter, then computes the residual (original minus filtered). Local
variance of the residual is measured in blocks. Inconsistency between regions may
indicate local image manipulation.

**Limitations:** Natural texture, ISO noise, and JPEG compression all affect residuals.

### DCT / JPEG Analysis
Extracts 8×8 DCT blocks from the JPEG image, computes coefficient histograms,
DC/AC energy statistics, and the blocking artifact measure. Also extracts
quantization tables via Pillow.

**Applicability:** JPEG only. Returns `NOT_APPLICABLE` for PNG/WebP.

### JPEG Double-Compression Evidence
Looks for gaps in DCT coefficient histograms — a signature that can appear when a
JPEG image has been re-quantized (saved twice at different quality levels).

**Limitations:** Social media processing, screenshots, and successive recompression
all introduce similar patterns.

### Resampling Detection
Applies a high-pass residual then measures autocorrelation in row/column variance
profiles to detect periodic resampling artifacts.

**Limitations:** Natural periodic structures can produce false signals. A resized
image is not necessarily a manipulated image.

### JPEG Grid / Blocking Analysis
Measures the boundary-versus-interior pixel difference at 8-pixel intervals.
High inconsistency between JPEG block boundaries may indicate pasted regions or
local recompression.

**Applicability:** JPEG only.

### Copy-Move Detection
Uses ORB keypoint detection and Hamming-distance matching to find internally
duplicated regions within the same image. A Lowe ratio test and minimum-distance
filter reject trivial neighbors. RANSAC verifies geometric consistency.

**Conservative design:** Requires minimum geometrically consistent matches.
Repeated natural structures (windows, patterns, bricks) are acknowledged as
hard negatives.

---

## Classical Pipeline

`POST /v1/inspect/classical-pipeline`

Runs all 7 detectors in sequence. Each failure is isolated — others continue.
Returns independent results. No fusion. No final verdict.

```json
{
  "pipeline": "classical_forensics",
  "pipeline_version": "1.0.0",
  "results": [ ... ],
  "summary": { "total": 7, "completed": 5, "failed": 0, "not_applicable": 2 },
  "note": "These are independent forensic signals. No fusion or final verdict is produced."
}
```

---

## Score Semantics

Every detector documents what its score means. Scores are **NOT** automatically
probabilities. Raw detector scores are never labeled as "92% chance edited".

Reliability is marked `UNCALIBRATED` on all Phase 3 detectors — scientific
calibration is planned for Phase 6.

---

## Planned (NOT YET IMPLEMENTED)

| Feature | Phase |
|---------|-------|
| AI-generated detection (classifier) | Phase 4 |
| AI-edit / inpainting detection | Phase 4 |
| UNet / SegFormer segmentation | Phase 4 |
| Original-vs-suspect reference comparison | Phase 3+ |
| Evidence fusion / calibration | Phase 6 |
| Final authenticity verdict | Phase 6 |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness |
| `GET` | `/detectors` | List all 8 implemented detectors |
| `POST` | `/v1/inspect/metadata` | Run metadata inspector |
| `POST` | `/v1/inspect/{detector_name}` | Run any single detector |
| `POST` | `/v1/inspect/classical-pipeline` | Run all 7 classical detectors |

---

## Test Coverage

| Test file | Tests | Status |
|-----------|-------|--------|
| `test_classical_detectors.py` | 33 | ✅ Pass |
| `test_metadata_inspector.py` | 21 | ✅ Pass |
| `test_health.py` | 2 | ✅ Pass |
| `test_ready.py` | 2 | ✅ Pass |
| `test_detector_interface.py` | 5 | ✅ Pass |

**Total: 63 Python tests, all passing.**
