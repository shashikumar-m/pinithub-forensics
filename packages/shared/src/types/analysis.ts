/**
 * Analysis domain types.
 *
 * An Analysis represents a forensic investigation request. It groups
 * one or more AnalysisJobs (which execute detectors) and aggregates
 * detector outputs, regions, and eventually a forensic report.
 */

export type AnalysisStatus =
  | 'CREATED'
  | 'QUEUED'
  | 'RUNNING'
  | 'DONE'
  | 'FAILED'
  | 'NOT_RUN';

export type AnalysisType =
  | 'AI_GENERATED_DETECTION'
  | 'AI_EDIT_DETECTION'
  | 'REGION_LOCALIZATION'
  | 'ORIGINAL_VS_COPY'
  | 'CROP_PERCENTAGE'
  | 'TRAVELLED_COPY'
  | 'METADATA_EXIF'
  | 'COMPREHENSIVE';

export interface AnalysisRecord {
  id: string;
  ownerId: string;
  /** Primary image under investigation */
  imageId: string;
  /** Optional reference/original image for comparison analyses */
  referenceImageId: string | null;
  type: AnalysisType;
  status: AnalysisStatus;
  /** Final aggregated verdict, only present when DONE and implemented */
  verdict: string | null;
  /** Overall confidence 0-1, only present when DONE and implemented */
  confidence: number | null;
  /** Error description if FAILED */
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Payload accepted by POST /v1/analyses */
export interface CreateAnalysisRequest {
  imageId: string;
  referenceImageId?: string;
  type: AnalysisType;
}

/** Response from POST /v1/analyses */
export interface CreateAnalysisResponse {
  analysis: AnalysisRecord;
}
