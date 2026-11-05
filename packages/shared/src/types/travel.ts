/**
 * Travelled-copy and investigation result types — Phase 7.
 *
 * IMPORTANT:
 * "TRANSFORMED_COPY" is NOT a content manipulation verdict.
 * Transport transformations (compression, resize, metadata stripping,
 * screenshots) are common platform behaviours and must NOT be
 * automatically classified as malicious edits.
 */

export type TravelTransformation =
  | 'NONE' | 'JPEG_RECOMPRESSION' | 'RESIZE' | 'CROP' | 'CROP_AND_RESIZE'
  | 'ROTATION' | 'BRIGHTNESS' | 'CONTRAST' | 'COLOR_CHANGE' | 'FILTER'
  | 'SCREENSHOT' | 'METADATA_CHANGE' | 'TEXT_ADDED' | 'STICKER_ADDED'
  | 'OBJECT_ADDED' | 'OBJECT_REMOVED' | 'AI_EDIT' | 'AI_GENERATED' | 'UNKNOWN';

/** Whether a transformation is transport or content. */
export const TRANSPORT_TRANSFORMS = new Set<TravelTransformation>([
  'JPEG_RECOMPRESSION', 'RESIZE', 'METADATA_CHANGE', 'SCREENSHOT',
  'COLOR_CHANGE', 'FILTER', 'ROTATION', 'BRIGHTNESS', 'CONTRAST',
]);

export const CONTENT_TRANSFORMS = new Set<TravelTransformation>([
  'CROP', 'CROP_AND_RESIZE', 'TEXT_ADDED', 'STICKER_ADDED',
  'OBJECT_ADDED', 'OBJECT_REMOVED', 'AI_EDIT', 'AI_GENERATED',
]);

export type InvestigationStatus =
  | 'NO_SIGNIFICANT_CHANGE' | 'TRANSFORMED_COPY' | 'CONTENT_CHANGED'
  | 'AI_CHANGE_DETECTED' | 'NO_MATCH' | 'INCONCLUSIVE' | 'QUEUED' | 'FAILED';

export interface TravelChangeRegion {
  type: string;
  bbox: { x: number; y: number; width: number; height: number };
  polygon?: Array<{ x: number; y: number }>;
  areaPixels?: number;
  areaPercentage?: number;
  evidence: string[];
  reliability?: string;
  detector?: string;
  detectorVersion?: string;
}

export interface MetadataChange {
  field: string;
  status: 'UNCHANGED' | 'REMOVED' | 'MODIFIED' | 'ADDED' | 'UNAVAILABLE';
  originalValue?: string;
  returnedValue?: string;
}

export interface TravelAnalysisRecord {
  id: string;
  comparisonId: string;
  status: InvestigationStatus;
  transformations: TravelTransformation[] | null;
  changes: TravelChangeRegion[] | null;
  metadataChanges: MetadataChange[] | null;
  cropResult: Record<string, unknown> | null;
  aiDetectionResult: Record<string, unknown> | null;
  registrationQuality: Record<string, unknown> | null;
  evidence: string[] | null;
  warnings: string[] | null;
  analyzerVersion: string | null;
  executionMs: number | null;
  error: string | null;
  createdAt: string;
}
