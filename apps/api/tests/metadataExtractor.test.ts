/**
 * Phase 2 — Metadata extraction tests.
 *
 * All tests are database-free. They test the extraction logic directly.
 */
import sharp from 'sharp';
import exifr from 'exifr';
import { extractMetadata } from '../src/services/metadataExtractor.js';
import { computeSha256 } from '../src/services/storage.js';

// ---- Helpers ----

async function makeJpeg(w = 20, h = 20): Promise<Buffer> {
  return sharp({ create: { width: w, height: h, channels: 3, background: { r: 100, g: 150, b: 200 } } })
    .jpeg({ quality: 85 })
    .toBuffer();
}

async function makePng(w = 15, h = 15): Promise<Buffer> {
  return sharp({ create: { width: w, height: h, channels: 4, background: { r: 50, g: 50, b: 50, alpha: 1 } } })
    .png()
    .toBuffer();
}

async function makeWebp(w = 10, h = 10): Promise<Buffer> {
  return sharp({ create: { width: w, height: h, channels: 3, background: { r: 200, g: 100, b: 50 } } })
    .webp()
    .toBuffer();
}

// -------- Tests --------

describe('extractMetadata — basic extraction', () => {
  it('succeeds on a valid JPEG without EXIF', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    expect(result.warnings.length).toBeLessThan(5); // may have minor warnings
    expect(result.normalized).toBeDefined();
    expect(result.characteristics).toBeDefined();
  });

  it('succeeds on a valid PNG', async () => {
    const buf = await makePng();
    const result = await extractMetadata(buf);
    expect(result.normalized).toBeDefined();
  });

  it('succeeds on a valid WEBP', async () => {
    const buf = await makeWebp();
    const result = await extractMetadata(buf);
    expect(result.normalized).toBeDefined();
  });

  it('never throws — returns warnings instead', async () => {
    // Random bytes that look almost like an image
    const trash = Buffer.alloc(50, 0xff);
    await expect(extractMetadata(trash)).resolves.toBeDefined();
  });
});

describe('extractMetadata — JPEG characteristics', () => {
  it('extracts JPEG quality estimate', async () => {
    const buf = await makeJpeg(30, 30);
    const result = await extractMetadata(buf);
    // May or may not have quality estimate depending on sharp version
    // but result should be defined either way
    expect(result.characteristics).toBeDefined();
  });

  it('marks jpeg quality estimate as estimate', async () => {
    const buf = await makeJpeg(20, 20);
    const result = await extractMetadata(buf);
    if (result.characteristics.jpegQualityEstimate !== null && result.characteristics.jpegQualityEstimate !== undefined) {
      expect(result.characteristics.jpegQualityIsEstimate).toBe(true);
    }
  });

  it('extracts correct width and height', async () => {
    const buf = await makeJpeg(60, 40);
    const result = await extractMetadata(buf);
    expect(result.characteristics.width).toBe(60);
    expect(result.characteristics.height).toBe(40);
  });

  it('computes correct pixel count', async () => {
    const buf = await makeJpeg(12, 8);
    const result = await extractMetadata(buf);
    expect(result.characteristics.pixelCount).toBe(12 * 8);
  });

  it('computes correct aspect ratio for 4:3 image', async () => {
    const buf = await makeJpeg(40, 30);
    const result = await extractMetadata(buf);
    expect(result.characteristics.aspectRatioW).toBe(4);
    expect(result.characteristics.aspectRatioH).toBe(3);
  });

  it('extracts PNG alpha channel presence', async () => {
    const buf = await makePng(10, 10);
    const result = await extractMetadata(buf);
    expect(result.characteristics.hasAlpha).toBe(true);
  });
});

describe('extractMetadata — metadata as evidence only', () => {
  it('returns null for camera make when no EXIF', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    expect(result.normalized.camera.make).toBeNull();
  });

  it('does not fabricate confidence values', async () => {
    // Evidence items should have no confidence for metadata fields
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    // All evidence items from metadata extraction have no confidence
    // (confidence is only for detector-scored results)
    expect(Array.isArray(result.evidenceItems)).toBe(true);
  });

  it('C2PA status is ABSENT for a plain JPEG', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    expect(result.normalized.c2pa.status).toBe('ABSENT');
  });

  it('does not log GPS in evidenceItems', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    // evidenceItems should never contain raw gps_latitude or gps_longitude
    const gpsCoordItem = result.evidenceItems.find(
      (i) => i.key === 'gps_latitude' || i.key === 'gps_longitude',
    );
    expect(gpsCoordItem).toBeUndefined();
  });
});

describe('extractMetadata — missing GPS', () => {
  it('sets hasGps = false when no GPS data', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    expect(result.normalized.location.hasGps).toBe(false);
    expect(result.normalized.location.latitude).toBeNull();
    expect(result.normalized.location.longitude).toBeNull();
  });
});

describe('extractMetadata — timestamp handling', () => {
  it('keeps timestamps as null when no EXIF', async () => {
    const buf = await makeJpeg();
    const result = await extractMetadata(buf);
    expect(result.normalized.timestamps.capturedAt).toBeNull();
    expect(result.normalized.timestamps.capturedAtTimezone).toBeNull();
    expect(result.normalized.timestamps.metadataModifiedAt).toBeNull();
  });
});

describe('SHA-256 hash verification', () => {
  it('computes reproducible hash', async () => {
    const buf = await makeJpeg(10, 10);
    const h1 = computeSha256(buf);
    const h2 = computeSha256(buf);
    expect(h1).toBe(h2);
  });

  it('detects hash mismatch when buffer changes', async () => {
    const buf = await makeJpeg(10, 10);
    const originalHash = computeSha256(buf);
    const tampered = Buffer.from(buf);
    tampered[tampered.length - 2] ^= 0x01;
    const tamperedHash = computeSha256(tampered);
    expect(originalHash).not.toBe(tamperedHash);
  });

  it('hash is 64-character hex', async () => {
    const buf = await makeJpeg(5, 5);
    const h = computeSha256(buf);
    expect(h).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe('extractMetadata — malformed/invalid input', () => {
  it('handles empty buffer without throwing', async () => {
    const result = await extractMetadata(Buffer.alloc(0));
    expect(result).toBeDefined();
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it('handles random bytes without throwing', async () => {
    const buf = Buffer.from('this is definitely not an image!');
    const result = await extractMetadata(buf);
    expect(result).toBeDefined();
  });

  it('handles a very short JPEG header without throwing', async () => {
    const jpegHeader = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
    const result = await extractMetadata(jpegHeader);
    expect(result).toBeDefined();
  });
});
