/**
 * Jest setup — provides required environment variables for tests.
 * This runs before any test file so getEnv() succeeds.
 */

// Set test environment variables before importing anything that calls getEnv()
process.env.NODE_ENV = 'test';
process.env.PORT = '4000';
process.env.DATABASE_URL = process.env.TEST_DATABASE_URL || 'postgresql://test:test@localhost:5432/test';
process.env.DIRECT_URL = process.env.TEST_DATABASE_URL || 'postgresql://test:test@localhost:5432/test';
process.env.LOG_LEVEL = 'error';
process.env.CORS_ORIGINS = 'http://localhost:5173';
process.env.FORENSICS_SERVICE_URL = 'http://localhost:8001';

// Supabase keys are optional — do not set them so validation treats them
// as undefined (acceptable). Never set real secrets in test config.
delete process.env.SUPABASE_URL;
delete process.env.SUPABASE_ANON_KEY;
delete process.env.SUPABASE_SERVICE_ROLE_KEY;
