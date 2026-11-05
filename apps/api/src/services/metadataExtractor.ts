/**
 * Metadata extraction service — Node.js side.
 *
 * Extracts EXIF, XMP, IPTC, and technical image characteristics from the
 * original buffer. This runs synchronously inside the protect-and-queue
 * pipeline so we can immediately populate the ImageMetadata record.
 *
 * IMPORTANT DESIGN PRINCIPLES:
 *   - The original buffer is NEVER modified.
 *   - Metadata is EVIDENCE, not proof. No authenticity judgements here.
 *   - GPS data is extracted but never written to logs.
 *   - Malformed/malicious metadata must not crash or execute anything.
 *   - Unknown timezone stays unknown — never silently converted to UTC.
 */
import exifr from 'exifr';
import sharp from 'sharp';
import { getLogger } from '../config/logger.js';
import type { NormalizedMetadata, C2PAStatus, ImageCharacteristicsRecord } from '@pinithub/shared';

/** Raw extraction result — one or more sections may be missing on failure. */
export interface MetadataExtractionResult {
  normalized: NormalizedMetadata;
  characteristics: Partial<Omit<ImageCharacteristicsRecord, 'id' | 'imageId' | 'createdAt'>>;
  evidenceItems: Array<{ category: string; key: string; value: unknown; valueType: string }>;
  warnings: string[];
}

/**
 * Extracts metadata from a raw image buffer.
 * Returns a best-effort result — partial failure is acceptable and documented.
 * Never throws — catches all parser errors internally.
 */
export async function extractMetadata(buffer: Buffer): Promise<MetadataExtractionResult> {
  const log = getLogger();
  const warnings: string[] = [];
  const evidenceItems: MetadataExtractionResult['evidenceItems'] = [];

  // ---- EXIF / XMP / IPTC parsing via exifr ----
  let exifData: Record<string, unknown> | null = null;
  try {
    exifData = await exifr.parse(buffer, {
      exif: true,
      gps: true,
      xmp: true,
      iptc: true,
      icc: true,
      jfif: true,
      ihdr: true,
      tiff: { multiSegment: false },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    warnings.push(`EXIF parse warning: ${msg}`);
    log.warn({ msg }, 'EXIF parsing failed — proceeding with available data');
    exifData = null;
  }

  // Ensure metadata values are not executable — treat as plain data only
  const safe = (v: unknown): unknown => {
    if (typeof v === 'function') return null;
    if (v instanceof Buffer || v instanceof Uint8Array) return '[binary]';
    return v;
  };

  // Sanitize exifData values
  if (exifData) {
    const sanitized: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(exifData)) {
      sanitized[k] = safe(v);
    }
    exifData = sanitized;
  }

  // ---- Extract normalized metadata fields ----
  const cameraMake = str(exifData?.['Make']) ?? null;
  const cameraModel = str(exifData?.['Model']) ?? null;
  const lensMake = str(exifData?.['LensMake']) ?? null;
  const lensModel = str(exifData?.['LensModel']) ?? null;
  const focalLength = num(exifData?.['FocalLength']) ?? null;
  const aperture = num(exifData?.['FNumber']) ?? num(exifData?.['ApertureValue']) ?? null;
  const shutterSpeed = shutterStr(exifData?.['ExposureTime']) ?? null;
  const iso = num(exifData?.['ISO']) ?? null;
  const orientation = num(exifData?.['Orientation']) ?? null;
  const colorSpace = str(exifData?.['ColorSpace']) ?? null;
  const software = str(exifData?.['Software']) ?? null;
  const editingSoftware = detectEditingSoftware(exifData);

  // Timestamps — kept separate, never merged
  const capturedAt = dateStr(exifData?.['DateTimeOriginal'] ?? exifData?.['CreateDate']) ?? null;
  const capturedAtTimezone = str(exifData?.['OffsetTimeOriginal'] ?? exifData?.['OffsetTime']) ?? null;
  const metadataCreatedAt = dateStr(exifData?.['CreateDate']) ?? null;
  const metadataModifiedAt = dateStr(exifData?.['ModifyDate']) ?? null;

  // GPS — extracted but NEVER logged
  const hasGps = !!(exifData?.['latitude'] ?? exifData?.['GPSLatitude']);
  const gpsLatitude = hasGps ? (num(exifData?.['latitude']) ?? null) : null;
  const gpsLongitude = hasGps ? (num(exifData?.['longitude']) ?? null) : null;
  const gpsAltitude = hasGps ? (num(exifData?.['GPSAltitude']) ?? null) : null;

  // ---- C2PA inspection ----
  const c2pa = inspectC2PA(buffer);

  // ---- Build normalized metadata ----
  const normalized: NormalizedMetadata = {
    camera: { make: cameraMake, model: cameraModel, lensMake, lensModel, focalLength, aperture, shutterSpeed, iso },
    capture: { datetime: capturedAt, timezone: capturedAtTimezone },
    timestamps: { capturedAt, capturedAtTimezone, metadataCreatedAt, metadataModifiedAt },
    location: { hasGps, latitude: gpsLatitude, longitude: gpsLongitude, altitude: gpsAltitude },
    software,
    editingSoftware,
    orientation,
    colorSpace,
    colorProfile: str(exifData?.['ProfileDescription'] ?? exifData?.['ICCProfileName']) ?? null,
    c2pa: { status: c2pa.status, issuer: c2pa.issuer, payload: c2pa.payload },
  };

  // ---- Technical characteristics via sharp (read-only) ----
  let characteristics: Partial<Omit<ImageCharacteristicsRecord, 'id' | 'imageId' | 'createdAt'>> = {};
  try {
    const sharpMeta = await sharp(buffer).metadata();
    const jpegInfo = await extractJpegInfo(buffer, sharpMeta);

    // Compute reduced aspect ratio using GCD
    const [arW, arH] = sharpMeta.width && sharpMeta.height
      ? reduceRatio(sharpMeta.width, sharpMeta.height)
      : [null, null];

    characteristics = {
      width: sharpMeta.width ?? null,
      height: sharpMeta.height ?? null,
      aspectRatioW: arW,
      aspectRatioH: arH,
      pixelCount: sharpMeta.width && sharpMeta.height ? sharpMeta.width * sharpMeta.height : null,
      channels: sharpMeta.channels ?? null,
      bitDepth: sharpMeta.depth ? parseDepth(sharpMeta.depth) : null,
      colorSpace: sharpMeta.space ?? null,
      hasAlpha: !!(sharpMeta.hasAlpha),
      jpegProgressive: jpegInfo.progressive,
      jpegSamplingFactors: jpegInfo.samplingFactors,
      jpegQuantTables: jpegInfo.quantTables,
      jpegMarkers: jpegInfo.markers,
      jpegQualityEstimate: jpegInfo.qualityEstimate,
      jpegQualityIsEstimate: jpegInfo.qualityIsEstimate,
      extractorName: 'image_characteristics',
      extractorVersion: '1.0.0',
      extractedAt: new Date().toISOString(),
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    warnings.push(`Characteristics extraction warning: ${msg}`);
  }

  // ---- Collect evidence items from metadata ----
  const addEvidence = (cat: string, key: string, value: unknown, type: string) => {
    if (value !== null && value !== undefined) {
      evidenceItems.push({ category: cat, key, value, valueType: type });
    }
  };

  if (cameraMake) addEvidence('camera', 'make', cameraMake, 'string');
  if (cameraModel) addEvidence('camera', 'model', cameraModel, 'string');
  if (software) addEvidence('software', 'software', software, 'string');
  if (editingSoftware) addEvidence('software', 'editing_software', editingSoftware, 'string');
  if (hasGps) addEvidence('location', 'has_gps', true, 'boolean');
  addEvidence('metadata', 'c2pa_status', c2pa.status, 'string');
  if (orientation !== null) addEvidence('camera', 'orientation', orientation, 'number');

  return { normalized, characteristics, evidenceItems, warnings };
}

// ---- Helpers ----

function str(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'string') return v.trim() || null;
  if (typeof v === 'number') return String(v);
  return null;
}

function num(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

function dateStr(v: unknown): string | null {
  if (!v) return null;
  if (v instanceof Date) return v.toISOString();
  if (typeof v === 'string') {
    try {
      const d = new Date(v);
      return isNaN(d.getTime()) ? null : d.toISOString();
    } catch { return null; }
  }
  return null;
}

function shutterStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'number') return v < 1 ? `1/${Math.round(1 / v)}` : `${v}`;
  if (typeof v === 'string') return v;
  return null;
}

/**
 * Detects known editing software strings in EXIF metadata.
 * Records the value as evidence only — not as a manipulation verdict.
 */
function detectEditingSoftware(exif: Record<string, unknown> | null): string | null {
  if (!exif) return null;
  const sw = str(exif['Software']);
  if (!sw) return null;
  const lower = sw.toLowerCase();
  const knownEditors = ['photoshop', 'lightroom', 'gimp', 'affinity', 'capture one', 'darktable', 'snapseed', 'vsco', 'facetune', 'canva', 'pixelmator', 'luminar'];
  return knownEditors.some((e) => lower.includes(e)) ? sw : null;
}

/**
 * Inspects for C2PA / Content Credentials signatures.
 *
 * Full C2PA parsing requires a dedicated library. In Phase 2 we detect
 * presence via byte signature only and record it as UNSUPPORTED until
 * the c2pa-rs/c2pa-node library is integrated in a later phase.
 */
function inspectC2PA(buffer: Buffer): { status: C2PAStatus; issuer: string | null; payload: Record<string, unknown> | null } {
  // C2PA embeds a 'jumb' box (JPEG/JUMBF) or XMP reference.
  // We check for the JUMBF box signature 'jumb' (0x6a756d62) in the buffer.
  // This is presence detection only — actual manifest parsing is Phase 2+.
  const jumbMagic = Buffer.from([0x6a, 0x75, 0x6d, 0x62]);
  let found = false;
  for (let i = 0; i < Math.min(buffer.length - 4, 8192); i++) {
    if (buffer[i] === jumbMagic[0] && buffer.subarray(i, i + 4).equals(jumbMagic)) {
      found = true;
      break;
    }
  }
  return {
    status: found ? 'PRESENT' : 'ABSENT',
    issuer: null,
    payload: found ? { detected: true, note: 'JUMBF signature found. Full parsing requires c2pa library (planned).' } : null,
  };
}

/** Extract JPEG-specific information from buffer + sharp metadata. */
async function extractJpegInfo(buffer: Buffer, meta: sharp.Metadata): Promise<{
  progressive: boolean | null;
  samplingFactors: string | null;
  quantTables: Record<string, unknown>[] | null;
  markers: string[] | null;
  qualityEstimate: number | null;
  qualityIsEstimate: boolean;
}> {
  if (meta.format !== 'jpeg') {
    return { progressive: null, samplingFactors: null, quantTables: null, markers: null, qualityEstimate: null, qualityIsEstimate: true };
  }

  // Parse JPEG markers from raw bytes
  const markers: string[] = [];
  const quantTables: Record<string, unknown>[] = [];
  let progressive = false;
  let samplingFactors: string | null = null;

  try {
    let i = 0;
    while (i < buffer.length - 1) {
      if (buffer[i] !== 0xff) { i++; continue; }
      const marker = buffer[i + 1];
      const markerHex = `FF${marker.toString(16).toUpperCase().padStart(2, '0')}`;

      if (!markers.includes(markerHex)) markers.push(markerHex);

      if (marker === 0xC2) progressive = true; // SOF2 = progressive DCT

      // DQT marker (0xDB) — quantization table
      if (marker === 0xDB) {
        const segLen = buffer.readUInt16BE(i + 2);
        const tableId = buffer[i + 4] & 0x0f;
        const precision = (buffer[i + 4] >> 4) & 0x0f;
        // Extract first 8 values as a sample (full table is 64 values)
        const values: number[] = [];
        for (let j = 0; j < Math.min(8, segLen - 3); j++) {
          values.push(buffer[i + 5 + j]);
        }
        quantTables.push({ tableId, precision, firstValues: values });
        i += 2 + segLen;
        continue;
      }

      // SOF0/SOF1 — sampling factors
      if (marker === 0xC0 || marker === 0xC1) {
        const components = buffer[i + 9];
        const sf: string[] = [];
        for (let c = 0; c < components; c++) {
          const h = (buffer[i + 11 + c * 3] >> 4) & 0x0f;
          const v = buffer[i + 11 + c * 3] & 0x0f;
          sf.push(`${h}x${v}`);
        }
        samplingFactors = sf.join(',');
      }

      if (marker === 0xD8 || marker === 0xD9) { i += 2; continue; }
      if (i + 3 < buffer.length) {
        const len = buffer.readUInt16BE(i + 2);
        i += 2 + len;
      } else { break; }
    }
  } catch { /* malformed JPEG — return what we have */ }

  // Estimate quality from first quantization table (table 0, luminance)
  let qualityEstimate: number | null = null;
  const qtable0 = quantTables.find((t) => t['tableId'] === 0);
  if (qtable0 && Array.isArray(qtable0['firstValues']) && qtable0['firstValues'].length > 0) {
    // Standard approximation: lower DC value → higher quality
    const dcValue = qtable0['firstValues'][0] as number;
    if (dcValue > 0) {
      // Rough inverse mapping from standard tables (this is an estimate)
      qualityEstimate = Math.min(100, Math.max(1, Math.round(100 - dcValue * 0.7)));
    }
  }

  return {
    progressive,
    samplingFactors,
    quantTables: quantTables.length > 0 ? quantTables : null,
    markers: markers.length > 0 ? markers : null,
    qualityEstimate,
    qualityIsEstimate: true, // Always an estimate without libjpeg internals
  };
}

function parseDepth(depth: string): number | null {
  const n = parseInt(depth, 10);
  return isNaN(n) ? null : n;
}

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

function reduceRatio(w: number, h: number): [number, number] {
  const g = gcd(w, h);
  return [w / g, h / g];
}
