/**
 * TanStack Query hooks for travel analysis endpoints (Phase 7).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { TravelAnalysisRecord } from '@pinithub/shared';

export function useTravelAnalysis(comparisonId: string | null) {
  return useQuery<{ comparisonId: string; travelAnalysis: TravelAnalysisRecord } | { status: string }>({
    queryKey: ['travel-analysis', comparisonId],
    queryFn: () => apiClient.get(`/v1/comparisons/${comparisonId}/travel-analysis`),
    enabled: !!comparisonId,
    refetchInterval: (query) => {
      const d = query.state.data as any;
      const status = d?.travelAnalysis?.status ?? d?.status;
      return ['QUEUED', 'RUNNING'].includes(status) ? 3000 : false;
    },
  });
}

export function useTriggerTravelAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (comparisonId: string) =>
      apiClient.post(`/v1/comparisons/${comparisonId}/travel-analysis`),
    onSuccess: (_data, comparisonId) => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['travel-analysis', comparisonId] }), 2000);
    },
  });
}
