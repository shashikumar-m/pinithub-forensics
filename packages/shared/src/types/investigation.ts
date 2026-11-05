/**
 * Investigation and final verdict types — Phase 8.
 *
 * IMPORTANT: The final verdict is evidence-based, not guaranteed.
 * "NOT_EDITED" does not mean "guaranteed authentic".
 * "EDITED" does not identify the editor or intent.
 * All scores are UNCALIBRATED unless explicitly stated otherwise.
 */

export type FinalVerdict =
  | 'EDITED' | 'NOT_EDITED' | 'INCONCLUSIVE' | 'NO_MATCH' | 'ANALYSIS_UNAVAILABLE';

export type EvidenceStatus = 'SUPPORTING' | 'NEUTRAL' | 'CONTRADICTING' | 'UNAVAILABLE';
export type EvidenceStrength = 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT';
export type ConfidenceStatus = 'CALIBRATED' | 'UNCALIBRATED' | 'UNAVAILABLE';

export interface InvestigationSummary {
  id: string;
  ownerId: string;
  comparisonId: string | null;
  status: string;
  verdict: FinalVerdict | null;
  confidenceStatus: ConfidenceStatus | null;
  evidenceStrength: EvidenceStrength | null;
  explanation: string | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
  evidenceCount: number;
  regionCount: number;
  reportHash: string | null;
  isSealed: boolean;
  sealedAt: string | null;
  sealedHash: string | null;
  note: string;
}

export interface EvidenceItem {
  id: string;
  category: string;
  detector: string;
  version: string;
  status: EvidenceStatus;
  score: number | null;
  description: string;
  evidenceGroup: string | null;
  executionMs: number | null;
}

export interface FinalRegion {
  id: string;
  type: string;
  bbox: { x: number; y: number; width: number; height: number };
  polygon?: Array<{ x: number; y: number }>;
  areaPixels: number;
  areaPercentage: number;
  confidence?: number;
  evidenceCount: number;
  sourceDetectors: string[];
  coordinateSystem: 'ORIGINAL_IMAGE_COORDINATES';
}

export interface SealedRecord {
  investigationId: string;
  isSealed: boolean;
  sealedHash: string;
  reportHash: string;
  sealedAt: string;
  algorithm: 'SHA-256';
  tamperEvident: true;
}
