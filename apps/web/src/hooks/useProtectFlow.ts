/**
 * useProtectFlow — state machine for the full protect workflow.
 *
 * States:
 *   CONSENT_REQUIRED → SELECTING_SOURCE → CAPTURING / UPLOADING
 *   → PROTECTING → PROTECTED / FAILED
 *
 * Both camera capture and file upload feed into the same backend pipeline.
 */
import { useState, useCallback } from 'react';
import { apiClient, ApiRequestError } from '../api/client';
import type { ImageRecord, ImageSource } from '@pinithub/shared';

export type FlowStep =
  | 'CONSENT_REQUIRED'
  | 'SELECTING_SOURCE'
  | 'CAPTURING'
  | 'UPLOADING'
  | 'PROTECTING'
  | 'QUEUED'
  | 'PROTECTED'
  | 'FAILED';

export interface ProtectResult {
  image: ImageRecord;
  analysisId?: string;
  duplicate: boolean;
  existingImageId?: string;
}

export interface ProtectError {
  code: string;
  message: string;
}

export const CONSENT_VERSION = '1.0';
export const POLICY_VERSION = '2024-11';

export function useProtectFlow() {
  const [step, setStep] = useState<FlowStep>('CONSENT_REQUIRED');
  const [error, setError] = useState<ProtectError | null>(null);
  const [result, setResult] = useState<ProtectResult | null>(null);
  const [consentId, setConsentId] = useState<string | null>(null);

  const recordConsent = useCallback(async (sourceType: ImageSource) => {
    try {
      const res = await apiClient.post<{ consent: { id: string } }>('/v1/consents', {
        sourceType,
        consentVersion: CONSENT_VERSION,
        policyVersion: POLICY_VERSION,
      });
      setConsentId(res.consent.id);
    } catch {
      // Consent recording failure is non-fatal in Phase 1 (auth comes later)
      // Log it but don't block the flow
    }
  }, []);

  const handleConsent = useCallback(
    async (sourceType: ImageSource) => {
      await recordConsent(sourceType);
      if (sourceType === 'CAMERA_CAPTURE') {
        setStep('CAPTURING');
      } else {
        setStep('UPLOADING');
      }
    },
    [recordConsent],
  );

  /** Called with the final image file (from camera or file picker). */
  const protect = useCallback(
    async (file: File, source: ImageSource, captureTimestamp?: string) => {
      setError(null);
      setStep('PROTECTING');

      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source', source);
        formData.append('role', 'ORIGINAL');
        if (captureTimestamp) {
          formData.append('captureTimestamp', captureTimestamp);
        }
        if (consentId) {
          formData.append('consentId', consentId);
        }

        const res = await apiClient.post<{
          image: ImageRecord;
          analysisId?: string;
          duplicate: boolean;
          existingImageId?: string;
          forensics?: any;
          metadata?: any;
        }>('/v1/uploads', formData);

        setResult({
          image: res.image,
          analysisId: res.analysisId,
          duplicate: res.duplicate,
          existingImageId: res.existingImageId,
          forensics: res.forensics,
          metadata: res.metadata,
        } as any);
        setStep('PROTECTED');
      } catch (err) {
        const code = err instanceof ApiRequestError ? err.code : 'UNKNOWN_ERROR';
        const message =
          err instanceof ApiRequestError
            ? err.message
            : 'An unexpected error occurred. Please try again.';

        setError({ code, message });
        setStep('FAILED');
      }
    },
    [consentId],
  );

  const reset = useCallback(() => {
    setStep('CONSENT_REQUIRED');
    setError(null);
    setResult(null);
    setConsentId(null);
  }, []);

  const goToSourceSelect = useCallback(() => setStep('SELECTING_SOURCE'), []);

  return {
    step,
    error,
    result,
    handleConsent,
    protect,
    reset,
    goToSourceSelect,
  };
}
