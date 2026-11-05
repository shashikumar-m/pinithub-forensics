/**
 * Comparison routes — image registration and reference comparison.
 *
 * POST /v1/comparisons              — create comparison job
 * GET  /v1/comparisons              — list comparisons (owner-scoped)
 * GET  /v1/comparisons/:id          — get comparison with diff map + regions
 * GET  /v1/comparisons/:id/registration — registration evidence only
 * GET  /v1/comparisons/:id/differences  — difference map details
 * GET  /v1/comparisons/:id/regions      — candidate changed regions
 *
 * All routes enforce owner isolation.
 * No cross-user comparison is possible.
 */
import { Router } from 'express';
import { z } from 'zod';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { uuidParamSchema } from '../schemas/index.js';
import { getComparisonService } from '../services/comparisonService.js';
import { getPrisma } from '../config/prisma.js';
import { notFound } from '../errors.js';

export const comparisonsRouter = Router();

const createComparisonSchema = z.object({
  referenceImageId: z.string().uuid('referenceImageId must be a valid UUID'),
  suspectImageId: z.string().uuid('suspectImageId must be a valid UUID'),
});

const listQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(50).default(10),
});

// ---- POST /v1/comparisons ----
comparisonsRouter.post(
  '/',
  validate(createComparisonSchema, 'body'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getComparisonService();
      const comparison = await service.create({
        ownerId,
        referenceImageId: req.body.referenceImageId,
        suspectImageId: req.body.suspectImageId,
      });
      res.status(201).json({ comparison: serialize(comparison) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/comparisons ----
comparisonsRouter.get(
  '/',
  validate(listQuerySchema, 'query'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getComparisonService();
      const result = await service.list(ownerId, {
        page: Number(req.query.page),
        pageSize: Number(req.query.pageSize),
      });
      res.json({ ...result, items: result.items.map(serialize) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/comparisons/:id ----
comparisonsRouter.get(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getComparisonService();
      const comparison = await service.getById(req.params.id, ownerId);
      res.json({ comparison: serializeFull(comparison) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/comparisons/:id/registration ----
comparisonsRouter.get(
  '/:id/registration',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
        select: {
          id: true, status: true,
          registrationMethod: true, detectorUsed: true, detectorVersion: true,
          keypointsReference: true, keypointsSuspect: true,
          rawMatches: true, goodMatches: true,
          inlierCount: true, outlierCount: true, inlierRatio: true,
          reprojectionError: true, homographyMatrix: true,
          projectedCorners: true, overlapRatio: true,
          executionTimeMs: true, warnings: true, error: true,
        },
      });
      if (!c) return next(notFound('Comparison not found'));
      res.json({
        comparisonId: req.params.id,
        registration: c,
        note: 'Registration evidence only. No authenticity verdict.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/comparisons/:id/differences ----
comparisonsRouter.get(
  '/:id/differences',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const c = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true, status: true },
      });
      if (!c) return next(notFound('Comparison not found'));

      const diffMap = await prisma.comparisonDiffMap.findUnique({
        where: { comparisonId: req.params.id },
      });

      if (!diffMap) {
        return res.status(202).json({
          status: 'NOT_AVAILABLE',
          message: 'Difference map not yet computed.',
          comparisonId: req.params.id,
        });
      }

      res.json({
        comparisonId: req.params.id,
        differenceMap: {
          id: diffMap.id,
          meanAbsDiff: diffMap.meanAbsDiff,
          medianAbsDiff: diffMap.medianAbsDiff,
          p95AbsDiff: diffMap.p95AbsDiff,
          ssimScore: diffMap.ssimScore,
          noiseFloor: diffMap.noiseFloor,
          diffMethod: diffMap.diffMethod,
          normalizationMethod: diffMap.normalizationMethod,
          absDiffStoragePath: diffMap.absDiffStoragePath,
          ssimMapStoragePath: diffMap.ssimMapStoragePath,
          overlapMaskPath: diffMap.overlapMaskPath,
          alignedSuspectPath: diffMap.alignedSuspectPath,
          createdAt: diffMap.createdAt?.toISOString(),
        },
        note: 'Pixel differences are not automatically evidence of manipulation.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/comparisons/:id/regions ----
comparisonsRouter.get(
  '/:id/regions',
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

      const regions = await prisma.comparisonRegion.findMany({
        where: { comparisonId: req.params.id },
        orderBy: { pixelArea: 'desc' },
      });

      res.json({
        comparisonId: req.params.id,
        regions: regions.map((r: any) => ({
          id: r.id,
          bbox: { x: r.bboxX, y: r.bboxY, width: r.bboxWidth, height: r.bboxHeight },
          pixelArea: r.pixelArea,
          areaPercent: r.areaPercent,
          meanDiffScore: r.meanDiffScore,
          sourceEvidence: r.sourceEvidence,
          maskStoragePath: r.maskStoragePath,
        })),
        total: regions.length,
        note: 'Candidate regions from difference analysis. Not classified as edits yet.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- Serializers ----
function serialize(c: any) {
  return {
    id: c.id,
    ownerId: c.ownerId,
    referenceImageId: c.referenceImageId,
    suspectImageId: c.suspectImageId,
    status: c.status,
    inlierRatio: c.inlierRatio,
    reprojectionError: c.reprojectionError,
    overlapRatio: c.overlapRatio,
    meanAbsDiff: c.meanAbsDiff,
    ssimScore: c.ssimScore,
    executionTimeMs: c.executionTimeMs,
    error: c.error,
    createdAt: c.createdAt?.toISOString(),
    updatedAt: c.updatedAt?.toISOString(),
  };
}

function serializeFull(c: any) {
  return {
    ...serialize(c),
    registrationMethod: c.registrationMethod,
    detectorUsed: c.detectorUsed,
    detectorVersion: c.detectorVersion,
    keypointsReference: c.keypointsReference,
    keypointsSuspect: c.keypointsSuspect,
    rawMatches: c.rawMatches,
    goodMatches: c.goodMatches,
    inlierCount: c.inlierCount,
    outlierCount: c.outlierCount,
    reprojectionError: c.reprojectionError,
    homographyMatrix: c.homographyMatrix,
    projectedCorners: c.projectedCorners,
    overlapRatio: c.overlapRatio,
    warnings: c.warnings,
    differenceMap: c.differenceMap ? {
      meanAbsDiff: c.differenceMap.meanAbsDiff,
      ssimScore: c.differenceMap.ssimScore,
      noiseFloor: c.differenceMap.noiseFloor,
    } : null,
    regions: (c.regions ?? []).map((r: any) => ({
      id: r.id,
      bbox: { x: r.bboxX, y: r.bboxY, width: r.bboxWidth, height: r.bboxHeight },
      pixelArea: r.pixelArea,
      areaPercent: r.areaPercent,
      meanDiffScore: r.meanDiffScore,
      sourceEvidence: r.sourceEvidence,
    })),
  };
}


// ---- Phase 5: Crop Detection endpoints ----

// POST /v1/comparisons/:id/crop-detection — trigger crop detection
comparisonsRouter.post(
  '/:id/crop-detection',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const env = (await import('../config/env.js')).getEnv();
      const log = (await import('../config/logger.js')).getLogger();

      // Verify ownership
      const comparison = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
        include: { referenceImage: true, suspectImage: true },
      });
      if (!comparison) return next(notFound('Comparison not found'));

      // Create/update crop detection record as QUEUED
      let cropRecord = await prisma.cropDetection.findUnique({
        where: { comparisonId: comparison.id },
      });

      if (!cropRecord) {
        cropRecord = await prisma.cropDetection.create({
          data: {
            comparisonId: comparison.id,
            status: 'INCONCLUSIVE',
            originalAreaPixels: (comparison.referenceImage.width ?? 0) * (comparison.referenceImage.height ?? 0),
          },
        });
      }

      // Fire-and-forget: run crop detection via Python service
      setImmediate(async () => {
        try {
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
            await prisma.cropDetection.update({
              where: { id: cropRecord.id },
              data: { status: 'FAILED', error: 'Could not load image files' },
            });
            return;
          }

          const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/crop-detect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              reference_hex: refBuf.toString('hex'),
              suspect_hex: susBuf.toString('hex'),
            }),
            signal: AbortSignal.timeout(120_000),
          });

          if (!resp.ok) {
            const err = await resp.text().catch(() => 'unknown');
            await prisma.cropDetection.update({
              where: { id: cropRecord.id },
              data: { status: 'FAILED', error: `Forensics service error: ${err}` },
            });
            return;
          }

          const result: any = await resp.json();
          const details = result.details ?? {};
          const cropData = details;

          await prisma.cropDetection.update({
            where: { id: cropRecord.id },
            data: {
              status: cropData.status ?? 'FAILED',
              cropPercentage: cropData.crop_percentage ?? null,
              keptPercentage: cropData.kept_percentage ?? null,
              originalAreaPixels: cropData.original_area_pixels ?? cropRecord.originalAreaPixels,
              keptAreaPixels: cropData.kept_area_pixels ?? null,
              removedAreaPixels: cropData.removed_area_pixels ?? null,
              cropPolygon: cropData.crop_polygon ?? null,
              boundingBox: cropData.bounding_box ?? null,
              confidence: cropData.confidence ?? null,
              reliability: cropData.reliability ?? 'UNCALIBRATED',
              registrationQuality: cropData.registration_quality ?? null,
              method: cropData.method ?? 'homography_inverse_projection',
              detectorName: cropData.detector ?? 'crop_detector',
              detectorVersion: cropData.version ?? '1.0.0',
              executionMs: result.execution_time_ms ?? null,
              warnings: cropData.warnings ?? null,
              error: cropData.error ?? null,
            },
          });

          await prisma.auditEvent.create({
            data: {
              eventType: cropData.status === 'DETECTED' ? 'CROP_DETECTED' : 'CROP_DETECTION_FAILED',
              resourceId: comparison.id,
              resourceType: 'comparison',
              payload: { cropStatus: cropData.status, cropPercentage: cropData.crop_percentage },
            },
          });

          log.info({ comparisonId: comparison.id, cropStatus: cropData.status }, 'Crop detection completed');
        } catch (err) {
          log.error({ err }, 'Crop detection pipeline failed');
          try {
            await prisma.cropDetection.update({
              where: { id: cropRecord.id },
              data: { status: 'FAILED', error: err instanceof Error ? err.message : String(err) },
            });
          } catch { /* ignore */ }
        }
      });

      res.status(202).json({
        comparisonId: comparison.id,
        cropDetectionId: cropRecord.id,
        status: 'QUEUED',
        message: 'Crop detection initiated. Poll GET /v1/comparisons/:id/crop-detection for results.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/crop-detection — get crop detection result
comparisonsRouter.get(
  '/:id/crop-detection',
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

      const crop = await prisma.cropDetection.findUnique({
        where: { comparisonId: req.params.id },
      });

      if (!crop) {
        return res.status(202).json({
          status: 'NOT_RUN',
          message: 'Crop detection has not been triggered for this comparison.',
          comparisonId: req.params.id,
        });
      }

      res.json({
        comparisonId: req.params.id,
        cropDetection: {
          id: crop.id,
          status: crop.status,
          cropPercentage: crop.cropPercentage,
          keptPercentage: crop.keptPercentage,
          originalAreaPixels: crop.originalAreaPixels,
          keptAreaPixels: crop.keptAreaPixels,
          removedAreaPixels: crop.removedAreaPixels,
          cropPolygon: crop.cropPolygon,
          boundingBox: crop.boundingBox,
          confidence: crop.confidence,
          reliability: crop.reliability,
          registrationQuality: crop.registrationQuality,
          method: crop.method,
          detectorName: crop.detectorName,
          detectorVersion: crop.detectorVersion,
          executionMs: crop.executionMs,
          warnings: crop.warnings,
          error: crop.error,
          coordinateSystem: 'ORIGINAL_IMAGE_COORDINATES',
          createdAt: crop.createdAt?.toISOString(),
        },
        note: 'Crop percentage represents the portion of the original image that was removed. All coordinates are in original image space.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/comparisons/:id/crop-detection/footprint — get crop footprint
comparisonsRouter.get(
  '/:id/crop-detection/footprint',
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

      const crop = await prisma.cropDetection.findUnique({
        where: { comparisonId: req.params.id },
        select: {
          status: true,
          cropPolygon: true,
          boundingBox: true,
          originalAreaPixels: true,
          keptAreaPixels: true,
          removedAreaPixels: true,
          keptPercentage: true,
          cropPercentage: true,
        },
      });

      if (!crop) {
        return res.status(202).json({
          status: 'NOT_RUN',
          message: 'Crop detection has not been run.',
        });
      }

      res.json({
        comparisonId: req.params.id,
        footprint: {
          status: crop.status,
          polygon: crop.cropPolygon,
          boundingBox: crop.boundingBox,
          coordinateSystem: 'ORIGINAL_IMAGE_COORDINATES',
          originalAreaPixels: crop.originalAreaPixels,
          keptAreaPixels: crop.keptAreaPixels,
          removedAreaPixels: crop.removedAreaPixels,
          keptPercentage: crop.keptPercentage,
          cropPercentage: crop.cropPercentage,
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- DELETE /v1/comparisons/:id ----
comparisonsRouter.delete(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const comparison = await prisma.imageComparison.findFirst({
        where: { id: req.params.id, ownerId },
      });
      if (!comparison) return next(notFound('Comparison not found'));

      // Hard-delete the comparison (cascades to diff maps, regions, crop, travel, investigation)
      await prisma.imageComparison.delete({ where: { id: req.params.id } });

      res.status(204).send();
    } catch (err) {
      next(err);
    }
  },
);
