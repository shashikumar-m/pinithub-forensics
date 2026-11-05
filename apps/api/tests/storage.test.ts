/**
 * Tests for storage helpers — MIME detection, filename sanitization,
 * SHA-256 hashing, and owner-scoped path generation.
 * These do NOT require a database connection.
 */
import {
  detectMimeType,
  isAllowedImageMime,
  sanitizeFilename,
  generateStoragePath,
  computeSha256,
} from '../src/services/storage.js';

describe('detectMimeType', () => {
  it('detects JPEG from magic bytes', () => {
    const jpegHeader = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
    expect(detectMimeType(jpegHeader)).toBe('image/jpeg');
  });

  it('detects PNG from magic bytes', () => {
    const pngHeader = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00]);
    expect(detectMimeType(pngHeader)).toBe('image/png');
  });

  it('returns null for non-image data', () => {
    const textHeader = Buffer.from('Hello, World!');
    expect(detectMimeType(textHeader)).toBeNull();
  });
});

describe('isAllowedImageMime', () => {
  it('accepts image/jpeg', () => {
    expect(isAllowedImageMime('image/jpeg')).toBe(true);
  });

  it('accepts image/png', () => {
    expect(isAllowedImageMime('image/png')).toBe(true);
  });

  it('rejects application/pdf', () => {
    expect(isAllowedImageMime('application/pdf')).toBe(false);
  });

  it('rejects image/gif', () => {
    expect(isAllowedImageMime('image/gif')).toBe(false);
  });
});

describe('sanitizeFilename', () => {
  it('strips directory traversal components', () => {
    const result = sanitizeFilename('../../etc/passwd');
    expect(result).toBe('passwd');
  });

  it('strips backslash components on Windows', () => {
    const result = sanitizeFilename('..\\windows\\system32');
    expect(result).toBe('system32');
  });

  it('replaces unsafe characters', () => {
    const result = sanitizeFilename('my file (1).jpg');
    expect(result).not.toContain(' ');
    expect(result).not.toContain('(');
    expect(result).not.toContain(')');
  });
});

describe('generateStoragePath', () => {
  it('creates owner-scoped path', () => {
    const ownerId = '550e8400-e29b-41d4-a716-446655440000';
    const imageId = '660e8400-e29b-41d4-a716-446655440001';
    const result = generateStoragePath(ownerId, imageId, 'photo.jpg');
    expect(result).toBe(`${ownerId}/${imageId}/photo.jpg`);
  });
});

describe('computeSha256', () => {
  it('produces consistent hash for same input', () => {
    const buf = Buffer.from('test data');
    const hash1 = computeSha256(buf);
    const hash2 = computeSha256(buf);
    expect(hash1).toBe(hash2);
  });

  it('produces different hash for different input', () => {
    const hash1 = computeSha256(Buffer.from('data1'));
    const hash2 = computeSha256(Buffer.from('data2'));
    expect(hash1).not.toBe(hash2);
  });

  it('produces 64-character hex string', () => {
    const hash = computeSha256(Buffer.from('test'));
    expect(hash).toHaveLength(64);
    expect(hash).toMatch(/^[a-f0-9]+$/);
  });
});
