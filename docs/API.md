# API Reference

Base URL: `http://localhost:4000`

## Error Format

All errors return a consistent JSON structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

## Endpoints

### Health & Readiness

#### `GET /v1/health`
Lightweight liveness check. No dependency calls.

**Response 200:**
```json
{
  "status": "ok",
  "service": "pinithub-api",
  "version": "0.1.0",
  "timestamp": "2026-11-01T12:00:00.000Z"
}
```

#### `GET /v1/ready`
Readiness check — probes database, storage, and forensic service.

**Response 200 or 503:**
```json
{
  "status": "ok",
  "service": "pinithub-api",
  "checks": {
    "database": "ok",
    "storage": "ok",
    "forensics": "ok"
  },
  "timestamp": "2026-11-01T12:00:00.000Z"
}
```

---

### Uploads

#### `POST /v1/uploads`
Upload an image to object storage.

**Request:** `multipart/form-data`
- `file` — image file (JPEG, PNG, WebP, TIFF, BMP)
- `role` — `ORIGINAL` | `SUSPECT` | `DATASET` (default: `SUSPECT`)
- `datasetItemId` — optional UUID

**Headers:**
- `X-Owner-Id` — UUID (optional in dev; defaults to dev user)

**Response 201:**
```json
{
  "image": {
    "id": "uuid",
    "ownerId": "uuid",
    "role": "SUSPECT",
    "status": "STORED",
    "originalFilename": "photo.jpg",
    "mimeType": "image/jpeg",
    "sizeBytes": 102400,
    "sha256": "abc123...",
    "storagePath": "owner-id/image-id/photo.jpg",
    "width": null,
    "height": null,
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

**Security:**
- File size limited by `MAX_UPLOAD_MB` (default 25MB)
- MIME type validated by magic-number signature, not extension
- Filename sanitized (directory traversal prevented)
- Duplicate detection by SHA-256 hash

---

### Analyses

#### `POST /v1/analyses`
Create a new forensic analysis and queue a job.

**Request:**
```json
{
  "imageId": "uuid",
  "referenceImageId": "uuid (optional)",
  "type": "METADATA_EXIF"
}
```

**Response 201:**
```json
{
  "analysis": {
    "id": "uuid",
    "ownerId": "uuid",
    "imageId": "uuid",
    "type": "METADATA_EXIF",
    "status": "QUEUED",
    "verdict": null,
    "confidence": null,
    "error": null,
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

**Note:** `verdict` and `confidence` are `null` because forensic
detectors are not yet implemented. The analysis is queued but no
fake results are returned.

#### `GET /v1/analyses`
List analyses (paginated, owner-scoped).

**Query params:** `page`, `pageSize`, `status`, `type`

**Response 200:**
```json
{
  "items": [...],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

#### `GET /v1/analyses/:id`
Get a single analysis with jobs, detector outputs, and regions.

**Response 200:**
```json
{
  "analysis": {
    "id": "uuid",
    "status": "QUEUED",
    "jobs": [...],
    "detectorOutputs": [],
    "regions": []
  }
}
```

#### `DELETE /v1/analyses/:id`
Delete an analysis (owner-scoped).

**Response:** 204 No Content

---

### Models

#### `GET /v1/models`
List registered model/detector versions.

#### `POST /v1/models`
Register a new model version.

**Request:**
```json
{
  "name": "ai-generated-resnet50",
  "version": "1.0.0",
  "type": "CLASSIFIER",
  "category": "AI_GENERATED",
  "status": "DRAFT",
  "description": "..."
}
```

---

## Status

| Feature | Status |
|---------|--------|
| Health/Ready endpoints | ✅ Implemented |
| Upload endpoint (with validation) | ✅ Implemented |
| Analysis CRUD + job queueing | ✅ Implemented |
| Model version registry | ✅ Implemented |
| Centralized error handling | ✅ Implemented |
| Request validation (Zod) | ✅ Implemented |
| Rate limiting | ✅ Implemented |
| Forensic result endpoints | ❌ Not implemented (detectors not ready) |
| Report endpoints | ❌ Planned (Phase 7) |
| Vault seal endpoints | ❌ Planned (Phase 8) |
