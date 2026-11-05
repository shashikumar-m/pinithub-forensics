/**
 * Region domain types.
 *
 * A Region represents a localized area of an image that a detector
 * flagged as interesting (edited, generated, copied, etc.). Regions
 * carry an optional binary mask stored as an artifact in object storage.
 */

export type RegionType =
  | 'AI_GENERATED'
  | 'AI_EDITED'
  | 'INPAINTED'
  | 'COPY_MOVE'
  | 'SPliced'
  | 'CROP_BOUNDARY'
  | 'COMPRESSION_ARTIFACT'
  | 'OTHER';

/** Axis-aligned bounding box in pixel coordinates. */
export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RegionRecord {
  id: string;
  analysisId: string;
  detectorOutputId: string;
  type: RegionType;
  /** Bounding box in image pixel coordinates */
  bbox: BoundingBox;
  /** Detector score for this region, 0-1 */
  score: number;
  /** Storage path to the binary mask artifact, when available */
  maskStoragePath: string | null;
  /** Free-text evidence / rationale */
  description: string | null;
  createdAt: string;
}
