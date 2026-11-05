/**
 * Image information extraction — validates that a buffer is a decodable
 * image and extracts basic metadata (dimensions, format, color mode).
 *
 * Uses sharp in READ-ONLY mode only. The original file is NEVER modified.
 * This is not forensic processing — it's basic file metadata extraction.
 */
import sharp from 'sharp';

export interface ImageInfo {
  /** Format detected by sharp, e.g. "jpeg", "png", "webp" */
  format: string;
  width: number;
  height: number;
  /** width × height */
  pixelCount: number;
  /** Number of channels */
  channels: number;
  /** Color space, e.g. "srgb", "rgb", "rgba" */
  colorMode: string;
  /** Whether the image decoded successfully */
  decodable: boolean;
}

/**
 * Validates that a buffer is a decodable image and extracts basic info.
 * Throws if the image cannot be decoded.
 */
export async function extractImageInfo(buffer: Buffer): Promise<ImageInfo> {
  let metadata: sharp.Metadata;
  try {
    metadata = await sharp(buffer).metadata();
  } catch (err) {
    throw new Error('IMAGE_DECODE_FAILED');
  }

  if (!metadata.width || !metadata.height) {
    throw new Error('IMAGE_DECODE_FAILED');
  }

  const channels = metadata.channels ?? 0;
  const space = metadata.space ?? 'unknown';

  return {
    format: metadata.format ?? 'unknown',
    width: metadata.width,
    height: metadata.height,
    pixelCount: metadata.width * metadata.height,
    channels,
    colorMode: space,
    decodable: true,
  };
}

/**
 * Maps a sharp-detected format to a MIME type.
 */
export function formatToMime(format: string): string | null {
  const map: Record<string, string> = {
    jpeg: 'image/jpeg',
    jpg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    tiff: 'image/tiff',
    bmp: 'image/bmp',
  };
  return map[format] ?? null;
}

/**
 * Verifies that the detected MIME type (from magic number) matches
 * the actual image format (from sharp). Returns true if they agree.
 */
export function mimeMatchesFormat(mime: string, format: string): boolean {
  const expectedMime = formatToMime(format);
  return expectedMime === mime;
}
