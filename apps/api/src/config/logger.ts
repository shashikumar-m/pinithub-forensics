/**
 * Pino structured logger configuration.
 *
 * Redaction rules strip sensitive fields from logs so secrets,
 * passwords, API keys, service-role keys, and full image payloads
 * are never written to log output.
 */
import pino from 'pino';
import { getEnv } from './env.js';

const redactPaths = [
  // Credentials / secrets
  'req.headers.authorization',
  'req.headers.cookie',
  'req.headers["x-api-key"]',
  '*.password',
  '*.apiKey',
  '*.api_key',
  '*.serviceRoleKey',
  '*.service_role_key',
  '*.anonKey',
  '*.anon_key',
  '*.SUPABASE_SERVICE_ROLE_KEY',
  '*.secret',
  '*.token',
  // Sensitive image data
  '*.imageData',
  '*.buffer',
  'file.buffer',
  // GPS / location privacy
  '*.gps',
  '*.exif.GPSLatitude',
  '*.exif.GPSLongitude',
  '*.exif.GPSInfo',
];

export function createLogger(name = 'pinithub-api') {
  const env = getEnv();
  return pino({
    name,
    level: env.LOG_LEVEL,
    redact: {
      paths: redactPaths,
      censor: '[REDACTED]',
    },
    transport:
      env.NODE_ENV === 'development'
        ? { target: 'pino-pretty', options: { colorize: true, translateTime: 'SYS:standard' } }
        : undefined,
  });
}

export type Logger = ReturnType<typeof createLogger>;

// Singleton logger instance
let loggerInstance: Logger | null = null;

export function getLogger(): Logger {
  if (!loggerInstance) {
    loggerInstance = createLogger();
  }
  return loggerInstance;
}
