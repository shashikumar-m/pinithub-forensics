/**
 * TanStack Query hooks for image endpoints (Phase 2).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ImageRecord, ImageMetadataRecord, ImageCharacteristicsRecord } from '@pinithub/shared';

export interface ImageListResponse {
  items: ImageRecord[];
  total: number;
  page: number;
  pageSize: number;
}

export function useImages(page = 1, pageSize = 20) {
  return useQuery<ImageListResponse>({
    queryKey: ['images', page, pageSize],
    queryFn: () => apiClient.get(`/v1/images?page=${page}&pageSize=${pageSize}`),
  });
}

export function useDeleteImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/v1/images/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['images'] }),
  });
}

export function useImage(id: string | null) {
  return useQuery<{ image: ImageRecord & { metadata?: ImageMetadataRecord; characteristics?: ImageCharacteristicsRecord } }>({
    queryKey: ['image', id],
    queryFn: () => apiClient.get(`/v1/images/${id}`),
    enabled: !!id,
  });
}

export function useImageMetadata(imageId: string | null) {
  return useQuery<{ metadata: ImageMetadataRecord } | { status: string; message: string }>({
    queryKey: ['image-metadata', imageId],
    queryFn: () => apiClient.get(`/v1/images/${imageId}/metadata`),
    enabled: !!imageId,
    // 202 Not-Extracted is a valid response, not an error
    retry: false,
  });
}

export function useImageEvidence(imageId: string | null) {
  return useQuery<{ imageId: string; items: any[]; total: number; note: string }>({
    queryKey: ['image-evidence', imageId],
    queryFn: () => apiClient.get(`/v1/images/${imageId}/evidence`),
    enabled: !!imageId,
  });
}

export function useImageIntegrity(imageId: string | null) {
  return useQuery<{ imageId: string; storedHash: string; checks: any[] }>({
    queryKey: ['image-integrity', imageId],
    queryFn: () => apiClient.get(`/v1/images/${imageId}/integrity`),
    enabled: !!imageId,
  });
}
