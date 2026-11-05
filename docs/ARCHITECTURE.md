# Architecture

## Overview

PINITHUB ForeNSICS is a monorepo with three runtime tiers, a shared type
package, and infrastructure support. The system is designed for
asynchronous, computationally expensive image forensics.

```
┌──────────────┐     ┌──────────────┐     ┌────────────────────┐
│   Frontend   │────▶│   Node API   │────▶│  Python Forensic  │
│  (React/Vite)│     │ (Express/TS) │     │  Service (FastAPI) │
└──────────────┘     └──────┬───────┘     └─────────┬──────────┘
                            │                        │
                     ┌──────┴───────┐          ┌──────┴───────┐
                     │ PostgreSQL   │          │ Object Storage│
                     │ (metadata,   │          │ (images,      │
                     │  jobs, audit)│          │  artifacts)   │
                     └──────────────┘          └──────────────┘
```

## Service Responsibilities

### Frontend (`apps/web`)
- React + TypeScript + Vite + Tailwind CSS
- React Router for navigation
- TanStack Query for server state
- Sends images and analysis requests to the Node API
- **Never** performs image processing or stores service-role keys

### Node.js API (`apps/api`)
- Express + TypeScript + Prisma + Zod
- Request validation, authentication context, rate limiting
- Creates analysis records and queues jobs in PostgreSQL
- Manages file uploads to object storage
- **Never** performs heavy image processing — delegates to the Python service
- Centralized error handling with structured `{ error: { code, message } }` shape
- Pino structured logging with secret redaction

### Python Forensic Service (`services/forensics`)
- FastAPI + Pydantic
- Defines the detector interface contract (`BaseDetector`)
- Future workers will poll the Node API for queued jobs (SKIP LOCKED)
- Runs detector pipelines against images
- **Never** exposes the service-role key or writes to the frontend

### Shared Types (`packages/shared`)
- TypeScript type definitions shared between frontend and API
- Ensures contract consistency — no duplicated incompatible versions
- Types only, no runtime logic

## Async Analysis Flow

```
Frontend → POST /v1/uploads → Image stored in object storage
        → POST /v1/analyses → Analysis + Job created in PostgreSQL (QUEUED)
        → Python worker polls/claims job (SKIP LOCKED) → RUNNING
        → Python worker runs detector pipeline → DetectorOutputs written
        → Python worker reports job completion → Job → DONE, Analysis → DONE
        → Frontend polls GET /v1/analyses/:id → receives results
```

## Status: Phase 0 — IMPLEMENTED NOW

| Component | Status |
|-----------|--------|
| Monorepo structure | ✅ Implemented |
| Frontend foundation + routes | ✅ Implemented |
| Node API + endpoints + validation | ✅ Implemented |
| Python service + health/ready | ✅ Implemented |
| Shared types | ✅ Implemented |
| Prisma schema (12 models) | ✅ Implemented |
| Docker compose | ✅ Implemented |
| Async job architecture (schema + claim logic) | ✅ Schema ready |
| Forensic detectors | ❌ Not implemented (Phase 2+) |
| Worker polling loop | ❌ Not implemented (Phase 2+) |
| Evidence fusion | ❌ Not implemented (Phase 6) |
| Report generation | ❌ Not implemented (Phase 7) |
| Vault sealing | ❌ Not implemented (Phase 8) |
