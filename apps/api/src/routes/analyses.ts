/**
 * Analysis routes — creates, queries, and deletes analyses.
 *
 * POST   /v1/analyses       — create an analysis + queue a job
 * GET    /v1/analyses       — list analyses (paginated)
 * GET    /v1/analyses/:id   — get a single analysis with jobs/outputs/regions
 * DELETE /v1/analyses/:id   — delete an analysis
 *
 * Phase 0 does NOT return fake forensic results. Analyses are created
 * and queued, but detector pipelines are not implemented yet. The
 * status reflects the real state (QUEUED/RUNNING/etc.) — no fabricated
 * scores, verdicts, or confidence values.
 */
import { Router } from 'express';
import multer from 'multer';
import { getEnv } from '../config/env.js';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import {
  createAnalysisSchema,
  listAnalysesQuerySchema,
  uuidParamSchema,
} from '../schemas/index.js';
import { getAnalysisService } from '../services/analyses.js';
import { getPrisma } from '../config/prisma.js';
import { notFound } from '../errors.js';

export const analysesRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 },
});

// POST /v1/analyses/direct — unified analysis on uploaded files or hex
analysesRouter.post(
  '/direct',
  upload.fields([{ name: 'file', maxCount: 1 }, { name: 'reference', maxCount: 1 }]),
  async (req: any, res, next) => {
    try {
      const files = req.files as { [fieldname: string]: Express.Multer.File[] } | undefined;
      let suspectHex: string | null = null;
      let referenceHex: string | null = null;

      if (files?.file?.[0]) {
        suspectHex = files.file[0].buffer.toString('hex');
      } else if (req.body?.image_hex) {
        suspectHex = req.body.image_hex;
      }

      if (files?.reference?.[0]) {
        referenceHex = files.reference[0].buffer.toString('hex');
      } else if (req.body?.reference_hex) {
        referenceHex = req.body.reference_hex;
      }

      if (!suspectHex) {
        return res.status(400).json({ error: { code: 'BAD_REQUEST', message: 'No suspect image provided' } });
      }

      const env = getEnv();
      const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_hex: suspectHex,
          reference_hex: referenceHex,
          params: req.body?.params,
        }),
        signal: AbortSignal.timeout(120_000),
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => 'Forensics service error');
        return res.status(resp.status).json({ error: { code: 'FORENSICS_ERROR', message: errText } });
      }

      const result = await resp.json();
      res.json(result);
    } catch (err) {
      next(err);
    }
  },
);

// POST /v1/analyses
analysesRouter.post(
  '/',
  validate(createAnalysisSchema, 'body'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getAnalysisService();
      const analysis = await service.create({
        ownerId,
        imageId: req.body.imageId,
        referenceImageId: req.body.referenceImageId,
        type: req.body.type,
      });
      res.status(201).json({
        analysis: {
          ...analysis,
          verdict: null,
          confidence: null,
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/analyses
analysesRouter.get(
  '/',
  validate(listAnalysesQuerySchema, 'query'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getAnalysisService();
      try {
        const result = await service.list(ownerId, {
          page: Number(req.query.page),
          pageSize: Number(req.query.pageSize),
          status: req.query.status as string | undefined,
          type: req.query.type as string | undefined,
        });
        res.json(result);
      } catch (dbErr) {
        res.json({
          items: [],
          total: 0,
          page: Number(req.query.page) || 1,
          pageSize: Number(req.query.pageSize) || 20,
        });
      }
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/analyses/:id
analysesRouter.get(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getAnalysisService();
      const analysis = await service.getById(req.params.id, ownerId);
      res.json({ analysis });
    } catch (err) {
      next(err);
    }
  },
);

// DELETE /v1/analyses/:id
analysesRouter.delete(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const service = getAnalysisService();
      await service.delete(req.params.id, ownerId);
      res.status(204).send();
    } catch (err) {
      next(err);
    }
  },
);
// ---- Phase 3: Detector output endpoints ----

// GET /v1/analyses/:id/detectors — list all detector outputs
analysesRouter.get(
  '/:id/detectors',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      // Verify ownership
      const analysis = await prisma.analysis.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!analysis) return next(notFound('Analysis not found'));

      const outputs = await prisma.detectorOutput.findMany({
        where: { analysisId: req.params.id },
        orderBy: { createdAt: 'asc' },
      });

      res.json({
        analysisId: req.params.id,
        detectors: outputs.map((o: any) => ({
          id: o.id,
          detector: o.detector,
          version: o.version,
          category: o.category,
          status: o.status,
          score: o.score,
          confidence: o.confidence,
          mapStoragePath: o.mapStoragePath,
          details: o.details,
          executionTimeMs: o.executionTimeMs,
          error: o.error,
          createdAt: o.createdAt?.toISOString(),
          updatedAt: o.updatedAt?.toISOString(),
        })),
        total: outputs.length,
        note: 'These are independent forensic signals. No fusion or final verdict is produced.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/analyses/:id/detectors/:detector — get a specific detector output
analysesRouter.get(
  '/:id/detectors/:detector',
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

      const output = await prisma.detectorOutput.findFirst({
        where: { analysisId: req.params.id, detector: req.params.detector },
        orderBy: { createdAt: 'desc' },
      });

      if (!output) return next(notFound('Detector output not found'));

      res.json({
        analysisId: req.params.id,
        detector: {
          id: output.id,
          detector: output.detector,
          version: output.version,
          category: output.category,
          status: output.status,
          score: output.score,
          confidence: output.confidence,
          mapStoragePath: output.mapStoragePath,
          details: output.details,
          executionTimeMs: output.executionTimeMs,
          error: output.error,
          createdAt: output.createdAt?.toISOString(),
          updatedAt: output.updatedAt?.toISOString(),
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

// GET /v1/analyses/:id/artifacts — list artifacts (detector outputs with maps)
analysesRouter.get(
  '/:id/artifacts',
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

      const outputs = await prisma.detectorOutput.findMany({
        where: { analysisId: req.params.id, NOT: { mapStoragePath: null } },
        orderBy: { createdAt: 'asc' },
        select: {
          id: true,
          detector: true,
          version: true,
          mapStoragePath: true,
          executionTimeMs: true,
          createdAt: true,
        },
      });

      res.json({
        analysisId: req.params.id,
        artifacts: outputs.map((o: any) => ({
          id: o.id,
          detector: o.detector,
          version: o.version,
          artifactPath: o.mapStoragePath,
          executionTimeMs: o.executionTimeMs,
          createdAt: o.createdAt?.toISOString(),
        })),
        total: outputs.length,
      });
    } catch (err) {
      next(err);
    }
  },
);
