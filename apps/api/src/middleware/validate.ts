/**
 * Validation middleware factory using Zod schemas.
 * Validates the specified part of the request (body, query, params).
 */
import type { Request, Response, NextFunction } from 'express';
import { type ZodSchema } from 'zod';

type RequestPart = 'body' | 'query' | 'params';

export function validate(schema: ZodSchema, part: RequestPart = 'body') {
  return (req: Request, _res: Response, next: NextFunction) => {
    const data = req[part];
    const result = schema.safeParse(data);
    if (!result.success) {
      // Re-throw as ZodError so errorHandler can handle it uniformly
      throw result.error;
    }
    // Replace with parsed/transformed data
    req[part] = result.data;
    next();
  };
}
