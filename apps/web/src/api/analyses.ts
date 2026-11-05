/**
 * TanStack Query hooks for analysis and AI detection endpoints.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  CreateAnalysisRequest, CreateAnalysisResponse,
  AnalysisRecord, PaginatedResponse, AIDetectionDBRecord,
} from '@pinithub/shared';

export function useAnalyses(params?: { page?: number; pageSize?: number; status?: string }) {
  const search = new URLSearchParams();
  if (params?.page) search.set('page', String(params.page));
  if (params?.pageSize) search.set('pageSize', String(params.pageSize));
  if (params?.status) search.set('status', params.status);
  return useQuery<PaginatedResponse<AnalysisRecord>>({
    queryKey: ['analyses', params],
    queryFn: () => apiClient.get(`/v1/analyses?${search.toString()}`),
  });
}

export function useAnalysis(id: string | null) {
  return useQuery<{ analysis: AnalysisRecord }>({
    queryKey: ['analysis', id],
    queryFn: () => apiClient.get(`/v1/analyses/${id}`),
    enabled: !!id,
  });
}

export function useCreateAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateAnalysisRequest) =>
      apiClient.post<CreateAnalysisResponse>('/v1/analyses', req),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analyses'] }),
  });
}

export function useDeleteAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/v1/analyses/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analyses'] }),
  });
}

// ---- Phase 6: AI Detection ----

export function useAIDetection(analysisId: string | null) {
  return useQuery<{ analysisId: string; aiDetection: AIDetectionDBRecord } | { status: string }>({
    queryKey: ['ai-detection', analysisId],
    queryFn: () => apiClient.get(`/v1/analyses/${analysisId}/ai-detection`),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const d = query.state.data as any;
      if (!d) return false;
      const status = d.aiDetection?.status ?? d.status;
      return ['QUEUED', 'RUNNING'].includes(status) ? 3000 : false;
    },
  });
}

export function useTriggerAIDetection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (analysisId: string) =>
      apiClient.post(`/v1/analyses/${analysisId}/ai-detection`),
    onSuccess: (_data, analysisId) => {
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['ai-detection', analysisId] });
      }, 2000);
    },
  });
}
