/**
 * Custom HTTP error classes and helpers.
 *
 * Every operational error thrown in route/service code should be an
 * instance of HttpError so the centralized error handler can map it
 * to the standard { error: { code, message } } response shape.
 */
import { ErrorCode, type ErrorCodeValue } from '@pinithub/shared';

export class HttpError extends Error {
  public readonly statusCode: number;
  public readonly code: ErrorCodeValue;
  public readonly details?: Record<string, unknown>;

  constructor(
    statusCode: number,
    code: ErrorCodeValue,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'HttpError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

export function badRequest(message: string, details?: Record<string, unknown>): HttpError {
  return new HttpError(400, ErrorCode.VALIDATION_ERROR, message, details);
}

export function unauthorized(message = 'Authentication required'): HttpError {
  return new HttpError(401, ErrorCode.UNAUTHORIZED, message);
}

export function forbidden(message = 'Access denied'): HttpError {
  return new HttpError(403, ErrorCode.FORBIDDEN, message);
}

export function notFound(message = 'Resource not found'): HttpError {
  return new HttpError(404, ErrorCode.NOT_FOUND, message);
}

export function conflict(message: string, details?: Record<string, unknown>): HttpError {
  return new HttpError(409, ErrorCode.CONFLICT, message, details);
}

export function payloadTooLarge(message = 'Upload exceeds maximum allowed size'): HttpError {
  return new HttpError(413, ErrorCode.PAYLOAD_TOO_LARGE, message);
}

export function unsupportedMediaType(message = 'Unsupported media type'): HttpError {
  return new HttpError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE, message);
}

export function notImplemented(message = 'This feature is not yet implemented'): HttpError {
  return new HttpError(501, ErrorCode.NOT_IMPLEMENTED, message);
}

export function serviceUnavailable(message = 'Dependent service unavailable'): HttpError {
  return new HttpError(503, ErrorCode.SERVICE_UNAVAILABLE, message);
}

export function internal(message = 'Internal server error'): HttpError {
  return new HttpError(500, ErrorCode.INTERNAL_ERROR, message);
}
