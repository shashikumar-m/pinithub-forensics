/**
 * Request logging middleware using pino-http.
 * Each request gets a child logger with a unique request ID.
 */
import pinoHttp from 'pino-http';
import { getLogger } from '../config/logger.js';

export function requestLogger() {
  return pinoHttp({
    logger: getLogger(),
    // Only log non-health-check requests at info, health checks at debug
    customLogLevel: (_req, res, err) => {
      if (err || res.statusCode >= 500) return 'error';
      if (res.statusCode >= 400) return 'warn';
      const url = (res.req?.url) ?? '';
      if (url.startsWith('/v1/health') || url.startsWith('/v1/ready')) {
        return 'debug';
      }
      return 'info';
    },
    // Redact sensitive paths from log output
    serializers: {
      req: (req: any) => ({
        id: req.id,
        method: req.method,
        url: req.url,
        // Intentionally do not include headers or body
      }),
      res: (res: any) => ({
        statusCode: res.statusCode,
      }),
    },
  });
}
