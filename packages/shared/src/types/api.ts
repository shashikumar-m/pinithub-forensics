/**
 * Generic API envelope types shared between frontend and backend.
 */

/** Success envelope wrapper for list endpoints. */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** Health check response. */
export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  timestamp: string;
}

/** Readiness check response (includes dependency checks). */
export interface ReadyResponse {
  status: 'ok' | 'degraded';
  service: string;
  checks: {
    database: 'ok' | 'fail' | 'skipped';
    storage: 'ok' | 'fail' | 'skipped';
    forensics: 'ok' | 'fail' | 'skipped';
  };
  timestamp: string;
}
