# Phase Plan

This document describes the intended progression of the PINITHUB
FORENSICS platform. Phase 0 is complete. Later phases are planned but
**not yet implemented**.

---

## Phase 0 — Foundation ✅ COMPLETE

**Goal:** Create the production-ready project foundation and architecture.

**Delivered:**
- Monorepo structure (apps, services, packages, infra, docs, tests)
- React frontend with routes: `/`, `/protect`, `/vault`, `/investigation`, `/history`
- Reusable components with proper empty/loading states (no fake values)
- Node.js API with health, ready, uploads, analyses, models endpoints
- Prisma schema with 12 models and proper relationships
- Python forensic service with health/ready and detector interface contract
- Shared TypeScript types package
- Docker compose for local development
- Test foundations (Vitest, Jest, pytest)
- Documentation for all systems
- Security measures (Helmet, CORS, rate limiting, validation, secret redaction)
- Async analysis architecture (job queue with SKIP LOCKED support)

**Not implemented:** Any actual forensic detection, AI models, detectors,
heatmaps, reports, or vault sealing.

---

## Phase 1 — Protect / Capture / Upload

**Goal:** Complete the image registration and protection workflow.

**Planned:**
- Full upload pipeline with signed URLs
- Camera capture workflow (one photo → same pipeline as upload)
- Consent flow integration
- Vault record creation with SHA-256 sealing
- User authentication (JWT/session)
- Owner-scoped access control enforcement

---

## Phase 2 — Metadata and Classical Forensics

**Goal:** Implement classical forensic detectors.

**Planned detectors:**
- Error Level Analysis (ELA)
- Noise residual analysis
- DCT forensic analysis
- JPEG double-compression detection
- Copy-move detection
- Image metadata and EXIF analysis
- Basic heatmap/mask generation

**Infrastructure:**
- Python worker polling loop
- Job claiming from the Node API
- DetectorOutput persistence
- Region detection for classical methods

---

## Phase 3 — Reference Comparison

**Goal:** Compare a suspect image against a protected original.

**Planned:**
- Keypoint matching (SIFT, ORB, AKAZE)
- Homography estimation
- Crop percentage detection
- Image-to-image forensic comparison
- Change detection between original and copy
- Region-level diff visualization

---

## Phase 4 — AI Detection and Segmentation

**Goal:** Detect AI-generated and AI-edited images.

**Planned:**
- AI-generated image detection (classifier)
- AI-edit / inpainting detection
- Pixel-level localization (segmentation)
- UNet / SegFormer models
- Model version registry population
- Confidence and reliability scoring

---

## Phase 5 — Travelled Copy Simulation

**Goal:** Simulate how images change as they travel across platforms.

**Planned:**
- Compression simulation (WhatsApp, Instagram, screenshots)
- Resize and crop simulation
- Rotation and brightness/contrast changes
- Filter application
- Object addition/removal simulation
- Copy-move forgery simulation
- AI editing simulation
- Text/sticker overlay simulation
- Metadata change simulation
- Dataset generation pipeline

---

## Phase 6 — Evidence Fusion and Calibration

**Goal:** Combine detector outputs into a unified verdict.

**Planned:**
- Evidence fusion across multiple detectors
- Calibration of detector scores
- Final forensic confidence computation
- Reliability weighting
- Conflict resolution between detectors

---

## Phase 7 — Investigation and Reporting

**Goal:** Generate tamper-evident forensic reports.

**Planned:**
- Forensic report generation
- Tamper-evident record creation
- Report PDF/export
- Investigation comparison UI
- Change list with evidence
- Report viewer component

---

## Phase 8 — Vault / Sealed Record

**Goal:** Complete the protected original vault.

**Planned:**
- Vault sealing with hash chains
- Tamper-evident audit trail
- Audit event hash chaining
- Sealed record verification
- Vault record management UI

---

## Phase 9 — Evaluation and Security

**Goal:** Measure detector performance and harden security.

**Planned:**
- Evaluation runs against datasets
- Evaluation metrics (precision, recall, F1, IoU, AUC)
- Test metric tracking and comparison
- File-signature validation hardening
- Decompression-bomb protection
- Signed URL expiration enforcement
- Supabase RLS policies
- API key rotation
- Security audit

---

## Phase 10 — Final UI / E2E Validation

**Goal:** End-to-end validation of the complete system.

**Planned:**
- Full UI integration with all detectors
- End-to-end test suite
- Performance validation
- User acceptance testing
- Documentation finalization
- Production readiness review
