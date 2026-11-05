/**
 * Tests for image information extraction.
 * Validates that sharp correctly reads dimensions, format, pixel count.
 * All tests are database-free.
 */
import sharp from 'sharp';
import { extractImageInfo, mimeMatchesFormat, formatToMime } from '../src/services/imageInfo.js';
import { computeSha256 } from '../src/services/storage.js';

// ---- Helpers to create minimal valid images ----

async function makeJpeg(width = 10, height = 10): Promise<Buffer> {
  return sharp({ create: { width, height, channels: 3, background: { r: 100, g: 100, b: 100 } } })
    .jpeg({ quality: 80 })
    .toBuffer();
}

async function makePng(width = 8, height = 8): Promise<Buffer> {
  return sharp({ create: { width, height, channels: 4, background: { r: 50, g: 50, b: 50, alpha: 1 } } })
    .png()
    .toBuffer();
}

async function makeWebp(width = 6, height = 6): Promise<Buffer> {
  return sharp({ create: { width, height, channels: 3, background: { r: 200, g: 100, b: 50 } } })
    .webp()
    .toBuffer();
}

// ---- Tests ----

describe('extractImageInfo', () => {
  it('correctly reads JPEG dimensions and format', async () => {
    const buf = await makeJpeg(20, 30);
    const info = await extractImageInfo(buf);
    expect(info.format).toBe('jpeg');
    expect(info.width).toBe(20);
    expect(info.height).toBe(30);
    expect(info.decodable).toBe(true);
  });

  it('correctly reads PNG dimensions and format', async () => {
    const buf = await makePng(15, 25);
    const info = await extractImageInfo(buf);
    expect(info.format).toBe('png');
    expect(info.width).toBe(15);
    expect(info.height).toBe(25);
    expect(info.decodable).toBe(true);
  });

  it('correctly reads WEBP dimensions and format', async () => {
    const buf = await makeWebp(12, 8);
    const info = await extractImageInfo(buf);
    expect(info.format).toBe('webp');
    expect(info.width).toBe(12);
    expect(info.height).toBe(8);
    expect(info.decodable).toBe(true);
  });

  it('computes correct pixel count (width × height)', async () => {
    const buf = await makeJpeg(7, 13);
    const info = await extractImageInfo(buf);
    expect(info.pixelCount).toBe(7 * 13);
  });

  it('throws IMAGE_DECODE_FAILED for random bytes', async () => {
    const buf = Buffer.from('this is not an image at all abcdefghijklmnop');
    await expect(extractImageInfo(buf)).rejects.toThrow('IMAGE_DECODE_FAILED');
  });

  it('throws IMAGE_DECODE_FAILED for empty buffer', async () => {
    await expect(extractImageInfo(Buffer.alloc(0))).rejects.toThrow('IMAGE_DECODE_FAILED');
  });

  it('throws IMAGE_DECODE_FAILED for truncated JPEG', async () => {
    const full = await makeJpeg();
    const truncated = full.subarray(0, 10);
    await expect(extractImageInfo(truncated)).rejects.toThrow('IMAGE_DECODE_FAILED');
  });
});

describe('mimeMatchesFormat', () => {
  it('returns true for image/jpeg + jpeg', () => {
    expect(mimeMatchesFormat('image/jpeg', 'jpeg')).toBe(true);
  });

  it('returns true for image/png + png', () => {
    expect(mimeMatchesFormat('image/png', 'png')).toBe(true);
  });

  it('returns true for image/webp + webp', () => {
    expect(mimeMatchesFormat('image/webp', 'webp')).toBe(true);
  });

  it('returns false for mismatched mime/format', () => {
    expect(mimeMatchesFormat('image/jpeg', 'png')).toBe(false);
    expect(mimeMatchesFormat('image/png', 'jpeg')).toBe(false);
  });
});

describe('formatToMime', () => {
  it('maps jpeg -> image/jpeg', () => expect(formatToMime('jpeg')).toBe('image/jpeg'));
  it('maps png -> image/png', () => expect(formatToMime('png')).toBe('image/png'));
  it('maps webp -> image/webp', () => expect(formatToMime('webp')).toBe('image/webp'));
  it('returns null for unknown', () => expect(formatToMime('xyz')).toBeNull());
});

describe('SHA-256 of original bytes', () => {
  it('is reproducible — same input always produces same hash', async () => {
    const buf = await makeJpeg(5, 5);
    expect(computeSha256(buf)).toBe(computeSha256(buf));
  });

  it('changes when even one byte changes', async () => {
    const buf = await makeJpeg(5, 5);
    const modified = Buffer.from(buf);
    modified[modified.length - 2] ^= 0xff;
    expect(computeSha256(buf)).not.toBe(computeSha256(modified));
  });

  it('produces 64-char lowercase hex', async () => {
    const buf = await makeJpeg(4, 4);
    const hash = computeSha256(buf);
    expect(hash).toHaveLength(64);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
  });
});
