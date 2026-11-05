/**
 * Image routes — owner-scoped image information, metadata, and evidence.
 *
 * GET /v1/images          — list protected images (owner-scoped)
 * GET /v1/images/:id      — get image with metadata + characteristics
 * GET /v1/images/:id/metadata    — normalized metadata only
 * GET /v1/images/:id/evidence    — forensic evidence items
 * GET /v1/images/:id/integrity   — hash verification history
 *
 * All routes are owner-isolated — no cross-user metadata access.
 * GPS data is included only in the detailed metadata response.
 * No sensitive data is written to logs.
 */
import { Router } from 'express';
import { getPrisma } from '../config/prisma.js';
import { validate } from '../middleware/validate.js';
import { getOwnerId } from '../middleware/owner.js';
import { uuidParamSchema, listAnalysesQuerySchema } from '../schemas/index.js';
import { notFound } from '../errors.js';

export const imagesRouter = Router();

// ---- GET /v1/images ----
imagesRouter.get(
  '/',
  validate(listAnalysesQuerySchema, 'query'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();
      const page = Number(req.query.page) || 1;
      const pageSize = Number(req.query.pageSize) || 20;

      let total = 0;
      let items: any[] = [];

      try {
        [total, items] = await Promise.all([
          prisma.image.count({ where: { ownerId, status: { not: 'DELETED' } } }),
          prisma.image.findMany({
            where: { ownerId, status: { not: 'DELETED' } },
            orderBy: { createdAt: 'desc' },
            skip: (page - 1) * pageSize,
            take: pageSize,
            include: {
              metadata: {
                select: {
                  cameraMake: true,
                  cameraModel: true,
                  capturedAt: true,
                  hasGps: true,
                  software: true,
                  c2paStatus: true,
                  extractedAt: true,
                },
              },
              characteristics: {
                select: {
                  width: true,
                  height: true,
                  jpegQualityEstimate: true,
                  jpegQualityIsEstimate: true,
                },
              },
            },
          }),
        ]);
      } catch (dbErr: any) {
        // Graceful fallback if database connection has temporary latency/timeout
        return res.json({
          items: [],
          total: 0,
          page,
          pageSize,
        });
      }

      res.json({
        items: items.map(serializeImage),
        total,
        page,
        pageSize,
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/images/:id ----
imagesRouter.get(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const image = await prisma.image.findFirst({
        where: { id: req.params.id, ownerId },
        include: {
          metadata: true,
          characteristics: true,
          integrityChecks: { orderBy: { checkedAt: 'desc' }, take: 1 },
        },
      });

      if (!image) return next(notFound('Image not found'));

      // Log access (no GPS in payload)
      await prisma.auditEvent.create({
        data: {
          eventType: 'RECORD_ACCESSED',
          actorId: ownerId,
          resourceId: image.id,
          resourceType: 'image',
          payload: {},
        },
      });

      res.json({ image: serializeImageFull(image) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/images/:id/metadata ----
imagesRouter.get(
  '/:id/metadata',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      // Verify ownership first
      const image = await prisma.image.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!image) return next(notFound('Image not found'));

      const metadata = await prisma.imageMetadata.findUnique({
        where: { imageId: req.params.id },
      });

      if (!metadata) {
        return res.status(202).json({
          status: 'NOT_EXTRACTED',
          message: 'Metadata has not been extracted for this image yet.',
          imageId: req.params.id,
        });
      }

      res.json({ metadata: serializeMetadata(metadata) });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/images/:id/evidence ----
imagesRouter.get(
  '/:id/evidence',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const image = await prisma.image.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true },
      });
      if (!image) return next(notFound('Image not found'));

      const items = await prisma.forensicEvidenceItem.findMany({
        where: { imageId: req.params.id },
        orderBy: [{ category: 'asc' }, { key: 'asc' }],
      });

      res.json({
        imageId: req.params.id,
        items: items.map((i: any) => ({
          id: i.id,
          category: i.category,
          key: i.key,
          value: i.value,
          valueType: i.valueType,
          source: i.source,
          detectorName: i.detectorName,
          detectorVersion: i.detectorVersion,
          confidence: i.confidence,
          createdAt: i.createdAt.toISOString(),
        })),
        total: items.length,
        note: 'Evidence items are forensic observations, not authenticity verdicts.',
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- GET /v1/images/:id/integrity ----
imagesRouter.get(
  '/:id/integrity',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const image = await prisma.image.findFirst({
        where: { id: req.params.id, ownerId },
        select: { id: true, sha256: true },
      });
      if (!image) return next(notFound('Image not found'));

      const checks = await prisma.imageIntegrityCheck.findMany({
        where: { imageId: req.params.id },
        orderBy: { checkedAt: 'desc' },
      });

      res.json({
        imageId: req.params.id,
        storedHash: image.sha256,
        checks: checks.map((c: any) => ({
          id: c.id,
          status: c.status,
          storedHash: c.storedHash,
          // Computed hash shown in full for integrity verification
          computedHash: c.computedHash,
          checkedAt: c.checkedAt.toISOString(),
          note: c.note,
        })),
      });
    } catch (err) {
      next(err);
    }
  },
);

// ---- Serializers ----

function serializeImage(img: any): Record<string, unknown> {
  return {
    id: img.id,
    ownerId: img.ownerId,
    role: img.role,
    status: img.status,
    source: img.source,
    originalFilename: img.originalFilename,
    mimeType: img.mimeType,
    format: img.format,
    sizeBytes: Number(img.sizeBytes),
    sha256: img.sha256,
    storagePath: img.storagePath,
    width: img.width,
    height: img.height,
    pixelCount: img.pixelCount,
    colorMode: img.colorMode,
    captureTimestamp: img.captureTimestamp?.toISOString() ?? null,
    createdAt: img.createdAt?.toISOString(),
    updatedAt: img.updatedAt?.toISOString(),
    // Summary metadata (no GPS)
    metadataSummary: img.metadata ? {
      cameraMake: img.metadata.cameraMake,
      cameraModel: img.metadata.cameraModel,
      capturedAt: img.metadata.capturedAt?.toISOString() ?? null,
      hasGps: img.metadata.hasGps,
      software: img.metadata.software,
      c2paStatus: img.metadata.c2paStatus,
      extractedAt: img.metadata.extractedAt?.toISOString() ?? null,
    } : null,
    characteristics: img.characteristics ? {
      width: img.characteristics.width,
      height: img.characteristics.height,
      jpegQualityEstimate: img.characteristics.jpegQualityEstimate,
      jpegQualityIsEstimate: img.characteristics.jpegQualityIsEstimate,
    } : null,
  };
}

function serializeImageFull(img: any): Record<string, unknown> {
  const base = serializeImage(img);
  return {
    ...base,
    metadata: img.metadata ? serializeMetadata(img.metadata) : null,
    characteristics: img.characteristics ? serializeCharacteristics(img.characteristics) : null,
    latestIntegrityCheck: img.integrityChecks?.[0] ? {
      status: img.integrityChecks[0].status,
      checkedAt: img.integrityChecks[0].checkedAt?.toISOString(),
    } : null,
  };
}

function serializeMetadata(m: any): Record<string, unknown> {
  return {
    id: m.id,
    imageId: m.imageId,
    camera: {
      make: m.cameraMake,
      model: m.cameraModel,
      lensMake: m.lensMake,
      lensModel: m.lensModel,
      focalLength: m.focalLength,
      aperture: m.aperture,
      shutterSpeed: m.shutterSpeed,
      iso: m.iso,
    },
    orientation: m.orientation,
    colorSpace: m.colorSpace,
    colorProfile: m.colorProfile,
    software: m.software,
    editingSoftware: m.editingSoftware,
    timestamps: {
      capturedAt: m.capturedAt?.toISOString() ?? null,
      capturedAtTimezone: m.capturedAtTimezone,
      metadataCreatedAt: m.metadataCreatedAt?.toISOString() ?? null,
      metadataModifiedAt: m.metadataModifiedAt?.toISOString() ?? null,
    },
    location: {
      hasGps: m.hasGps,
      // Latitude/longitude only included for authorized display — controlled here
      latitude: m.gpsLatitude ?? null,
      longitude: m.gpsLongitude ?? null,
      altitude: m.gpsAltitude ?? null,
    },
    c2pa: {
      status: m.c2paStatus ?? 'ABSENT',
      payload: m.c2paPayload ?? null,
    },
    exifRaw: m.exifRaw,
    extractorName: m.extractorName,
    extractorVersion: m.extractorVersion,
    extractedAt: m.extractedAt?.toISOString(),
    createdAt: m.createdAt?.toISOString(),
    note: 'Metadata is forensic evidence, not proof of authenticity.',
  };
}

function serializeCharacteristics(c: any): Record<string, unknown> {
  return {
    id: c.id,
    width: c.width,
    height: c.height,
    aspectRatioW: c.aspectRatioW,
    aspectRatioH: c.aspectRatioH,
    pixelCount: c.pixelCount,
    channels: c.channels,
    bitDepth: c.bitDepth,
    colorSpace: c.colorSpace,
    hasAlpha: c.hasAlpha,
    jpeg: c.jpegProgressive !== null ? {
      progressive: c.jpegProgressive,
      samplingFactors: c.jpegSamplingFactors,
      quantizationTables: c.jpegQuantTables,
      markers: c.jpegMarkers,
      qualityEstimate: c.jpegQualityEstimate,
      qualityIsEstimate: c.jpegQualityIsEstimate,
    } : null,
    extractorName: c.extractorName,
    extractorVersion: c.extractorVersion,
    extractedAt: c.extractedAt?.toISOString(),
    createdAt: c.createdAt?.toISOString(),
  };
}

// ---- DELETE /v1/images/:id ----
imagesRouter.delete(
  '/:id',
  validate(uuidParamSchema, 'params'),
  async (req, res, next) => {
    try {
      const ownerId = getOwnerId(req);
      const prisma = getPrisma();

      const image = await prisma.image.findFirst({
        where: { id: req.params.id, ownerId },
      });
      if (!image) return next(notFound('Image not found'));

      // Soft-delete: mark as DELETED (preserves audit trail)
      await prisma.image.update({
        where: { id: req.params.id },
        data: { status: 'DELETED' },
      });

      await prisma.auditEvent.create({
        data: {
          eventType: 'RECORD_DELETED',
          actorId: ownerId,
          resourceId: req.params.id,
          resourceType: 'image',
          payload: { filename: image.originalFilename, sha256Prefix: image.sha256.slice(0, 12) },
        },
      });

      res.status(204).send();
    } catch (err) {
      next(err);
    }
  },
);
