# Storage

## Technology

- **Supabase Storage** (S3-compatible object storage)
- **Local filesystem fallback** for development without Supabase

## Private Buckets

| Bucket | Purpose |
|--------|---------|
| `originals` | Uploaded original images (protected originals) |
| `artifacts` | Forensic artifacts (heatmaps, masks, reports) |
| `datasets` | Dataset images for evaluation |
| `models` | Model checkpoints / detector weights |

All buckets are **private by default**. Files are never publicly accessible.

## Owner-Scoped Paths

Files are stored using owner-scoped paths to prevent cross-user access:

```
{ownerId}/{imageId}/{sanitizedFilename}
```

Example:
```
550e8400-e29b-41d4-a716-446655440000/660e8400-.../photo.jpg
```

## Signed URLs

The architecture supports generating signed URLs for time-limited
access to private files. This will be implemented when the frontend
needs to display stored images.

**Status:** ❌ Not implemented yet — signed URL generation is a
future-phase feature.

## Key Security Rules

1. **The Supabase service-role key is NEVER sent to the frontend.**
   Only the Node API uses it server-side.
2. **The frontend uses the anon key** (if any) with Row-Level Security.
3. **Image binaries are NOT stored in PostgreSQL** — only in object storage.
4. **Filenames are sanitized** — directory traversal is prevented.
5. **File types are validated by magic-number signature**, not extension.

## Local Development Fallback

When `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are not configured,
the storage client writes files to a local `.local-storage/` directory
(which is gitignored). This allows full local development without
Supabase.

## Configuration

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET_ORIGINALS=originals
SUPABASE_STORAGE_BUCKET_ARTIFACTS=artifacts
SUPABASE_STORAGE_BUCKET_DATASETS=datasets
SUPABASE_STORAGE_BUCKET_MODELS=models
```

## Status

| Feature | Status |
|---------|--------|
| Storage config + env vars | ✅ Implemented |
| Owner-scoped path generation | ✅ Implemented |
| Supabase upload (when configured) | ✅ Implemented |
| Local filesystem fallback | ✅ Implemented |
| Filename sanitization | ✅ Implemented |
| Magic-number MIME validation | ✅ Implemented |
| Signed URL generation | ❌ Planned |
| Decompression-bomb protection | ❌ Planned (security phase) |
