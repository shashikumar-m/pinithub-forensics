/**
 * Environment configuration with validation at startup.
 *
 * Required variables are validated eagerly so the server fails fast
 * with a clear message if configuration is missing.
 */
import { z } from 'zod';

const envSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(4000),

  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required'),
  DIRECT_URL: z.string().min(1, 'DIRECT_URL is required'),

  SUPABASE_URL: z.string().url().optional(),
  SUPABASE_ANON_KEY: z.string().optional(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().optional(),

  SUPABASE_STORAGE_BUCKET_ORIGINALS: z.string().default('originals'),
  SUPABASE_STORAGE_BUCKET_ARTIFACTS: z.string().default('artifacts'),
  SUPABASE_STORAGE_BUCKET_DATASETS: z.string().default('datasets'),
  SUPABASE_STORAGE_BUCKET_MODELS: z.string().default('models'),

  FORENSICS_SERVICE_URL: z.string().default('http://localhost:8001').transform((val) => val.startsWith('http') ? val : `https://${val}`),

  MAX_UPLOAD_MB: z.coerce.number().int().min(1).max(500).default(25),
  MAX_IMAGE_UPLOAD_BYTES: z.coerce.number().int().min(1024).max(500 * 1024 * 1024).default(25 * 1024 * 1024),
  CORS_ORIGINS: z.string().default('http://localhost:5173'),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().min(1000).default(900000),
  RATE_LIMIT_MAX: z.coerce.number().int().min(1).default(100),

  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
});

export type Env = z.infer<typeof envSchema>;

let cachedEnv: Env | null = null;

/**
 * Validates and returns the runtime environment configuration.
 * Throws on first call if required variables are missing.
 */
export function getEnv(): Env {
  if (cachedEnv && process.env.NODE_ENV !== 'test') return cachedEnv;

  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const issues = result.error.issues
      .map((i) => `  - ${i.path.join('.')}: ${i.message}`)
      .join('\n');
    throw new Error(`Environment validation failed:\n${issues}`);
  }

  cachedEnv = result.data;
  return cachedEnv;
}

/**
 * Returns the CORS allowed origins as an array.
 */
export function getCorsOrigins(): string[] {
  const env = getEnv();
  return env.CORS_ORIGINS.split(',')
    .map((o) => o.trim())
    .filter(Boolean);
}

/**
 * Whether we are running in production.
 */
export function isProduction(): boolean {
  return getEnv().NODE_ENV === 'production';
}

/**
 * Whether we are running tests.
 */
export function isTest(): boolean {
  return getEnv().NODE_ENV === 'test';
}
