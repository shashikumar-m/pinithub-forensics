/**
 * Storage configuration — Supabase Storage bucket names.
 *
 * The Node API uses the service-role key (server-side only) to interact
 * with private buckets. The frontend never receives the service-role key.
 * Signed URLs are generated server-side when the frontend needs access.
 */
import { getEnv } from './env.js';

export interface StorageConfig {
  url: string | null;
  serviceRoleKey: string | null;
  anonKey: string | null;
  buckets: {
    originals: string;
    artifacts: string;
    datasets: string;
    models: string;
  };
}

export function getStorageConfig(): StorageConfig {
  const env = getEnv();
  return {
    url: env.SUPABASE_URL ?? null,
    serviceRoleKey: env.SUPABASE_SERVICE_ROLE_KEY ?? null,
    anonKey: env.SUPABASE_ANON_KEY ?? null,
    buckets: {
      originals: env.SUPABASE_STORAGE_BUCKET_ORIGINALS,
      artifacts: env.SUPABASE_STORAGE_BUCKET_ARTIFACTS,
      datasets: env.SUPABASE_STORAGE_BUCKET_DATASETS,
      models: env.SUPABASE_STORAGE_BUCKET_MODELS,
    },
  };
}

/**
 * Whether Supabase storage is configured. If not, storage operations
 * will be skipped and endpoints should report storage as unavailable.
 */
export function isStorageConfigured(): boolean {
  const cfg = getStorageConfig();
  return cfg.url !== null && cfg.serviceRoleKey !== null;
}
