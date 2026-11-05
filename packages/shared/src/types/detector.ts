/**
 * DetectorOutput domain types.
 *
 * A DetectorOutput is the raw result of running one forensic detector
 * against an image. This contract mirrors the Python service's detector
 * result schema so results flow cleanly between services.
 */

export type DetectorCategory =
  | 'AI_GENERATED'
  | 'AI_EDITED'
  | 'ELA'
  | 'NOISE_RESIDUAL'
  | 'DCT'
  | 'JPEG_DOUBLE_COMPRESSION'
  | 'COPY_MOVE'
  | 'KEYPOINT_MATCH'
  | 'CROP_PERCENTAGE'
  | 'TRAVELLED_COPY'
  | 'METADATA';

export type DetectorOutputStatus = 'NOT_RUN' | 'RUNNING' | 'DONE' | 'FAILED' | 'NOT_IMPLEMENTED';

export interface DetectorOutputRecord {
  id: string;
  analysisId: string;
  /** Detector identifier, e.g. "ela-v1" */
  detector: string;
  /** Version of the detector that produced this output */
  version: string;
  category: DetectorCategory;
  status: DetectorOutputStatus;
  /** Primary score 0-1, when available */
  score: number | null;
  /** Confidence / reliability 0-1, when available */
  confidence: number | null;
  /** Storage path to a heatmap/mask artifact, when available */
  mapStoragePath: string | null;
  /** Detector-specific structured evidence */
  details: Record<string, unknown> | null;
  /** Execution time in milliseconds */
  executionTimeMs: number | null;
  /** Error description if FAILED */
  error: string | null;
  createdAt: string;
  updatedAt: string;
}
