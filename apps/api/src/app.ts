/**
 * Express application factory.
 *
 * Wires up security middleware, request logging, CORS, rate limiting,
 * routes, and the centralized error handler. Exports a factory function
 * so tests can create isolated app instances.
 */
import express, { type Application } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import compression from 'compression';
import { getCorsOrigins } from './config/env.js';
import { requestLogger } from './middleware/requestLogger.js';
import { rateLimiter } from './middleware/rateLimiter.js';
import { errorHandler } from './middleware/errorHandler.js';
import { ownerContext } from './middleware/owner.js';
import { healthRouter } from './routes/health.js';
import { uploadsRouter } from './routes/uploads.js';
import { analysesRouter } from './routes/analyses.js';
import { modelsRouter } from './routes/models.js';
import { consentsRouter } from './routes/consents.js';
import { imagesRouter } from './routes/images.js';
import { comparisonsRouter } from './routes/comparisons.js';
import { aiDetectionRouter } from './routes/ai_detection.js';
import { travelRouter } from './routes/travel.js';
import { investigationsRouter } from './routes/investigations.js';
import { jobsRouter } from './routes/jobs.js';
import { ErrorCode } from '@pinithub/shared';

export function createApp(): Application {
  const app = express();

  // ---- Trust proxy (behind reverse proxy / load balancer) ----
  app.set('trust proxy', 1);

  // ---- Security middleware ----
  app.use(helmet());
  app.use(
    cors({
      origin: (origin, callback) => {
        if (!origin) return callback(null, true);
        const configured = getCorsOrigins();
        if (
          configured.includes('*') ||
          configured.includes(origin) ||
          origin.endsWith('.trycloudflare.com') ||
          origin.includes('localhost') ||
          origin.includes('127.0.0.1')
        ) {
          return callback(null, true);
        }
        return callback(null, false);
      },
      credentials: false,
    }),
  );

  // ---- Compression ----
  app.use(compression());

  // ---- Request logging (before body parsing) ----
  app.use(requestLogger());

  // ---- Rate limiting ----
  app.use(rateLimiter());

  // ---- Body parsing ----
  app.use(express.json({ limit: '50mb' }));
  app.use(express.urlencoded({ extended: true, limit: '50mb' }));

  // ---- Routes ----
  app.use('/v1', healthRouter);
  app.use('/v1/consents', ownerContext, consentsRouter);
  app.use('/v1/uploads', ownerContext, uploadsRouter);
  app.use('/v1/images', ownerContext, imagesRouter);
  app.use('/v1/comparisons', ownerContext, comparisonsRouter);
  app.use('/v1/analyses', ownerContext, analysesRouter);
  app.use('/v1/analyses', ownerContext, aiDetectionRouter);
  app.use('/v1/comparisons', ownerContext, travelRouter);
  app.use('/v1/investigations', ownerContext, investigationsRouter);
  app.use('/v1/jobs', jobsRouter);
  app.use('/v1/models', modelsRouter);

  // ---- 404 handler ----
  app.use((_req, res) => {
    res.status(404).json({
      error: {
        code: ErrorCode.NOT_FOUND,
        message: 'Route not found',
      },
    });
  });

  // ---- Centralized error handler (must be last) ----
  app.use(errorHandler);

  return app;
}
