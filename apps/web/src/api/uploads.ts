/**
 * TanStack Query hooks for upload endpoints.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { ImageRole, UploadImageResponse } from '@pinithub/shared';

export function useUploadImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { file: File; role: ImageRole }) => {
      const formData = new FormData();
      formData.append('file', vars.file);
      formData.append('role', vars.role);
      return apiClient.post<UploadImageResponse>('/v1/uploads', formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analyses'] });
    },
  });
}
