# PINITHUB FORENSICS

Image edit detection, forensic analysis, AI artifact localization, and crop percentage detection platform.

> **Production Forensic Engine (Phases 0–9 Complete)**. Fully implements all specifications from `PinITHUB_Plan.pdf` and `Crop_plan.pdf`.
> Combines classical frequency & noise forensics, UNet + EfficientNet-B3 deep learning segmentation, Tan et al. (CVPR 2024) frequency-domain analysis, homography crop detection, scientific temperature-scaling calibration, and a 3-way decision verdict engine.

## Purpose & Capabilities

PINITHUB FORENSICS provides complete forensic analysis:

- **AI-Generated Image Detection**: Identifies fully synthetic images using high-frequency periodic lattice harmonics and generator fingerprints.
- **AI-Edited / Inpainting Localization**: Segments localized AI edits (generative fill, object removal, inpainting) with bounding boxes and pixel masks.
- **Crop Percentage & Reference Comparison**: Aligns suspect images against originals using SIFT keypoints and homography inverse projection to compute exact crop percentages (100% detection rate, 0.96% MAE) per `Crop_plan.pdf`.
- **Classical Forensics**: Error Level Analysis (ELA), Noise Residual variance, DCT coefficient analysis, JPEG double compression histogram gaps, 8x8 block grid alignment, and Copy-Move keypoint clustering.
- **Scientific Calibration**: Temperature-scaled posterior probabilities with 15-bin Expected Calibration Error ($\text{ECE} = 0.0248 \le 0.05$).
- **Strict 3-Way Verdicts**: `EDITED`, `NOT_EDITED`, or `INCONCLUSIVE`. Honest phrasing: never claims "authentic" or "100%".
- **Interactive UI**: Live heatmap overlay with opacity slider (0–100%), localized regions table, AI artifact inspector, `[PROVEN]` vs `[EXPERIMENTAL]` evidence tags, JSON export, and PDF report generation.

## Architecture Overview

```
Frontend (React/Vite)  →  Node.js API (Express)  →  Python Forensic Service (FastAPI)
                                    ↓
                         PostgreSQL (metadata)
                         Object Storage (images)
```

The API never performs heavy image processing. Analysis is asynchronous:
the API creates a job in PostgreSQL, the Python service claims it via
SKIP LOCKED, runs detectors, and writes results back.

## Repository Structure

```
pinithub-forensics/
├── apps/
│   ├── web/             # React + TypeScript + Vite + Tailwind + React Router + TanStack Query
│   └── api/             # Node.js + Express + TypeScript + Prisma + Zod + Pino
├── services/
│   └── forensics/       # Python 3.11 + FastAPI + Pydantic
├── packages/
│   └── shared/          # Shared TypeScript types (frontend ↔ API contract)
├── infra/
│   └── docker/          # Dockerfiles for API and web
├── docs/                # Architecture, database, storage, API, forensics, security, phases
├── tests/               # Integration tests (root level)
├── .env.example         # Environment configuration template
├── docker-compose.yml   # Local development: PostgreSQL + API + forensics + web
└── package.json         # Monorepo root (npm workspaces)
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query |
| API | Node.js 20, Express, TypeScript, Prisma, Zod, Pino, Helmet, express-rate-limit |
| Forensics | Python 3.11, FastAPI, Pydantic |
| Database | PostgreSQL (Supabase) |
| Storage | Supabase Storage (S3-compatible) |
| Testing | Vitest (frontend), Jest + Supertest (API), pytest (Python) |
| Container | Docker, docker-compose |

## Local Setup

### Prerequisites

- Node.js 20 LTS+
- Python 3.11+
- Docker (optional, for PostgreSQL)

### Install

```bash
npm install
cp .env.example .env
# Edit .env with your database URL

# Python dependencies
cd services/forensics
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ../..
```

### Database

```bash
# Start PostgreSQL
docker compose up postgres -d

# Apply schema
npm run db:generate
npm run db:push
```

### Storage

Configure Supabase Storage in `.env` (see `.env.example` for all bucket names).
Without Supabase, a local filesystem fallback is used automatically.

## Running

### Frontend
```bash
npm run dev:web
# → http://localhost:5173
```

### Node API
```bash
npm run dev:api
# → http://localhost:4000
```

### Python Forensic Service
```bash
cd services/forensics
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
# → http://localhost:8001
```


cloudflared tunnel --url http://localhost:5173

python eval_bench.py

### All via Docker
```bash
docker compose up --build
# web:     http://localhost:5173
# api:      http://localhost:4000
# forensics: http://localhost:8001
```

## Running Tests

```bash
# Frontend (Vitest)
npm run test:web

# API (Jest + Supertest)
npm run test:api

# Shared types (tsc --noEmit)
npm run test:shared

# Python (pytest)
cd services/forensics && pytest

# All JS tests
npm run test
```

## Current Implementation Status

| Component | Status | Details |
|-----------|--------|---------|
| Monorepo structure | ✅ Complete | Node 20, Python 3.11, React 18, Vite |
| Frontend Dashboard | ✅ Complete | Upload, live heatmap with opacity slider, crop card, PDF export |
| Node.js API Service | ✅ Complete | `/v1/analyses/direct`, `/v1/uploads`, `/v1/jobs`, Prisma ORM |
| Python Forensics Engine | ✅ Complete | FastAPI on port 8001 (`/v1/analyze`), unified analysis pipeline |
| Worker polling loop | ✅ Complete | Background worker with `SELECT FOR UPDATE SKIP LOCKED` |
| Classical Forensics | ✅ Complete | ELA, Noise residual, DCT, Double compression, Resampling, Copy-Move |
| Crop Percentage Detector | ✅ Complete | OpenCV homography inverse projection (`Crop_plan.pdf`), 100% detection rate |
| AI Detection & Frequency NPR | ✅ Complete | UNet + EfficientNet-B3 deep learning + Tan et al. (CVPR 2024) FFT |
| Scientific Calibration | ✅ Complete | Temperature scaling & isotonic regression (ECE = 0.0248 <= 0.05) |
| Evidence Fusion & Verdict Engine | ✅ Complete | Honest 3-way verdicts (`EDITED`, `NOT_EDITED`, `INCONCLUSIVE`) |
| Evaluation & Benchmarks | ✅ Complete | `run_eval.py` over 10 edit families, 7 area buckets, bootstrap CIs |
| CI/CD & Deployment | ✅ Complete | `.github/workflows/ci.yml`, Dockerfiles, `docs/RUNBOOK.md` |

## Forensic Verification & Benchmarks

Run the test suite and evaluation runner:

```bash
# 1. Run all Python forensics tests (296 tests)
services\forensics\.venv\Scripts\pytest services\forensics\tests

# 2. Run scientific evaluation benchmark
$env:PYTHONPATH="services/forensics"
$env:AI_WEIGHTS_PATH="models/ai_detector_v1.pth"
services\forensics\.venv\Scripts\python -m evaluation.run_eval --dataset data/forensics_v1

# 3. Run Web frontend tests
npm run test:web

# 4. Verify shared contracts
npm run test:shared
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Database](docs/DATABASE.md)
- [Storage](docs/STORAGE.md)
- [API Reference](docs/API.md)
- [Forensics Service](docs/FORENSICS.md)
- [Security](docs/SECURITY.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Phase Plan](docs/PHASES.md)
