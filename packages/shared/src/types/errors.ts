/**
 * Standard API error shape used across the Node API.
 * Every error response follows this structure so the frontend
 * can parse failures consistently.
 */
export interface ApiError {
  error: {
    /** Machine-readable error code, e.g. VALIDATION_ERROR, NOT_FOUND */
    code: string;
    /** Human-readable message safe to display to end users */
    message: string;
    /** Optional field-level validation details */
    details?: Record<string, unknown>;
  };
}

/** Well-known error codes used across the platform. */
export const ErrorCode = {
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  CONFLICT: 'CONFLICT',
  RATE_LIMITED: 'RATE_LIMITED',
  PAYLOAD_TOO_LARGE: 'PAYLOAD_TOO_LARGE',
  UNSUPPORTED_MEDIA_TYPE: 'UNSUPPORTED_MEDIA_TYPE',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  NOT_IMPLEMENTED: 'NOT_IMPLEMENTED',
  BAD_GATEWAY: 'BAD_GATEWAY',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
} as const;

export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];
