/**
 * AI Detection result types — Phase 6.
 *
 * IMPORTANT: AI detection is experimental and UNCALIBRATED.
 * Raw scores are not probabilities. No final verdict is produced.
 * Language: "Current model detected AI-like evidence in N regions."
 */

export type AIDetectionStatus =
  | 'AI_GENERATED'
  | 'AI_EDITED_LOCAL'
  | 'NO_AI_EVIDENCE'
  | 'INCONCLUSIVE'
  | 'UNAVAILABLE'
  | 'QUEUED'
  | 'RUNNING'
  | 'FAILED';

export interface AIRegion {
  bbox: { x: number; y: number; width: number; height: number };
  polygon?: Array<{ x: number; y: number }>;
  areaPixels: number;
  areaPercentage: number;
  confidence?: number;  // raw, UNCALIBRATED
  editType?: string;
  evidence: string[];
}

export interface AIDetectionDBRecord {
  id: string;
  analysisId: string;
  status: AIDetectionStatus;
  imageLevelScore: number | null;
  imageLevelLabel: string | null;
  editedAreaPct: number | null;
  modelName: string | null;
  modelVersion: string | null;
  weightsHash: string | null;
  calibrationStatus: string;   // always "UNCALIBRATED" until calibrated
  heatmapStoragePath: string | null;
  maskStoragePath: string | null;
  regions: AIRegion[] | null;
  evidence: string[] | null;
  warnings: string[] | null;
  executionMs: number | null;
  error: string | null;
  createdAt: string;
}
