/**
 * Crop detection result types — Phase 5.
 *
 * crop_percentage = 100 × (1 - kept_area / original_area)
 * This represents the percentage of the ORIGINAL image that was cut away.
 * All coordinates are in ORIGINAL_IMAGE_COORDINATES.
 */

export type CropDetectionStatus =
  | 'DETECTED'
  | 'NO_CROP'
  | 'NO_MATCH'
  | 'INCONCLUSIVE'
  | 'FAILED';

export interface CropPolygonPoint {
  x: number;
  y: number;
}

export interface CropBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RegistrationQuality {
  inlierCount: number | null;
  inlierRatio: number | null;
  reprojectionError: number | null;
  goodMatches: number | null;
  keypointsReference: number | null;
  keypointsSuspect: number | null;
  overlapPercentage: number | null;
}

export interface CropDetectionResult {
  status: CropDetectionStatus;
  cropPercentage: number | null;
  keptPercentage: number | null;
  originalAreaPixels: number;
  keptAreaPixels: number | null;
  removedAreaPixels: number | null;
  cropPolygon: CropPolygonPoint[] | null;
  boundingBox: CropBoundingBox | null;
  coordinateSystem: 'ORIGINAL_IMAGE_COORDINATES';
  confidence: number | null;
  reliability: string | null;
  registrationQuality: RegistrationQuality | null;
  method: string;
  detector: string;
  version: string;
  executionMs: number;
  warnings: string[] | null;
  error: string | null;
}

export interface CropDetectionDBRecord {
  id: string;
  comparisonId: string;
  status: CropDetectionStatus;
  cropPercentage: number | null;
  keptPercentage: number | null;
  originalAreaPixels: number;
  keptAreaPixels: number | null;
  removedAreaPixels: number | null;
  cropPolygon: CropPolygonPoint[] | null;
  boundingBox: CropBoundingBox | null;
  confidence: number | null;
  reliability: string | null;
  registrationQuality: RegistrationQuality | null;
  method: string | null;
  detectorName: string | null;
  detectorVersion: string | null;
  executionMs: number | null;
  warnings: string[] | null;
  error: string | null;
  createdAt: string;
}
