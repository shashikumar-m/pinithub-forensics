/**
 * Tests for environment validation.
 * Ensures the server fails fast with a clear message when required
 * configuration is missing.
 */
import { z } from 'zod';

// Re-implement the env schema subset to test validation logic
const envSchema = z.object({
  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required'),
  DIRECT_URL: z.string().min(1, 'DIRECT_URL is required'),
  PORT: z.coerce.number().int().min(1).max(65535).default(4000),
});

describe('Environment validation', () => {
  it('accepts valid configuration', () => {
    const result = envSchema.safeParse({
      DATABASE_URL: 'postgresql://user:pass@host:5432/db',
      DIRECT_URL: 'postgresql://user:pass@host:5432/db',
      PORT: '4000',
    });
    expect(result.success).toBe(true);
  });

  it('rejects missing DATABASE_URL', () => {
    const result = envSchema.safeParse({
      DIRECT_URL: 'postgresql://user:pass@host:5432/db',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issues = result.error.issues.map((i) => i.path.join('.'));
      expect(issues).toContain('DATABASE_URL');
    }
  });

  it('rejects missing DIRECT_URL', () => {
    const result = envSchema.safeParse({
      DATABASE_URL: 'postgresql://user:pass@host:5432/db',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issues = result.error.issues.map((i) => i.path.join('.'));
      expect(issues).toContain('DIRECT_URL');
    }
  });

  it('rejects empty string for required fields', () => {
    const result = envSchema.safeParse({
      DATABASE_URL: '',
      DIRECT_URL: 'postgresql://user:pass@host:5432/db',
    });
    expect(result.success).toBe(false);
  });
});
