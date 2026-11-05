/**
 * API client — thin fetch wrapper for the Node API.
 *
 * All responses are typed against @pinithub/shared contracts.
 * The API URL is configurable via VITE_API_URL, defaulting to same-origin
 * so the Vite dev proxy forwards /v1 requests to the API.
 */
import type { ApiError } from '@pinithub/shared';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {};

  // Merge existing headers (RequestInit.headers can be various types)
  if (options.headers) {
    const incoming = options.headers as Record<string, string>;
    for (const [key, value] of Object.entries(incoming)) {
      headers[key] = value;
    }
  }

  // Don't set Content-Type for FormData (browser sets boundary)
  if (!(options.body instanceof FormData) && options.body) {
    headers['Content-Type'] = 'application/json';
  }

  // X-Owner-Id — Phase 0 uses a header for owner context
  if (typeof localStorage !== 'undefined') {
    const ownerId = localStorage.getItem('pinithub-owner-id');
    if (ownerId) headers['X-Owner-Id'] = ownerId;
  }

  const res = await fetch(url, { ...options, headers });

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const error = data as ApiError | null;
    throw new ApiRequestError(
      res.status,
      error?.error?.code ?? 'UNKNOWN',
      error?.error?.message ?? `Request failed with status ${res.status}`,
    );
  }

  return data as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
