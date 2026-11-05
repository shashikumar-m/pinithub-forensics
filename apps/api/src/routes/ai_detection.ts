/**
 * AI Detection routes — Phase 6.
 *
 * POST /v1/analyses/:id/ai-detection        — trigger AI detection
 * GET  /v1/analyses/:id/ai-detection        — get result
 * GET  /v1/analyses/:id/ai-detection/regions — candidate AI regions
 * GET  /v1/analyses/:id/ai-detection/heatmap — heatmap artifact info
 *
 * All routes enforce owner isolation.
 * Results are experimental. UNAVAILABLE status is shown when
 * model weights are not trained yet.
 *
 * IMPORTANT: AI detection is UNCALIBRATED.
 * Do not expose model weights hash or private artifacts directly.
 */
import { Router } from 'express';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { uuidParamSchema } from '../schemas/index.js';
import { getPrisma } from '../config/prisma.js';
import { getEnv } from '../config/env.js';
import { getLogger } from '../config/logger.js';
import { notFound } from '../errors.js';

export const aiDetectionRouter = Router();

// ---- POST /v1/analyses/:id/ai-detection ----
aiDetectionRouter.post(
  '/:id/ai-detection',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const log = getLogger();
      const env = getEnv();

      // Verify analysis ownership
      const analysis = await prisma.analysis.findFirst({
        where: { id: req.params.id, ownerId },
        include: { image: true },
      });
      if (!analysis) return next(notFound('Analysis not found'));

      // Create / reset result record
      const existing = await prisma.aIDetectionResult.findUnique({
        where: { analysisId: req.params.id },
      });

      const record = existing
        ? await prisma.aIDetectionResult.update({
            where: { analysisId: req.params.id },
            data: { status: 'QUEUED', error: null },
          })
        : await prisma.aIDetectionResult.create({
            data: {
              analysisId: req.params.id,
              status: 'QUEUED',
              calibrationStatus: 'UNCALIBRATED',
            },
          });

      // Fire-and-forget pipeline
      setImmediate(async () => {
        try {
          // Load image from local storage
          const path = await import('node:path');
          const fs = await import('node:fs/promises');
          const localRoot = path.resolve(process.cwd(), '.local-storage');
          const imgPath = path.join(localRoot, 'originals', analysis.image.storagePath);

          let imgBuf: Buffer;
          try {
            imgBuf = await fs.readFile(imgPath);
          } catch {
            await prisma.aIDetectionResult.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: 'Could not load image file' },
            });
            return;
          }

          await prisma.aIDetectionResult.update({
            where: { id: record.id },
            data: { status: 'RUNNING' },
          });

          // Call Python service
          const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/ai-detect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_hex: imgBuf.toString('hex') }),
            signal: AbortSignal.timeout(120_000),
          });

          if (!resp.ok) {
            const err = await resp.text().catch(() => 'unknown');
            await prisma.aIDetectionResult.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: `Forensics service: ${err}` },
            });
            return;
          }

          const result: any = await resp.json();
          const det = result.details ?? result;

          await prisma.aIDetectionResult.update({
            where: { id: record.id },
            data: {
              status: det.status ?? 'FAILED',
              imageLevelScore: det.image_level_score ?? null,
              imageLevelLabel: det.image_level_label ?? null,
              editedAreaPct: det.edited_area_percentage ?? null,
              modelName: det.model ?? 'ai_detector',
              modelVersion: det.version ?? 'v1.0.0',
              calibrationStatus: det.calibration_status ?? 'UNCALIBRATED',
              regions: det.regions ?? null,
              evidence: det.evidence ?? null,
              warnings: det.warnings ?? null,
              executionMs: det.execution_ms ?? null,
              error: det.error ?? null,
            },
          });

          await prisma.auditEvent.create({
            data: {
              eventType: det.status === 'UNAVAILABLE' ? 'AI_DETECTION_FAILED' : 'AI_DETECTION_COMPLETED',
              actorId: ownerId,
              resourceId: req.params.id,
              resourceType: 'analysis',
              payload: { status: det.status, model: det.model },
            },
          });

          log.info({ analysisId: req.params.id, status: det.status }, 'AI detection completed');
        } catch (err) {
          log.error({ err }, 'AI detection pipeline failed');
          try {
            await prisma.aIDetectionResult.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: err instanceof Error ? err.message : String(err) },
            });
          } catch { /* ignore */ }
        }
      });

      res.status(202).json({
        analysisId: req.params.id,
        aiDetectionId: record.id,
        status: 'QUEUED',
        message: 'AI detection initiated. Poll GET /v1/analyses/:id/ai-detection for results.',
        note: 'AI detection is experimental (UNCALIBRATED). Results require trained model weights.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/analyses/:id/ai-detection ----
aiDetectionRouter.get(
  '/:id/ai-detection',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const analysis = await prisma.analysis.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!analysis) return next(notFound('Analysis not found'));

      const record = await prisma.aIDetectionResult.findUnique({
        where: { analysisId: req.params.id },
      });

      if (!record) {
        return res.status(202).json({
          status: 'NOT_RUN',
          message: 'AI detection has not been triggered.',
          analysisId: req.params.id,
        });
      }

      res.json({
        analysisId: req.params.id,
        aiDetection: serializeAIResult(record),
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/analyses/:id/ai-detection/regions ----
aiDetectionRouter.get(
  '/:id/ai-detection/regions',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const analysis = await prisma.analysis.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!analysis) return next(notFound('Analysis not found'));

      const record = await prisma.aIDetectionResult.findUnique({
        where: { analysisId: req.params.id },
        select: { status: true, regions: true, editedAreaPct: true },
      });

      if (!record) {
        return res.status(202).json({ status: 'NOT_RUN', regions: [] });
      }

      res.json({
        analysisId: req.params.id,
        status: record.status,
        regions: record.regions ?? [],
        editedAreaPct: record.editedAreaPct,
        note: 'Candidate AI-edited regions (experimental, UNCALIBRATED).',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/analyses/:id/ai-detection/heatmap ----
aiDetectionRouter.get(
  '/:id/ai-detection/heatmap',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const analysis = await prisma.analysis.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!analysis) return next(notFound('Analysis not found'));

      const record = await prisma.aIDetectionResult.findUnique({
        where: { analysisId: req.params.id },
        select: { heatmapStoragePath: true, maskStoragePath: true, status: true },
      });

      if (!record || !record.heatmapStoragePath) {
        return res.status(202).json({
          status: record?.status ?? 'NOT_RUN',
          message: 'Heatmap not available. AI detection must be run first.',
        });
      }

      // In production: generate a signed URL
      res.json({
        analysisId: req.params.id,
        heatmapStoragePath: record.heatmapStoragePath,
        maskStoragePath: record.maskStoragePath,
        note: 'Use signed URL generation to access these artifacts.',
      });
    } catch (err) {
      next(err);
    }
  },
);

function serializeAIResult(r: any) {
  return {
    id: r.id,
    analysisId: r.analysisId,
    status: r.status,
    imageLevelScore: r.imageLevelScore,
    imageLevelLabel: r.imageLevelLabel,
    editedAreaPct: r.editedAreaPct,
    modelName: r.modelName,
    modelVersion: r.modelVersion,
    calibrationStatus: r.calibrationStatus,
    regions: r.regions,
    evidence: r.evidence,
    warnings: r.warnings,
    executionMs: r.executionMs,
    error: r.error,
    createdAt: r.createdAt?.toISOString(),
    note: 'AI detection is experimental and UNCALIBRATED. Results are not a definitive verdict.',
  };
}
