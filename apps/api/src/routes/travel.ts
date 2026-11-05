/**
 * Travel Analysis routes — Phase 7.
 *
 * POST /v1/comparisons/:id/travel-analysis         — trigger travel analysis
 * GET  /v1/comparisons/:id/travel-analysis         — get result
 * GET  /v1/comparisons/:id/travel-analysis/changes         — detected changes
 * GET  /v1/comparisons/:id/travel-analysis/transformations — detected transformations
 * GET  /v1/comparisons/:id/travel-analysis/metadata        — metadata changes
 *
 * All routes enforce owner isolation.
 * Transport transformations are clearly separated from content changes.
 *
 * IMPORTANT: "TRANSFORMED_COPY" is NOT a content-manipulation verdict.
 * Compression, resizing, and metadata stripping are benign platform transformations.
 */
import { Router } from 'express';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { uuidParamSchema } from '../schemas/index.js';
import { getPrisma } from '../config/prisma.js';
import { getEnv } from '../config/env.js';
import { getLogger } from '../config/logger.js';
import { notFound } from '../errors.js';

export const travelRouter = Router();

// POST /v1/comparisons/:id/travel-analysis
travelRouter.post(
  '/:id/travel-analysis',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const log = getLogger();
      const env = getEnv();

      const comparison = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
        include: { referenceImage: true, suspectImage: true },
      });
      if (!comparison) return next(notFound('Comparison not found'));

      // Upsert travel analysis record
      const existing = await prisma.travelAnalysis.findUnique({
        where: { comparisonId: comparison.id },
      });
      const record = existing
        ? await prisma.travelAnalysis.update({
            where: { comparisonId: comparison.id },
            data: { status: 'QUEUED', error: null },
          })
        : await prisma.travelAnalysis.create({
            data: { comparisonId: comparison.id, status: 'QUEUED' },
          });

      // Fire-and-forget
      setImmediate(async () => {
        try {
          const path = await import('node:path');
          const fs = await import('node:fs/promises');
          const localRoot = path.resolve(process.cwd(), '.local-storage');
          const refPath = path.join(localRoot, 'originals', comparison.referenceImage.storagePath);
          const susPath = path.join(localRoot, 'originals', comparison.suspectImage.storagePath);

          let refBuf: Buffer, susBuf: Buffer;
          try {
            refBuf = await fs.readFile(refPath);
            susBuf = await fs.readFile(susPath);
          } catch {
            await prisma.travelAnalysis.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: 'Could not load image files' },
            });
            return;
          }

          // Load metadata from DB
          const refMeta = await prisma.imageMetadata.findUnique({
            where: { imageId: comparison.referenceImageId },
          });
          const susMeta = await prisma.imageMetadata.findUnique({
            where: { imageId: comparison.suspectImageId },
          });

          const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/travel-analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              reference_hex: refBuf.toString('hex'),
              suspect_hex: susBuf.toString('hex'),
              reference_metadata: refMeta ? { cameraMake: (refMeta as any).cameraMake, cameraModel: (refMeta as any).cameraModel, software: (refMeta as any).software, hasGps: (refMeta as any).hasGps } : null,
              suspect_metadata: susMeta ? { cameraMake: (susMeta as any).cameraMake, cameraModel: (susMeta as any).cameraModel, software: (susMeta as any).software, hasGps: (susMeta as any).hasGps } : null,
            }),
            signal: AbortSignal.timeout(180_000),
          });

          if (!resp.ok) {
            const err = await resp.text().catch(() => 'unknown');
            await prisma.travelAnalysis.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: `Forensics: ${err}` },
            });
            return;
          }

          const result: any = await resp.json();
          await prisma.travelAnalysis.update({
            where: { id: record.id },
            data: {
              status: result.status ?? 'FAILED',
              transformations: result.transformations ?? null,
              changes: result.changes ?? null,
              metadataChanges: result.metadata_changes ?? null,
              cropResult: result.crop ?? null,
              aiDetectionResult: result.ai_detection ?? null,
              registrationQuality: result.registration_quality ?? null,
              evidence: result.evidence ?? null,
              warnings: result.warnings ?? null,
              analyzerVersion: result.version ?? null,
              executionMs: result.execution_ms ?? null,
              error: result.error ?? null,
            },
          });

          await prisma.auditEvent.create({
            data: {
              eventType: result.status === 'NO_MATCH' ? 'TRAVEL_ANALYSIS_FAILED' : 'TRAVEL_ANALYSIS_COMPLETED',
              resourceId: comparison.id,
              resourceType: 'comparison',
              payload: { status: result.status, transformationCount: (result.transformations ?? []).length },
            },
          });

          log.info({ comparisonId: comparison.id, status: result.status }, 'Travel analysis complete');
        } catch (err) {
          log.error({ err }, 'Travel analysis failed');
          try {
            await prisma.travelAnalysis.update({
              where: { id: record.id },
              data: { status: 'FAILED', error: err instanceof Error ? err.message : String(err) },
            });
          } catch { /* ignore */ }
        }
      });

      res.status(202).json({
        comparisonId: comparison.id,
        travelAnalysisId: record.id,
        status: 'QUEUED',
        message: 'Travel analysis initiated.',
        note: 'Transport-only transformations (compression, resize, metadata) are NOT classified as content edits.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/travel-analysis
travelRouter.get(
  '/:id/travel-analysis',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!c) return next(notFound('Comparison not found'));

      const ta = await prisma.travelAnalysis.findUnique({
        where: { comparisonId: req.params.id },
      });

      if (!ta) {
        return res.status(202).json({
          status: 'NOT_RUN',
          message: 'Travel analysis has not been triggered.',
          comparisonId: req.params.id,
        });
      }

      res.json({ comparisonId: req.params.id, travelAnalysis: serializeTA(ta) });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/travel-analysis/changes
travelRouter.get(
  '/:id/travel-analysis/changes',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!c) return next(notFound('Comparison not found'));

      const ta = await prisma.travelAnalysis.findUnique({
        where: { comparisonId: req.params.id },
        select: { changes: true, status: true },
      });

      if (!ta) return res.status(202).json({ status: 'NOT_RUN', changes: [] });
      res.json({
        comparisonId: req.params.id,
        status: ta.status,
        changes: ta.changes ?? [],
        note: 'All coordinates in ORIGINAL_IMAGE_COORDINATES.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/travel-analysis/transformations
travelRouter.get(
  '/:id/travel-analysis/transformations',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!c) return next(notFound('Comparison not found'));

      const ta = await prisma.travelAnalysis.findUnique({
        where: { comparisonId: req.params.id },
        select: { transformations: true, status: true, evidence: true },
      });

      if (!ta) return res.status(202).json({ status: 'NOT_RUN', transformations: [] });
      res.json({
        comparisonId: req.params.id,
        status: ta.status,
        transformations: ta.transformations ?? [],
        evidence: ta.evidence ?? [],
        note: 'Transport transformations (JPEG_RECOMPRESSION, RESIZE, METADATA_CHANGE, SCREENSHOT) are platform behaviors, NOT content edits.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/travel-analysis/metadata
travelRouter.get(
  '/:id/travel-analysis/metadata',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!c) return next(notFound('Comparison not found'));

      const ta = await prisma.travelAnalysis.findUnique({
        where: { comparisonId: req.params.id },
        select: { metadataChanges: true, status: true },
      });

      if (!ta) return res.status(202).json({ status: 'NOT_RUN', metadataChanges: [] });
      res.json({
        comparisonId: req.params.id,
        status: ta.status,
        metadataChanges: ta.metadataChanges ?? [],
        note: 'Metadata removal is a common platform behavior and is NOT evidence of manipulation by itself.',
      });
    } catch (err) {
      next(err);
    }
  },
);

function serializeTA(ta: any) {
  return {
    id: ta.id,
    comparisonId: ta.comparisonId,
    status: ta.status,
    transformations: ta.transformations,
    changes: ta.changes,
    metadataChanges: ta.metadataChanges,
    cropResult: ta.cropResult,
    aiDetectionResult: ta.aiDetectionResult,
    registrationQuality: ta.registrationQuality,
    evidence: ta.evidence,
    warnings: ta.warnings,
    analyzerVersion: ta.analyzerVersion,
    executionMs: ta.executionMs,
    error: ta.error,
    createdAt: ta.createdAt?.toISOString(),
  };
}
