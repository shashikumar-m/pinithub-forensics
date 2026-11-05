/**
 * Storage service — owner-scoped storage path generation.
 *
 * Image binaries and forensic artifacts live in object storage (Supabase
 * Storage), NOT in the database. This service generates safe, owner-scoped
 * paths and validates MIME types.
 *
 * Actual file upload/download to Supabase Storage is handled at the
 * infrastructure boundary. Phase 0 provides path generation, MIME
 * validation, and filename sanitization.
 */
import crypto from 'node:crypto';

/** Allowed image MIME types for uploads. */
export const ALLOWED_IMAGE_MIMES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/tiff',
  'image/bmp',
] as const;

export type AllowedImageMime = (typeof ALLOWED_IMAGE_MIMES)[number];

/** Magic-number signatures for file-type validation (not extension-based). */
export const IMAGE_SIGNATURES: Record<string, Buffer[]> = {
  'image/jpeg': [Buffer.from([0xff, 0xd8, 0xff])],
  'image/png': [Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])],
  'image/webp': [Buffer.from('RIFF', 'ascii'), Buffer.from('WEBP', 'ascii')],
  'image/tiff': [Buffer.from([0x49, 0x49, 0x2a, 0x00]), Buffer.from([0x4d, 0x4d, 0x00, 0x2a])],
  'image/bmp': [Buffer.from([0x42, 0x4d])],
};

/**
 * Detect the real file type from the file's magic-number header.
 * Never trust the filename extension alone.
 * Returns the MIME type or null if no signature matches.
 */
export function detectMimeType(header: Buffer): string | null {
  for (const [mime, signatures] of Object.entries(IMAGE_SIGNATURES)) {
    // For multi-signature types (like webp/tiff), check all parts
    if (mime === 'image/webp') {
      if (header.length >= 12 && header.subarray(0, 4).equals(signatures[0]) && header.subarray(8, 12).equals(signatures[1])) {
        return mime;
      }
      continue;
    }
    for (const sig of signatures) {
      if (header.length >= sig.length && header.subarray(0, sig.length).equals(sig)) {
        return mime;
      }
    }
  }
  return null;
}

/**
 * Validates that a declared MIME type is in the allowed set.
 */
export function isAllowedImageMime(mime: string): mime is AllowedImageMime {
  return (ALLOWED_IMAGE_MIMES as readonly string[]).includes(mime);
}

/**
 * Sanitizes a filename to prevent path traversal and unsafe characters.
 * Returns a safe base name (no directory components).
 */
export function sanitizeFilename(filename: string): string {
  // Strip directory components
  const base = filename.split(/[/\\]/).pop() ?? filename;
  // Replace unsafe characters
  const safe = base.replace(/[^a-zA-Z0-9._-]/g, '_');
  // Limit length
  return safe.slice(0, 255) || 'upload';
}

/**
 * Generates an owner-scoped storage path for an uploaded image.
 * Format: {ownerId}/{imageId}/{sanitizedFilename}
 */
export function generateStoragePath(
  ownerId: string,
  imageId: string,
  filename: string,
): string {
  const safeName = sanitizeFilename(filename);
  return `${ownerId}/${imageId}/${safeName}`;
}

/**
 * Computes SHA-256 hash of a buffer.
 */
export function computeSha256(buffer: Buffer): string {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}
