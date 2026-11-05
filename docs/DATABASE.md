# Database

## Technology

- **PostgreSQL** (via Supabase or local Docker)
- **Prisma ORM** for schema management and queries

## Design Principles

1. **Image binaries are NEVER stored in the database** — only metadata,
   identifiers, hashes, references, and analysis state.
2. **UUIDs** for all primary keys (non-sequential, hard to guess).
3. **Owner-scoped access** — every resource carries an `ownerId`.
4. **Audit trail** — every mutation records an `AuditEvent`.
5. **Async job lifecycle** — analyses create jobs with `QUEUED → RUNNING → DONE/FAILED`.

## Schema Models (12 tables)

### `users`
- `id` (UUID PK), `email`, `name`, `role`, timestamps

### `images`
- `id` (UUID PK), `ownerId` (FK→users), `role`, `status`
- `originalFilename`, `mimeType`, `sizeBytes`, `sha256` (unique)
- `storagePath` (owner-scoped path in object storage, NOT binary data)
- `width`, `height`, `datasetItemId`, timestamps
- Indexes: `ownerId`, `sha256`, `role`

### `image_metadata`
- 1:1 with `images` — parsed EXIF/metadata
- `exif` (JSON), `software`, `capturedAt`, `colorSpace`, `hasGps`
- GPS data is NOT stored — only a boolean `hasGps`

### `analyses`
- `id` (UUID PK), `ownerId`, `imageId`, `referenceImageId`
- `type` (analysis type enum), `status`
- `verdict`, `confidence` — only populated when results are real (not yet)
- `error`, timestamps
- Indexes: `ownerId`, `imageId`, `status`, `type`

### `analysis_jobs`
- `id` (UUID PK), `analysisId` (FK→analyses)
- `status` (QUEUED/RUNNING/DONE/FAILED), `pipeline`, `attempt`, `maxAttempts`
- `claimedBy`, `startedAt`, `completedAt`, `error` (JSON)
- Indexes: `status`, `analysisId`
- **SKIP LOCKED** support via raw query for concurrent job claiming

### `detector_outputs`
- `id` (UUID PK), `analysisId`, `detector`, `version`, `category`
- `status` (NOT_RUN/RUNNING/DONE/FAILED/NOT_IMPLEMENTED)
- `score`, `confidence`, `mapStoragePath`, `details` (JSON)
- `executionTimeMs`, `error`, timestamps

### `regions`
- `id` (UUID PK), `analysisId`, `detectorOutputId`
- `type`, `bbox` (x/y/width/height), `score`
- `maskStoragePath` (artifact reference), `description`

### `model_versions`
- `id` (UUID PK), `name`, `version` (unique pair), `type`, `status`
- `category`, `artifactStoragePath`, `sha256`, `description`

### `datasets`
- `id` (UUID PK), `name`, `description`, timestamps

### `dataset_items`
- `id` (UUID PK), `datasetId`, `imageId` (FK→images, optional)
- `label`, `groundTruth` (JSON)

### `evaluation_runs`
- `id` (UUID PK), `datasetId`, `modelVersionId`, `detector`, `status`
- `startedAt`, `completedAt`

### `evaluation_metrics`
- `id` (UUID PK), `evaluationRunId`, `metricName`, `metricValue`

### `audit_events`
- `id` (UUID PK), `eventType`, `actorId`, `resourceId`, `resourceType`
- `payload` (JSON), `previousHash`, `hash`
- **Tamper-evident chain** — hash chaining is a future-phase enhancement

## Setup

```bash
# From the project root
cd apps/api
npx prisma generate
npx prisma db push   # or: npx prisma migrate dev
```

## Status

| Feature | Status |
|---------|--------|
| Prisma schema | ✅ Implemented |
| All 12 models defined | ✅ Implemented |
| Relationships + indexes | ✅ Implemented |
| SKIP LOCKED job claim query | ✅ Implemented |
| Seed data | ❌ Not implemented |
| Hash-chained audit | ❌ Planned (Phase 8) |
| Evaluation metrics population | ❌ Planned (Phase 9) |
