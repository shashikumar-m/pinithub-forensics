/**
 * Analysis service — creates analyses, queues jobs, and queries results.
 *
 * Phase 0 behavior:
 *   - Creates an analysis record and queues an associated job.
 *   - Does NOT fabricate detector outputs, scores, or verdicts.
 *   - The job remains QUEUED until a Python worker claims it.
 *   - Since no detector pipeline is implemented in Phase 0, analyses
 *     created here will not produce forensic results yet.
 */
import type { PrismaClient } from '@prisma/client';
import { getPrisma } from '../config/prisma.js';
import { getLogger } from '../config/logger.js';
import { badRequest, notFound } from '../errors.js';
import type { AnalysisType } from '@pinithub/shared';

export interface CreateAnalysisInput {
  ownerId: string;
  imageId: string;
  referenceImageId?: string;
  type: AnalysisType;
}

/**
 * Maps an analysis type to the detector pipeline name.
 * The pipeline names correspond to future Python-service pipelines.
 * No pipeline is implemented in Phase 0, but the job is still queued
 * so the async architecture can be tested end-to-end.
 */
function pipelineForType(type: AnalysisType): string {
  const map: Record<AnalysisType, string> = {
    AI_GENERATED_DETECTION: 'ai-generated',
    AI_EDIT_DETECTION: 'ai-edit',
    REGION_LOCALIZATION: 'region-localization',
    ORIGINAL_VS_COPY: 'original-vs-copy',
    CROP_PERCENTAGE: 'crop-percentage',
    TRAVELLED_COPY: 'travelled-copy',
    METADATA_EXIF: 'metadata-exif',
    COMPREHENSIVE: 'comprehensive',
  };
  return map[type] ?? 'unknown';
}

export class AnalysisService {
  constructor(private prisma: PrismaClient = getPrisma()) {}

  async create(input: CreateAnalysisInput) {
    const log = getLogger();

    // Verify the image exists and belongs to the owner
    const image = await this.prisma.image.findFirst({
      where: { id: input.imageId, ownerId: input.ownerId },
    });
    if (!image) {
      throw notFound('Image not found');
    }

    // Verify reference image if provided
    if (input.referenceImageId) {
      const refImage = await this.prisma.image.findFirst({
        where: { id: input.referenceImageId, ownerId: input.ownerId },
      });
      if (!refImage) {
        throw badRequest('Reference image not found or not owned by caller');
      }
    }

    // Create analysis + queue a job in a transaction
    const analysis = await this.prisma.$transaction(async (tx: any) => {
      const created = await tx.analysis.create({
        data: {
          ownerId: input.ownerId,
          imageId: input.imageId,
          referenceImageId: input.referenceImageId ?? null,
          type: input.type,
          status: 'QUEUED',
        },
      });

      await tx.analysisJob.create({
        data: {
          analysisId: created.id,
          status: 'QUEUED',
          pipeline: pipelineForType(input.type),
        },
      });

      await tx.auditEvent.create({
        data: {
          eventType: 'ANALYSIS_CREATED',
          actorId: input.ownerId,
          resourceId: created.id,
          resourceType: 'analysis',
          payload: { analysisType: input.type, imageId: input.imageId },
        },
      });

      return created;
    });

    log.info({ analysisId: analysis.id, type: input.type }, 'Analysis created and job queued');

    // Asynchronously dispatch analysis to forensics pipeline
    setImmediate(() => this._runAnalysis(analysis.id, input.ownerId));

    return analysis;
  }

  async getById(id: string, ownerId: string) {
    const analysis = await this.prisma.analysis.findFirst({
      where: { id, ownerId },
      include: {
        jobs: { orderBy: { createdAt: 'desc' } },
        detectorOutputs: { orderBy: { createdAt: 'desc' } },
        regions: { orderBy: { createdAt: 'desc' } },
      },
    });
    if (!analysis) {
      throw notFound('Analysis not found');
    }
    return analysis;
  }

  async list(ownerId: string, opts: { page: number; pageSize: number; status?: string; type?: string }) {
    const where: Record<string, unknown> = { ownerId };
    if (opts.status) where.status = opts.status;
    if (opts.type) where.type = opts.type;

    const [total, items] = await Promise.all([
      this.prisma.analysis.count({ where }),
      this.prisma.analysis.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip: (opts.page - 1) * opts.pageSize,
        take: opts.pageSize,
        include: { jobs: { orderBy: { createdAt: 'desc' }, take: 1 } },
      }),
    ]);

    return { items, total, page: opts.page, pageSize: opts.pageSize };
  }

  async delete(id: string, ownerId: string) {
    const analysis = await this.prisma.analysis.findFirst({
      where: { id, ownerId },
    });
    if (!analysis) {
      throw notFound('Analysis not found');
    }

    await this.prisma.analysis.delete({ where: { id } });

    await this.prisma.auditEvent.create({
      data: {
        eventType: 'RECORD_DELETED',
        actorId: ownerId,
        resourceId: id,
        resourceType: 'analysis',
        payload: {},
      },
    });

    return { id };
  }

  /**
   * Claims the next available QUEUED job using SKIP LOCKED semantics.
   * This allows safe concurrent workers. Returns null if no job is available.
   */
  async claimNextJob(workerId: string): Promise<{ jobId: string; analysisId: string; pipeline: string } | null> {
    const result = await this.prisma.$queryRaw<{ id: string; analysis_id: string; pipeline: string }[]>`
      UPDATE "analysis_jobs"
      SET status = 'RUNNING', "claimed_by" = ${workerId}, "started_at" = NOW(), attempt = attempt + 1
      WHERE id = (
        SELECT id FROM "analysis_jobs"
        WHERE status = 'QUEUED'
        ORDER BY "created_at"
        FOR UPDATE SKIP LOCKED
        LIMIT 1
      )
      RETURNING id, analysis_id, pipeline
    `;

    if (result.length === 0) {
      return null;
    }

    const job = result[0];
    await this.prisma.auditEvent.create({
      data: {
        eventType: 'JOB_CLAIMED',
        resourceId: job.id,
        resourceType: 'analysis_job',
        payload: { workerId },
      },
    });

    return { jobId: job.id, analysisId: job.analysis_id, pipeline: job.pipeline };
  }

  private async _loadImageBuffer(storagePath: string): Promise<Buffer | null> {
    try {
      const path = await import('node:path');
      const fs = await import('node:fs/promises');
      const localRoot = path.resolve(process.cwd(), '.local-storage');
      const fullPath = path.join(localRoot, 'originals', storagePath);
      return await fs.readFile(fullPath);
    } catch {
      return null;
    }
  }

  async _runAnalysis(analysisId: string, _ownerId: string) {
    const log = getLogger();
    try {
      const analysis = await this.prisma.analysis.findUnique({
        where: { id: analysisId },
        include: { image: true, referenceImage: true },
      });
      if (!analysis) return;

      await this.prisma.analysis.update({
        where: { id: analysisId },
        data: { status: 'RUNNING' },
      });

      const suspectBuf = await this._loadImageBuffer(analysis.image.storagePath);
      if (!suspectBuf) {
        log.warn({ analysisId }, 'Image file buffer not found locally, waiting for worker');
        return;
      }

      let referenceBuf: Buffer | null = null;
      if (analysis.referenceImage) {
        referenceBuf = await this._loadImageBuffer(analysis.referenceImage.storagePath);
      }

      const { getEnv } = await import('../config/env.js');
      const env = getEnv();
      const resp = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_hex: suspectBuf.toString('hex'),
          reference_hex: referenceBuf ? referenceBuf.toString('hex') : null,
        }),
        signal: AbortSignal.timeout(180_000),
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => 'unknown error');
        log.warn({ analysisId, errText }, 'Forensics service error during async analysis');
        return;
      }

      const result: any = await resp.json();
      await this.persistAnalysisResult(analysisId, result);
    } catch (err: any) {
      log.error({ err, analysisId }, 'Async analysis execution encountered error');
    }
  }

  async persistAnalysisResult(analysisId: string, result: any) {
    const log = getLogger();
    try {
      await this.prisma.$transaction(async (tx: any) => {
        // Update analysis record
        await tx.analysis.update({
          where: { id: analysisId },
          data: {
            status: 'DONE',
            verdict: result.verdict,
            confidence: result.probability,
          },
        });

        // Mark associated jobs DONE
        await tx.analysisJob.updateMany({
          where: { analysisId, status: { in: ['QUEUED', 'RUNNING'] } },
          data: { status: 'DONE', completedAt: new Date() },
        });

        // Save detector outputs
        if (Array.isArray(result.evidence)) {
          for (const ev of result.evidence) {
            const validCategories = [
              'AI_GENERATED', 'AI_EDITED', 'ELA', 'NOISE_RESIDUAL', 'DCT',
              'JPEG_DOUBLE_COMPRESSION', 'COPY_MOVE', 'KEYPOINT_MATCH',
              'CROP_PERCENTAGE', 'TRAVELLED_COPY', 'METADATA',
            ];
            const category = validCategories.includes(ev.category) ? ev.category : 'METADATA';

            await tx.detectorOutput.create({
              data: {
                analysisId,
                detector: ev.detector || 'unknown',
                version: ev.version || '1.0.0',
                category: category as any,
                status: 'DONE',
                score: typeof ev.score === 'number' ? ev.score : null,
                confidence: typeof ev.reliability === 'number' ? ev.reliability : null,
                details: {
                  tag: ev.tag,
                  notes: ev.notes,
                },
              },
            });
          }
        }
      });
      log.info({ analysisId, verdict: result.verdict }, 'Analysis result successfully persisted to database');
    } catch (err: any) {
      log.error({ err, analysisId }, 'Failed to persist analysis result transaction');
    }
  }
}

// Singleton
let serviceInstance: AnalysisService | null = null;
export function getAnalysisService(): AnalysisService {
  if (!serviceInstance) serviceInstance = new AnalysisService();
  return serviceInstance;
}
