/**
 * Image comparison domain types — Phase 4.
 *
 * A comparison represents the forensic registration and difference analysis
 * between a protected original and a suspect/travelled copy.
 *
 * IMPORTANT: A comparison result is forensic evidence.
 * It is NOT an authenticity verdict.
 * "Registration succeeded" ≠ "Image is authentic".
 * "Differences found" ≠ "Image was maliciously edited".
 */

export type ComparisonStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'MATCHING'
  | 'REGISTERING'
  | 'COMPARING'
  | 'COMPLETED'
  | 'FAILED'
  | 'NO_MATCH'
  | 'INCONCLUSIVE';

/** Request body for creating a comparison */
export interface CreateComparisonRequest {
  referenceImageId: string;
  suspectImageId: string;
}

/** Full comparison record as returned by the API */
export interface ComparisonRecord {
  id: string;
  ownerId: string;
  referenceImageId: string;
  suspectImageId: string;
  status: ComparisonStatus;
  registrationMethod: string | null;
  detectorUsed: string | null;
  detectorVersion: string | null;

  // Keypoint evidence
  keypointsReference: number | null;
  keypointsSuspect: number | null;
  rawMatches: number | null;
  goodMatches: number | null;
  inlierCount: number | null;
  outlierCount: number | null;
  inlierRatio: number | null;
  reprojectionError: number | null;

  // Homography
  homographyMatrix: number[][] | null;
  projectedCorners: number[][] | null;
  overlapRatio: number | null;

  // Normalization
  normalizationMethod: string | null;

  // Difference
  meanAbsDiff: number | null;
  ssimScore: number | null;

  executionTimeMs: number | null;
  error: string | null;
  warnings: string[] | null;
  createdAt: string;
  updatedAt: string;
}

/** Spatial difference map associated with a comparison */
export interface ComparisonDiffMap {
  id: string;
  comparisonId: string;
  absDiffStoragePath: string | null;
  ssimMapStoragePath: string | null;
  overlapMaskPath: string | null;
  alignedSuspectPath: string | null;
  meanAbsDiff: number | null;
  medianAbsDiff: number | null;
  p95AbsDiff: number | null;
  ssimScore: number | null;
  noiseFloor: number | null;
  diffMethod: string | null;
  normalizationMethod: string | null;
  createdAt: string;
}

/** A candidate changed region in the original image coordinate system */
export interface ComparisonRegion {
  id: string;
  comparisonId: string;
  bbox: { x: number; y: number; width: number; height: number };
  pixelArea: number | null;
  areaPercent: number | null;
  meanDiffScore: number | null;
  maskStoragePath: string | null;
  sourceEvidence: string | null;
}

/** Full result of a registration computation (Python service output) */
export interface RegistrationResult {
  status: ComparisonStatus;
  detector: string;
  detectorVersion: string;
  keypointsReference: number;
  keypointsSuspect: number;
  rawMatches: number;
  goodMatches: number;
  inlierCount: number;
  outlierCount: number;
  inlierRatio: number;
  reprojectionError: number | null;
  homographyMatrix: number[][] | null;
  projectedCorners: number[][] | null;
  overlapRatio: number | null;
  executionTimeMs: number;
  warnings: string[];
  error: string | null;
  qualityChecks: RegistrationQualityChecks;
}

/** Quality checks performed on a homography */
export interface RegistrationQualityChecks {
  sufficientMatches: boolean;
  sufficientInliers: boolean;
  inlierRatioAboveThreshold: boolean;
  reprojectionErrorAcceptable: boolean;
  homographyNotDegenerate: boolean;
  cornersProjectedValidly: boolean;
  scaleReasonable: boolean;
  overallPass: boolean;
}
