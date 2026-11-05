/**
 * TanStack Query hooks for image comparison and crop detection (Phase 4 + 5).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ComparisonRecord, CreateComparisonRequest, CropDetectionDBRecord } from '@pinithub/shared';

export interface ComparisonListResponse {
  items: ComparisonRecord[];
  total: number;
  page: number;
  pageSize: number;
}

export function useComparisons(page = 1, pageSize = 10) {
  return useQuery<ComparisonListResponse>({
    queryKey: ['comparisons', page, pageSize],
    queryFn: () => apiClient.get(`/v1/comparisons?page=${page}&pageSize=${pageSize}`),
  });
}

export function useComparison(id: string | null) {
  return useQuery<{ comparison: ComparisonRecord }>({
    queryKey: ['comparison', id],
    queryFn: () => apiClient.get(`/v1/comparisons/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = (query.state.data as any)?.comparison?.status;
      const running = ['QUEUED', 'RUNNING', 'MATCHING', 'REGISTERING', 'COMPARING'].includes(status);
      return running ? 3000 : false;
    },
  });
}

export function useComparisonRegions(id: string | null) {
  return useQuery<{ comparisonId: string; regions: any[]; total: number; note: string }>({
    queryKey: ['comparison-regions', id],
    queryFn: () => apiClient.get(`/v1/comparisons/${id}/regions`),
    enabled: !!id,
  });
}

export function useCreateComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateComparisonRequest) =>
      apiClient.post<{ comparison: ComparisonRecord }>('/v1/comparisons', req),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comparisons'] }),
  });
}

export function useDeleteComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/v1/comparisons/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['comparisons'] });
      qc.invalidateQueries({ queryKey: ['comparison'] });
    },
  });
}

// ---- Phase 5: Crop detection ----

export interface CropDetectionResponse {
  comparisonId: string;
  cropDetection: CropDetectionDBRecord;
  note: string;
}

export function useCropDetection(comparisonId: string | null) {
  return useQuery<CropDetectionResponse | { status: string; message: string }>({
    queryKey: ['crop-detection', comparisonId],
    queryFn: () => apiClient.get(`/v1/comparisons/${comparisonId}/crop-detection`),
    enabled: !!comparisonId,
    // Poll while running
    refetchInterval: (query) => {
      const d = query.state.data as any;
      if (!d) return false;
      const status = d.cropDetection?.status ?? d.status;
      return ['QUEUED', 'NOT_RUN'].includes(status) ? false : false;
    },
  });
}

export function useTriggerCropDetection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (comparisonId: string) =>
      apiClient.post(`/v1/comparisons/${comparisonId}/crop-detection`),
    onSuccess: (_data, comparisonId) => {
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['crop-detection', comparisonId] });
      }, 2000);
    },
  });
}
