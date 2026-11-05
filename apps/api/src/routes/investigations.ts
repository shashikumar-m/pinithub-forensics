/**
 * Investigation routes — Phase 8.
 *
 * POST /v1/investigations                        — create investigation (fuse all evidence)
 * GET  /v1/investigations/:id                    — get full investigation
 * GET  /v1/investigations/:id/evidence           — evidence items
 * GET  /v1/investigations/:id/regions            — fused regions
 * POST /v1/investigations/:id/report             — generate JSON + text report
 * GET  /v1/investigations/:id/report             — get report
 * GET  /v1/investigations/:id/report.json        — download canonical JSON
 * POST /v1/investigations/:id/seal               — create tamper-evident seal
 * GET  /v1/investigations/:id/seal               — get sealed record
 *
 * All routes enforce owner isolation.
 * No cross-user investigation is possible.
 */
import { Router } from 'express';
import { z } from 'zod';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { uuidParamSchema } from '../schemas/index.js';
import { getPrisma } from '../config/prisma.js';
import { getEnv } from '../config/env.js';
import { getLogger } from '../config/logger.js';
import { notFound, badRequest } from '../errors.js';

export const investigationsRouter = Router();

const createInvestigationSchema = z.object({
  comparisonId: z.string().uuid('comparisonId must be a valid UUID'),
});

// ---- POST /v1/investigations ----
investigationsRouter.post(
  '/',
  validate(createInvestigationSchema, 'body'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const log = getLogger();
      const env = getEnv();

      // Verify comparison ownership
      const comparison = await prisma.imageComparison.findFirst({
        where: { id: req.body.comparisonId, ownerId },
        include: {
          referenceImage: { include: { metadata: true } },
          suspectImage: { include: { metadata: true } },
          travelAnalysis: true,
          cropDetection: true,
        },
      });
      if (!comparison) return next(notFound('Comparison not found'));

      // Create investigation record
      const investigation = await prisma.investigation.create({
        data: {
          ownerId,
          comparisonId: comparison.id,
          referenceImageId: comparison.referenceImageId,
          suspectImageId: comparison.suspectImageId,
          status: 'PENDING',
        },
      });

      await prisma.auditEvent.create({
        data: {
          eventType: 'INVESTIGATION_CREATED',
          actorId: ownerId,
          resourceId: investigation.id,
          resourceType: 'investigation',
          payload: { comparisonId: comparison.id },
        },
      });

      // Fire-and-forget pipeline
      setImmediate(async () => {
        try {
          await prisma.investigation.update({
            where: { id: investigation.id },
            data: { status: 'RUNNING' },
          });

          // Load image files
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
            await prisma.investigation.update({
              where: { id: investigation.id },
              data: { status: 'FAILED', error: 'Could not load image files' },
            });
            return;
          }

          // Build metadata objects
          const refMeta: any = comparison.referenceImage?.metadata ?? null;
          const susMeta: any = comparison.suspectImage?.metadata ?? null;

          const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/investigate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              reference_hex: refBuf.toString('hex'),
              suspect_hex: susBuf.toString('hex'),
              reference_metadata: refMeta ? {
                cameraMake: refMeta.cameraMake, cameraModel: refMeta.cameraModel,
                software: refMeta.software, hasGps: refMeta.hasGps,
                sha256: comparison.referenceImage.sha256,
                originalFilename: comparison.referenceImage.originalFilename,
                mimeType: comparison.referenceImage.mimeType,
                format: comparison.referenceImage.format,
                sizeBytes: Number(comparison.referenceImage.sizeBytes),
                width: comparison.referenceImage.width,
                height: comparison.referenceImage.height,
              } : null,
              suspect_metadata: susMeta ? {
                cameraMake: susMeta.cameraMake, cameraModel: susMeta.cameraModel,
                software: susMeta.software, hasGps: susMeta.hasGps,
                sha256: comparison.suspectImage.sha256,
                originalFilename: comparison.suspectImage.originalFilename,
                mimeType: comparison.suspectImage.mimeType,
                format: comparison.suspectImage.format,
                sizeBytes: Number(comparison.suspectImage.sizeBytes),
                width: comparison.suspectImage.width,
                height: comparison.suspectImage.height,
              } : null,
              investigation_id: investigation.id,
            }),
            signal: AbortSignal.timeout(300_000),
          });

          if (!resp.ok) {
            const err = await resp.text().catch(() => 'unknown');
            await prisma.investigation.update({
              where: { id: investigation.id },
              data: { status: 'FAILED', error: `Forensics: ${err}` },
            });
            return;
          }

          const result: any = await resp.json();
          const verdict = result.verdict ?? 'INCONCLUSIVE';

          // Persist investigation + evidence + regions + assessment atomically
          await prisma.$transaction(async (tx: any) => {
            // Update investigation
            await tx.investigation.update({
              where: { id: investigation.id },
              data: {
                status: 'COMPLETED',
                verdict,
                confidenceStatus: result.confidenceStatus ?? 'UNCALIBRATED',
                evidenceStrength: result.evidenceStrength ?? 'INSUFFICIENT',
                fusionVersion: result.evidenceItems?.[0]?.fusionVersion ?? 'fusion_logistic_v1',
                explanation: result.explanation,
                executionMs: null,
              },
            });

            // Evidence items
            for (const ev of (result.evidenceItems ?? [])) {
              await tx.investigationEvidence.create({
                data: {
                  investigationId: investigation.id,
                  category: ev.category ?? 'OTHER',
                  detector: ev.detector ?? 'unknown',
                  version: ev.version ?? '0',
                  status: ev.status ?? 'UNAVAILABLE',
                  score: ev.score ?? null,
                  description: ev.description ?? '',
                  rawResult: ev.raw_result ?? null,
                  evidenceGroup: ev.evidence_group ?? null,
                  executionMs: ev.execution_ms ?? null,
                  warnings: ev.warnings ?? null,
                },
              });
            }

            // Regions
            for (const region of (result.regions ?? [])) {
              const bbox = region.bbox ?? {};
              await tx.finalRegion.create({
                data: {
                  investigationId: investigation.id,
                  type: region.type ?? 'UNKNOWN',
                  bboxX: bbox.x ?? 0,
                  bboxY: bbox.y ?? 0,
                  bboxWidth: bbox.width ?? 0,
                  bboxHeight: bbox.height ?? 0,
                  polygon: region.polygon ?? null,
                  areaPixels: region.areaPixels ?? 0,
                  areaPercentage: region.areaPercentage ?? 0,
                  confidence: region.confidence ?? null,
                  evidenceCount: region.evidenceCount ?? 1,
                  sourceDetectors: region.sourceDetectors ?? null,
                },
              });
            }

            // Final assessment
            await tx.finalAssessment.upsert({
              where: { investigationId: investigation.id },
              create: {
                investigationId: investigation.id,
                verdict,
                confidenceStatus: result.confidenceStatus ?? 'UNCALIBRATED',
                evidenceStrength: result.evidenceStrength ?? 'INSUFFICIENT',
                explanation: result.explanation ?? '',
                evidenceIds: (result.evidenceItems ?? []).map((e: any) => e.id),
                warnings: result.warnings ?? null,
                fusionVersion: 'fusion_logistic_v1',
                calibrationMethod: 'NONE',
              },
              update: {
                verdict,
                explanation: result.explanation ?? '',
                evidenceStrength: result.evidenceStrength ?? 'INSUFFICIENT',
              },
            });

            // Report
            await tx.investigationReport.create({
              data: {
                investigationId: investigation.id,
                schemaVersion: '1.0',
                reportJson: result.report ?? null,
                reportHash: result.reportHash ?? null,
              },
            });

            await tx.auditEvent.create({
              data: {
                eventType: 'INVESTIGATION_COMPLETED',
                actorId: ownerId,
                resourceId: investigation.id,
                resourceType: 'investigation',
                payload: { verdict, reportHash: result.reportHash },
              },
            });
          });

          log.info({ investigationId: investigation.id, verdict }, 'Investigation completed');
        } catch (err) {
          log.error({ err }, 'Investigation pipeline failed');
          try {
            await prisma.investigation.update({
              where: { id: investigation.id },
              data: { status: 'FAILED', error: err instanceof Error ? err.message : String(err) },
            });
          } catch { /* ignore */ }
        }
      });

      res.status(202).json({
        investigationId: investigation.id,
        comparisonId: comparison.id,
        status: 'PENDING',
        message: 'Investigation initiated. Poll GET /v1/investigations/:id',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id ----
investigationsRouter.get(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId },
        include: {
          evidenceItems: true,
          finalRegions: true,
          assessments: true,
          reports: { orderBy: { createdAt: 'desc' }, take: 1 },
        },
      });
      if (!inv) return next(notFound('Investigation not found'));

      res.json({ investigation: serializeInvestigation(inv) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id/evidence ----
investigationsRouter.get(
  '/:id/evidence',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!inv) return next(notFound('Investigation not found'));
      const items = await prisma.investigationEvidence.findMany({
        where: { investigationId: req.params.id },
        orderBy: [{ category: 'asc' }],
      });
      res.json({ investigationId: req.params.id, items, total: items.length });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id/regions ----
investigationsRouter.get(
  '/:id/regions',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!inv) return next(notFound('Investigation not found'));
      const regions = await prisma.finalRegion.findMany({
        where: { investigationId: req.params.id },
        orderBy: { areaPixels: 'desc' },
      });
      res.json({
        investigationId: req.params.id,
        regions: regions.map((r: any) => ({
          id: r.id,
          type: r.type,
          bbox: { x: r.bboxX, y: r.bboxY, width: r.bboxWidth, height: r.bboxHeight },
          polygon: r.polygon,
          areaPixels: r.areaPixels,
          areaPercentage: r.areaPercentage,
          confidence: r.confidence,
          evidenceCount: r.evidenceCount,
          sourceDetectors: r.sourceDetectors,
          coordinateSystem: 'ORIGINAL_IMAGE_COORDINATES',
        })),
        note: 'All coordinates in ORIGINAL_IMAGE_COORDINATES.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id/report ----
investigationsRouter.get(
  '/:id/report',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!inv) return next(notFound('Investigation not found'));
      const report = await prisma.investigationReport.findFirst({
        where: { investigationId: req.params.id },
        orderBy: { createdAt: 'desc' },
      });
      if (!report) return res.status(202).json({ status: 'NOT_GENERATED' });
      res.json({ investigationId: req.params.id, report });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id/report.json ----
investigationsRouter.get(
  '/:id/report.json',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!inv) return next(notFound('Investigation not found'));
      const report = await prisma.investigationReport.findFirst({
        where: { investigationId: req.params.id },
        orderBy: { createdAt: 'desc' },
        select: { reportJson: true, reportHash: true },
      });
      if (!report?.reportJson) return res.status(202).json({ status: 'NOT_GENERATED' });
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Content-Disposition', `attachment; filename="investigation-${req.params.id}.json"`);
      res.send(JSON.stringify(report.reportJson, null, 2));
    } catch (err) {
      next(err);
    }
  },
);

// ---- POST /v1/investigations/:id/seal ----
investigationsRouter.post(
  '/:id/seal',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const log = getLogger();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true, verdict: true },
      });
      if (!inv) return next(notFound('Investigation not found'));

      const report = await prisma.investigationReport.findFirst({
        where: { investigationId: req.params.id },
        orderBy: { createdAt: 'desc' },
      });
      if (!report) return next(badRequest('No report exists to seal. Generate a report first.'));
      if (report.isSealed) {
        return res.json({
          investigationId: req.params.id,
          sealedHash: report.sealedHash,
          sealedAt: report.sealedAt?.toISOString(),
          alreadySealed: true,
        });
      }

      const crypto = await import('node:crypto');
      const reportStr = JSON.stringify(report.reportJson, null, 0);
      const sealedHash = crypto.createHash('sha256').update(reportStr).digest('hex');
      const sealedAt = new Date();

      await prisma.investigationReport.update({
        where: { id: report.id },
        data: {
          isSealed: true,
          sealedAt,
          sealedHash,
        },
      });

      await prisma.auditEvent.create({
        data: {
          eventType: 'REPORT_SEALED',
          actorId: ownerId,
          resourceId: req.params.id,
          resourceType: 'investigation',
          payload: { sealedHash: sealedHash.slice(0, 12) + '…', verdict: inv.verdict },
        },
      });

      log.info({ investigationId: req.params.id, sealedHash }, 'Report sealed');
      res.json({
        investigationId: req.params.id,
        sealedHash,
        sealedAt: sealedAt.toISOString(),
        algorithm: 'SHA-256',
        tamperEvident: true,
        note: 'TAMPER_EVIDENT (not TAMPER_PROOF). Verify by re-hashing the canonical report JSON.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/investigations/:id/seal ----
investigationsRouter.get(
  '/:id/seal',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const inv = await prisma.investigation.findFirst({
        where: { id: req.params.id, ownerId }, select: { id: true },
      });
      if (!inv) return next(notFound('Investigation not found'));
      const report = await prisma.investigationReport.findFirst({
        where: { investigationId: req.params.id },
        select: { isSealed: true, sealedHash: true, sealedAt: true, reportHash: true },
      });
      if (!report || !report.isSealed) {
        return res.status(202).json({ status: 'NOT_SEALED' });
      }
      res.json({
        investigationId: req.params.id,
        isSealed: true,
        sealedHash: report.sealedHash,
        reportHash: report.reportHash,
        sealedAt: report.sealedAt?.toISOString(),
        algorithm: 'SHA-256',
        tamperEvident: true,
      });
    } catch (err) {
      next(err);
    }
  },
);

function serializeInvestigation(inv: any) {
  const report = inv.reports?.[0];
  const assessment = inv.assessments?.[0];
  return {
    id: inv.id,
    ownerId: inv.ownerId,
    comparisonId: inv.comparisonId,
    status: inv.status,
    verdict: inv.verdict,
    confidenceStatus: inv.confidenceStatus,
    evidenceStrength: inv.evidenceStrength,
    explanation: inv.explanation,
    error: inv.error,
    createdAt: inv.createdAt?.toISOString(),
    updatedAt: inv.updatedAt?.toISOString(),
    evidenceCount: inv.evidenceItems?.length ?? 0,
    regionCount: inv.finalRegions?.length ?? 0,
    assessment: assessment ? {
      verdict: assessment.verdict,
      evidenceStrength: assessment.evidenceStrength,
      confidenceStatus: assessment.confidenceStatus,
      fusionVersion: assessment.fusionVersion,
    } : null,
    reportHash: report?.reportHash ?? null,
    isSealed: report?.isSealed ?? false,
    sealedAt: report?.sealedAt?.toISOString() ?? null,
    sealedHash: report?.sealedHash ?? null,
    note: 'Verdict is evidence-based. No authenticity guarantee is implied.',
  };
}
