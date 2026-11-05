import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { InvestigationSummary, EvidenceItem, FinalRegion, SealedRecord } from '@pinithub/shared';

export function useInvestigation(id: string | null) {
  return useQuery<{ investigation: InvestigationSummary }>({
    queryKey: ['investigation', id],
    queryFn: () => apiClient.get(`/v1/investigations/${id}`),
    enabled: !!id,
    refetchInterval: (q) => {
      const status = (q.state.data as any)?.investigation?.status;
      return ['PENDING', 'RUNNING'].includes(status) ? 3000 : false;
    },
  });
}

export function useInvestigationEvidence(id: string | null) {
  return useQuery<{ investigationId: string; items: EvidenceItem[]; total: number }>({
    queryKey: ['investigation-evidence', id],
    queryFn: () => apiClient.get(`/v1/investigations/${id}/evidence`),
    enabled: !!id,
  });
}

export function useInvestigationRegions(id: string | null) {
  return useQuery<{ investigationId: string; regions: FinalRegion[] }>({
    queryKey: ['investigation-regions', id],
    queryFn: () => apiClient.get(`/v1/investigations/${id}/regions`),
    enabled: !!id,
  });
}

export function useInvestigationSeal(id: string | null) {
  return useQuery<SealedRecord | { status: string }>({
    queryKey: ['investigation-seal', id],
    queryFn: () => apiClient.get(`/v1/investigations/${id}/seal`),
    enabled: !!id,
  });
}

export function useCreateInvestigation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (comparisonId: string) =>
      apiClient.post<{ investigationId: string; status: string }>('/v1/investigations', { comparisonId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['investigations'] }),
  });
}

export function useSealInvestigation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.post(`/v1/investigations/${id}/seal`),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['investigation', id] });
      qc.invalidateQueries({ queryKey: ['investigation-seal', id] });
    },
  });
}
