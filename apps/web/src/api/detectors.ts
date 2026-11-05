/**
 * TanStack Query hooks for detector output endpoints (Phase 3).
 */
import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';

export interface DetectorOutput {
  id: string;
  detector: string;
  version: string;
  category: string;
  status: string;
  score: number | null;
  confidence: number | null;
  mapStoragePath: string | null;
  details: Record<string, unknown>;
  executionTimeMs: number | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export function useDetectorOutputs(analysisId: string | null) {
  return useQuery<{
    analysisId: string;
    detectors: DetectorOutput[];
    total: number;
    note: string;
  }>({
    queryKey: ['detector-outputs', analysisId],
    queryFn: () => apiClient.get(`/v1/analyses/${analysisId}/detectors`),
    enabled: !!analysisId,
  });
}

export function useDetectorOutput(analysisId: string | null, detectorName: string | null) {
  return useQuery<{ analysisId: string; detector: DetectorOutput }>({
    queryKey: ['detector-output', analysisId, detectorName],
    queryFn: () => apiClient.get(`/v1/analyses/${analysisId}/detectors/${detectorName}`),
    enabled: !!analysisId && !!detectorName,
  });
}

export function useAnalysisArtifacts(analysisId: string | null) {
  return useQuery<{ analysisId: string; artifacts: any[]; total: number }>({
    queryKey: ['analysis-artifacts', analysisId],
    queryFn: () => apiClient.get(`/v1/analyses/${analysisId}/artifacts`),
    enabled: !!analysisId,
  });
}
