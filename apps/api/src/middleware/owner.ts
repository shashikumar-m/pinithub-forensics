/**
 * Owner context middleware.
 *
 * Phase 0 does not implement full authentication. Instead, it resolves
 * the "owner" from an X-Owner-Id header or falls back to a default
 * development user that is auto-created on first request.
 *
 * This keeps all resources owner-scoped (the security principle) while
 * deferring real auth to a later phase.
 */
import type { Request, Response, NextFunction } from 'express';
import { getPrisma } from '../config/prisma.js';
import { getLogger } from '../config/logger.js';
import { isTest } from '../config/env.js';
import { unauthorized } from '../errors.js';

const DEFAULT_DEV_USER_EMAIL = 'dev@pinithub.local';

/**
 * Fallback owner UUID used when the database is unreachable in
 * test/development mode. This lets validation and routing proceed
 * even without a database connection.
 */
const FALLBACK_OWNER_ID = '00000000-0000-0000-0000-000000000001';

/**
 * Ensures a default development user exists and returns its ID.
 * Caches the ID in-memory after the first lookup.
 */
let cachedDefaultUserId: string | null = null;

async function getOrCreateDefaultUser(): Promise<string | null> {
  if (cachedDefaultUserId) return cachedDefaultUserId;

  const prisma = getPrisma();
  const log = getLogger();

  try {
    let user = await prisma.user.findUnique({ where: { email: DEFAULT_DEV_USER_EMAIL } });
    if (!user) {
      user = await prisma.user.create({
        data: { email: DEFAULT_DEV_USER_EMAIL, name: 'Development User' },
      });
      log.info({ userId: user.id }, 'Created default development user');
    }
    cachedDefaultUserId = user.id;
    return cachedDefaultUserId;
  } catch (err) {
    log.error({ err }, 'Failed to create/find default dev user — check DB schema (run: npx prisma db push)');
    return null;
  }
}

/**
 * Attaches ownerId to the request object.
 * In production, this would validate a JWT/session.
 */
export async function ownerContext(req: Request, _res: Response, next: NextFunction) {
  const log = getLogger();

  const headerOwner = req.headers['x-owner-id'] as string | undefined;

  if (headerOwner) {
    try {
      const prisma = getPrisma();
      const user = await prisma.user.findUnique({ where: { id: headerOwner } });
      if (!user) {
        return next(unauthorized('Invalid owner identifier'));
      }
      (req as any).ownerId = headerOwner;
      return next();
    } catch {
      // Database unavailable — in test/dev, accept the header as-is
      if (isTest()) {
        (req as any).ownerId = headerOwner;
        return next();
      }
      log.error('Failed to verify owner header');
      return next(unauthorized('Unable to verify owner identifier'));
    }
  }

  // Development fallback — use the default dev user
  try {
    const devUserId = await getOrCreateDefaultUser();
    if (devUserId) {
      (req as any).ownerId = devUserId;
      return next();
    }
    // User creation failed — use stable fallback UUID in development
    log.warn('Using fallback dev owner ID (check DB schema)');
    (req as any).ownerId = FALLBACK_OWNER_ID;
    return next();
  } catch (err) {
    if (isTest()) {
      (req as any).ownerId = FALLBACK_OWNER_ID;
      return next();
    }
    log.error({ err }, 'Failed to resolve owner context');
    next(unauthorized('Unable to resolve owner context'));
  }
}

/**
 * Helper to extract ownerId from a request.
 */
export function getOwnerId(req: Request): string {
  return (req as any).ownerId as string;
}
