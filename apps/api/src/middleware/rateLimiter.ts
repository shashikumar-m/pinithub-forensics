/**
 * Rate limiter middleware using express-rate-limit.
 */
import rateLimit from 'express-rate-limit';
import { getEnv } from '../config/env.js';
import { ErrorCode } from '@pinithub/shared';

export function rateLimiter() {
  const env = getEnv();
  return rateLimit({
    windowMs: env.RATE_LIMIT_WINDOW_MS,
    max: env.RATE_LIMIT_MAX,
    standardHeaders: true,
    legacyHeaders: false,
    // Skip rate limiting for health checks
    skip: (req) => req.path.startsWith('/v1/health') || req.path.startsWith('/v1/ready'),
    handler: (_req, res) => {
      res.status(429).json({
        error: {
          code: ErrorCode.RATE_LIMITED,
          message: 'Too many requests, please try again later',
        },
      });
    },
  });
}
