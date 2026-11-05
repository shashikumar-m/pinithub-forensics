/**
 * Centralized error handler — converts all errors into the standard
 * { error: { code, message } } JSON response shape.
 */
import type { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';
import { HttpError } from '../errors.js';
import { ErrorCode } from '@pinithub/shared';
import { getLogger } from '../config/logger.js';

export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  const log = getLogger();

  // Zod validation errors
  if (err instanceof ZodError) {
    const details: Record<string, unknown> = {};
    for (const issue of err.issues) {
      const key = issue.path.join('.') || 'value';
      details[key] = issue.message;
    }
    log.warn({ msg: 'Validation error', details });
    res.status(400).json({
      error: {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Request validation failed',
        details,
      },
    });
    return;
  }

  // Known HTTP errors
  if (err instanceof HttpError) {
    if (err.statusCode >= 500) {
      log.error({ err }, 'Server error');
    } else {
      log.warn({ code: err.code, msg: err.message });
    }
    res.status(err.statusCode).json({
      error: {
        code: err.code,
        message: err.message,
        ...(err.details ? { details: err.details } : {}),
      },
    });
    return;
  }

  // Multer file-size errors
  if (isMulterError(err) && (err as { code?: string }).code === 'LIMIT_FILE_SIZE') {
    log.warn({ msg: 'Upload too large' });
    res.status(413).json({
      error: {
        code: ErrorCode.PAYLOAD_TOO_LARGE,
        message: 'Upload exceeds maximum allowed size',
      },
    });
    return;
  }

  // Unknown errors — expose in development, hide in production
  log.error({ err }, 'Unhandled error');
  const isDev = process.env.NODE_ENV === 'development';
  const message = isDev
    ? (err instanceof Error ? `${err.message}\n${err.stack}` : String(err))
    : 'Internal server error';
  res.status(500).json({
    error: {
      code: ErrorCode.INTERNAL_ERROR,
      message,
    },
  });
}

function isMulterError(err: unknown): boolean {
  return err instanceof Error && err.name === 'MulterError';
}
