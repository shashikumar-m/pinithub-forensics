# Security

## Phase 0 Security Measures

The following security measures are implemented in the foundation:

### HTTP Security
- **Helmet** — sets secure HTTP headers (CSP, X-Frame-Options, etc.)
- **CORS** — configurable allowed origins, no credentials by default
- **Rate limiting** — `express-rate-limit` with configurable window/max
- **Compression** — response compression enabled

### Input Validation
- **Zod schemas** validate all request bodies, queries, and params
- **File size limits** — enforced via multer (`MAX_UPLOAD_MB`)
- **Magic-number validation** — file type detected from bytes, not extension
- **Filename sanitization** — directory traversal prevented
- **UUID validation** — all ID params validated as UUIDs

### Secret Management
- **No secrets committed** — `.env` is gitignored, only `.env.example` is tracked
- **Service-role key never exposed to frontend** — only used server-side in the API
- **Environment validation at startup** — server fails fast if required vars are missing
- **Pino log redaction** — passwords, API keys, service-role keys, image buffers, and
  GPS data are redacted from logs

### Storage Security
- **Private buckets** — images and artifacts are not publicly accessible
- **Owner-scoped paths** — `ownerId/imageId/filename` prevents cross-user access
- **No binary data in database** — only metadata, hashes, and references

### Resource Access
- **Owner-scoped queries** — every query filters by `ownerId`
- **Analysis delete** — verified owner before deletion
- **Image upload** — verified owner before processing

### Error Handling
- **Structured error responses** — `{ error: { code, message } }`
- **No stack traces in production** — internal errors return generic message
- **No secret leakage** — error messages never include credentials

## Planned Enhancements (Future Phases)

| Measure | Phase |
|---------|-------|
| Full authentication (JWT/session) | Phase 1 |
| File-signature validation hardening | Phase 9 |
| Decompression-bomb protection | Phase 9 |
| Image dimension limits | Phase 9 |
| Signed URL expiration enforcement | Phase 9 |
| Audit hash chaining (tamper-evidence) | Phase 8 |
| RLS policies in Supabase | Phase 9 |
| API key rotation | Phase 9 |

## What Is NOT Implemented Yet

- No user authentication or JWT issuance
- No session management
- Owner identity comes from an `X-Owner-Id` header (dev) or defaults to a
  development user. This is explicitly a Phase 0 placeholder.
- No file-signature validation beyond basic magic-number checks
- No decompression-bomb detection
- No signed URL generation
- No audit hash chaining

These are documented limitations, not oversights. Each is tracked in
the phase plan.
