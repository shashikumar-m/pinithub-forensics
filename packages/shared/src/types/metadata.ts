/**
 * Metadata / EXIF domain types — Phase 2.
 *
 * IMPORTANT: Metadata is forensic EVIDENCE, not proof of authenticity.
 * Do not interpret these fields as definitive manipulation verdicts.
 * The forensic reasoning layer will interpret these signals in later phases.
 */

/** C2PA/Content Credentials inspection status. */
export type C2PAStatus =
  | 'PRESENT'
  | 'ABSENT'
  | 'UNREADABLE'
  | 'UNSUPPORTED';

/** Result of SHA-256 re-verification against the stored file. */
export type IntegrityStatus = 'VERIFIED' | 'MISMATCH' | 'SKIPPED' | 'ERROR';

/**
 * Normalized metadata extracted from a protected image.
 * All fields are nullable — missing metadata is represented as null,
 * never as a fabricated value.
 */
export interface NormalizedMetadata {
  camera: {
    make: string | null;
    model: string | null;
    lensMake: string | null;
    lensModel: string | null;
    focalLength: number | null;
    aperture: number | null;
    shutterSpeed: string | null;
    iso: number | null;
  };
  capture: {
    datetime: string | null;
    /** Timezone string when available, e.g. "+05:30". null means unknown — NOT UTC. */
    timezone: string | null;
  };
  timestamps: {
    capturedAt: string | null;
    capturedAtTimezone: string | null;
    metadataCreatedAt: string | null;
    metadataModifiedAt: string | null;
  };
  location: {
    /** Whether GPS data is present in the image */
    hasGps: boolean;
    /** Latitude in decimal degrees — controlled display, not exposed by default */
    latitude: number | null;
    /** Longitude in decimal degrees — controlled display, not exposed by default */
    longitude: number | null;
    altitude: number | null;
  };
  software: string | null;
  editingSoftware: string | null;
  orientation: number | null;
  colorSpace: string | null;
  colorProfile: string | null;
  c2pa: {
    status: C2PAStatus;
    /** Non-sensitive credential information when present */
    issuer: string | null;
    payload: Record<string, unknown> | null;
  };
}

/** Full image metadata record as stored in the database. */
export interface ImageMetadataRecord {
  id: string;
  imageId: string;

  // Camera
  cameraMake: string | null;
  cameraModel: string | null;
  lensMake: string | null;
  lensModel: string | null;
  focalLength: number | null;
  aperture: number | null;
  shutterSpeed: string | null;
  iso: number | null;
  orientation: number | null;
  colorSpace: string | null;
  colorProfile: string | null;
  software: string | null;
  editingSoftware: string | null;

  // Timestamps (intentionally distinct — do not merge)
  capturedAt: string | null;
  capturedAtTimezone: string | null;
  metadataCreatedAt: string | null;
  metadataModifiedAt: string | null;

  // GPS
  hasGps: boolean;
  /** null when GPS not present or not shown for privacy */
  gpsLatitude: number | null;
  gpsLongitude: number | null;
  gpsAltitude: number | null;

  // Raw payloads
  exifRaw: Record<string, unknown> | null;
  xmpRaw: Record<string, unknown> | null;
  iptcRaw: Record<string, unknown> | null;
  comments: string[] | null;

  // C2PA
  c2paStatus: C2PAStatus | null;
  c2paPayload: Record<string, unknown> | null;

  // Extraction info
  extractorName: string;
  extractorVersion: string;
  extractedAt: string;
  createdAt: string;
}

/** Technical image characteristics. */
export interface ImageCharacteristicsRecord {
  id: string;
  imageId: string;

  // Dimensions
  width: number | null;
  height: number | null;
  aspectRatioW: number | null;
  aspectRatioH: number | null;
  pixelCount: number | null;

  // Color
  channels: number | null;
  bitDepth: number | null;
  colorSpace: string | null;
  hasAlpha: boolean;

  // JPEG-specific (null for non-JPEG)
  jpegProgressive: boolean | null;
  jpegSamplingFactors: string | null;
  /** Quantization tables as JSON — forensic evidence, not a verdict */
  jpegQuantTables: Record<string, unknown>[] | null;
  jpegMarkers: string[] | null;
  /**
   * Estimated JPEG quality (0-100).
   * Always check jpegQualityIsEstimate before treating as precise.
   */
  jpegQualityEstimate: number | null;
  /** True when jpegQualityEstimate is an approximation only. */
  jpegQualityIsEstimate: boolean;

  extractorName: string;
  extractorVersion: string;
  extractedAt: string;
  createdAt: string;
}

/** A single atomic forensic evidence item. */
export interface ForensicEvidenceItem {
  id: string;
  imageId: string;
  category: string;
  key: string;
  value: unknown;
  valueType: string;
  source: string;
  detectorName: string | null;
  detectorVersion: string | null;
  confidence: number | null;
  createdAt: string;
}

/** Integrity check result for a protected image. */
export interface IntegrityCheckRecord {
  id: string;
  imageId: string;
  status: IntegrityStatus;
  storedHash: string;
  /** null when check could not be completed */
  computedHash: string | null;
  checkedAt: string;
  note: string | null;
}

/** A derived artifact (e.g. display-normalized copy for analysis). */
export interface DerivedArtifactRecord {
  id: string;
  sourceImageId: string;
  artifactType: string;
  transformationName: string;
  transformationVersion: string;
  storagePath: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  note: string | null;
  createdAt: string;
}

/** Full metadata analysis result from the Python service. */
export interface MetadataAnalysisResult {
  detector: string;
  version: string;
  status: 'COMPLETED' | 'PARTIAL' | 'FAILED';
  executionMs: number;
  normalizedMetadata: NormalizedMetadata;
  characteristics: Omit<ImageCharacteristicsRecord, 'id' | 'imageId' | 'createdAt'>;
  integrityStatus: IntegrityStatus;
  evidenceItems: Omit<ForensicEvidenceItem, 'id' | 'imageId' | 'createdAt'>[];
  error: string | null;
}
