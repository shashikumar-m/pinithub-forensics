/**
 * Health and readiness endpoints.
 *
 * GET /v1/health  — lightweight liveness check (no dependency calls)
 * GET /v1/ready   — readiness check that probes database, storage, and
 *                   the Python forensic service
 */
import { Router } from 'express';
import { checkDatabase } from '../config/prisma.js';
import { isStorageConfigured } from '../config/storage.js';
import { getEnv } from '../config/env.js';
import { getLogger } from '../config/logger.js';
import type { HealthResponse, ReadyResponse } from '@pinithub/shared';

export const healthRouter = Router();

healthRouter.get('/health', (_req, res) => {
  const response: HealthResponse = {
    status: 'ok',
    service: 'pinithub-api',
    version: '0.1.0',
    timestamp: new Date().toISOString(),
  };
  res.json(response);
});

healthRouter.get('/ready', async (_req, res) => {
  const env = getEnv();
  const log = getLogger();

  // Check database
  let database: 'ok' | 'fail' | 'skipped' = 'fail';
  try {
    const ok = await checkDatabase();
    database = ok ? 'ok' : 'fail';
  } catch {
    database = 'fail';
  }

  // Check storage configuration (just config presence, not a live call)
  const storage: 'ok' | 'fail' | 'skipped' = isStorageConfigured() ? 'ok' : 'skipped';

  // Check forensics service
  let forensics: 'ok' | 'fail' | 'skipped' = 'fail';
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/health`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    forensics = resp.ok ? 'ok' : 'fail';
  } catch {
    forensics = 'fail';
    log.debug('Forensics service not reachable');
  }

  const response: ReadyResponse = {
    status: database === 'ok' ? 'ok' : 'degraded',
    service: 'pinithub-api',
    checks: { database, storage, forensics },
    timestamp: new Date().toISOString(),
  };

  const httpStatus = database === 'ok' ? 200 : 503;
  res.status(httpStatus).json(response);
});
