/**
 * Model version routes — registry of detector/model versions.
 *
 * GET    /v1/models          — list model versions
 * POST   /v1/models          — register a new model version
 *
 * Model versions are metadata records for reproducibility. The actual
 * model artifacts are stored in the models storage bucket, not in the DB.
 */
import { Router } from 'express';
import { getPrisma } from '../config/prisma.js';
import { validate } from '../middleware/validate.js';
import { createModelVersionSchema } from '../schemas/index.js';
import { conflict } from '../errors.js';
import { getLogger } from '../config/logger.js';

export const modelsRouter = Router();

// GET /v1/models
modelsRouter.get('/', async (_req, res, next) => {
  try {
    const prisma = getPrisma();
    const models = await prisma.modelVersion.findMany({
      orderBy: { createdAt: 'desc' },
    });
    res.json({ items: models, total: models.length });
  } catch (err) {
    next(err);
  }
});

// POST /v1/models
modelsRouter.post('/', validate(createModelVersionSchema, 'body'), async (req, res, next) => {
  try {
    const log = getLogger();
    const prisma = getPrisma();
    const body = req.body;

    // Check for duplicate name+version
    const existing = await prisma.modelVersion.findUnique({
      where: {
        name_version: { name: body.name, version: body.version },
      },
    });
    if (existing) {
      return next(conflict(`Model ${body.name} v${body.version} already exists`));
    }

    const model = await prisma.modelVersion.create({
      data: {
        name: body.name,
        version: body.version,
        type: body.type,
        category: body.category,
        status: body.status,
        description: body.description ?? null,
      },
    });

    log.info({ modelId: model.id, name: body.name, version: body.version }, 'Model version registered');
    res.status(201).json({ model });
  } catch (err) {
    next(err);
  }
});
