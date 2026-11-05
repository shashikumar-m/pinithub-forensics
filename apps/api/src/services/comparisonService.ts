/**
 * Comparison service — creates and manages image comparison jobs.
 *
 * Coordinates:
 *   - Ownership verification for both reference and suspect images
 *   - Comparison record creation
 *   - Async job dispatch to the Python forensic service
 *   - Result persistence
 *
 * A comparison result is forensic evidence, NOT an authenticity verdict.
 */
import type { PrismaClient } from '@prisma/client';
import { getPrisma } from '../config/prisma.js';
import { getLogger } from '../config/logger.js';
import { getEnv } from '../config/env.js';
import { notFound, badRequest } from '../errors.js';

export interface CreateComparisonInput {
  ownerId: string;
  referenceImageId: string;
  suspectImageId: string;
}

export class ComparisonService {
  constructor(private prisma: PrismaClient = getPrisma()) {}

  async create(input: CreateComparisonInput) {
    const log = getLogger();

    // Verify reference image ownership
    const refImage = await this.prisma.image.findFirst({
      where: { id: input.referenceImageId, ownerId: input.ownerId },
    });
    if (!refImage) throw notFound('Reference image not found');

    // Verify suspect image ownership
    const susImage = await this.prisma.image.findFirst({
      where: { id: input.suspectImageId, ownerId: input.ownerId },
    });
    if (!susImage) throw notFound('Suspect image not found');

    // Prevent comparing an image to itself
    if (input.referenceImageId === input.suspectImageId) {
      throw badRequest('Reference and suspect images must be different');
    }

    const comparison = await this.prisma.$transaction(async (tx: any) => {
      const created = await tx.imageComparison.create({
        data: {
          ownerId: input.ownerId,
          referenceImageId: input.referenceImageId,
          suspectImageId: input.suspectImageId,
          status: 'QUEUED',
        },
      });

      await tx.auditEvent.create({
        data: {
          eventType: 'COMPARISON_CREATED',
          actorId: input.ownerId,
          resourceId: created.id,
          resourceType: 'comparison',
          payload: {
            referenceImageId: input.referenceImageId,
            suspectImageId: input.suspectImageId,
          },
        },
      });

      return created;
    });

    log.info({ comparisonId: comparison.id }, 'Comparison created');

    // Fire-and-forget: run the comparison pipeline
    setImmediate(() => this._runComparison(comparison.id, input.ownerId));

    return comparison;
  }

  private async _runComparison(comparisonId: string, _ownerId: string) {
    const log = getLogger();

    try {
      await this.prisma.imageComparison.update({
        where: { id: comparisonId },
        data: { status: 'RUNNING' },
      });

      // Load both images
      const comparison = await this.prisma.imageComparison.findUnique({
        where: { id: comparisonId },
        include: { referenceImage: true, suspectImage: true },
      });
      if (!comparison) return;

      // Load image files from local storage
      const refBuffer = await this._loadImageBuffer(comparison.referenceImage.storagePath);
      const susBuffer = await this._loadImageBuffer(comparison.suspectImage.storagePath);

      if (!refBuffer || !susBuffer) {
        await this._markFailed(comparisonId, 'Could not load image files from storage');
        return;
      }

      // Call the Python forensic service
      const env = getEnv();
      const response = await fetch(`${env.FORENSICS_SERVICE_URL}/v1/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reference_hex: refBuffer.toString('hex'),
          suspect_hex: susBuffer.toString('hex'),
        }),
        signal: AbortSignal.timeout(120_000), // 2-minute timeout
      });

      if (!response.ok) {
        const err = await response.text().catch(() => 'unknown error');
        await this._markFailed(comparisonId, `Forensics service error: ${err}`);
        return;
      }

      const result: any = await response.json();
      await this._persistResult(comparisonId, result);

      log.info({ comparisonId, status: result.status }, 'Comparison completed');
    } catch (err) {
      log.error({ err, comparisonId }, 'Comparison pipeline failed');
      await this._markFailed(comparisonId, err instanceof Error ? err.message : String(err));
    }
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

  private async _persistResult(comparisonId: string, result: any) {
    const reg = result.registration;
    const diff = result.difference;
    const regions = result.candidate_regions ?? [];

    const status = this._mapStatus(result.status);

    await this.prisma.$transaction(async (tx: any) => {
      // Update comparison record
      await tx.imageComparison.update({
        where: { id: comparisonId },
        data: {
          status: status as any,
          registrationMethod: reg?.parameters?.feature_detector ?? 'sift',
          detectorUsed: reg?.detector ?? 'registration',
          detectorVersion: reg?.detector_version ?? '1.0.0',
          keypointsReference: reg?.keypoints_reference ?? null,
          keypointsSuspect: reg?.keypoints_suspect ?? null,
          rawMatches: reg?.raw_matches ?? null,
          goodMatches: reg?.good_matches ?? null,
          inlierCount: reg?.inlier_count ?? null,
          outlierCount: reg?.outlier_count ?? null,
          inlierRatio: reg?.inlier_ratio ?? null,
          reprojectionError: reg?.reprojection_error ?? null,
          homographyMatrix: reg?.homography_matrix ?? null,
          projectedCorners: reg?.projected_corners ?? null,
          overlapRatio: reg?.overlap_ratio ?? null,
          normalizationMethod: diff?.normalization_applied ?? null,
          meanAbsDiff: diff?.mean_abs_diff ?? null,
          ssimScore: diff?.ssim_score ?? null,
          executionTimeMs: result.execution_time_ms ?? null,
          warnings: result.warnings ?? null,
          error: result.error ?? null,
        },
      });

      // Create diff map record
      if (diff) {
        const artifacts = result.artifacts ?? {};
        await tx.comparisonDiffMap.upsert({
          where: { comparisonId },
          create: {
            comparisonId,
            absDiffStoragePath: artifacts.abs_diff_map ? `comparisons/${comparisonId}/abs_diff.png` : null,
            ssimMapStoragePath: artifacts.ssim_diff_map ? `comparisons/${comparisonId}/ssim_diff.png` : null,
            overlapMaskPath: artifacts.overlap_mask ? `comparisons/${comparisonId}/overlap_mask.png` : null,
            alignedSuspectPath: artifacts.aligned_suspect ? `comparisons/${comparisonId}/aligned.png` : null,
            meanAbsDiff: diff.mean_abs_diff ?? null,
            medianAbsDiff: diff.median_abs_diff ?? null,
            p95AbsDiff: diff.p95_abs_diff ?? null,
            ssimScore: diff.ssim_score ?? null,
            noiseFloor: diff.noise_floor ?? null,
            diffMethod: 'absolute_pixel_difference',
            normalizationMethod: diff.normalization_applied ?? null,
          },
          update: {
            meanAbsDiff: diff.mean_abs_diff ?? null,
            medianAbsDiff: diff.median_abs_diff ?? null,
            p95AbsDiff: diff.p95_abs_diff ?? null,
            ssimScore: diff.ssim_score ?? null,
            noiseFloor: diff.noise_floor ?? null,
          },
        });
      }

      // Create candidate regions
      if (regions.length > 0) {
        await tx.comparisonRegion.deleteMany({ where: { comparisonId } });
        for (const region of regions) {
          await tx.comparisonRegion.create({
            data: {
              comparisonId,
              bboxX: region.bbox.x,
              bboxY: region.bbox.y,
              bboxWidth: region.bbox.width,
              bboxHeight: region.bbox.height,
              pixelArea: region.pixel_area ?? null,
              areaPercent: region.area_percent ?? null,
              meanDiffScore: region.mean_diff_score ?? null,
              sourceEvidence: region.source_evidence ?? null,
            },
          });
        }
      }

      // Audit event
      await tx.auditEvent.create({
        data: {
          eventType: status === 'COMPLETED' ? 'COMPARISON_COMPLETED' : 'COMPARISON_FAILED',
          resourceId: comparisonId,
          resourceType: 'comparison',
          payload: { status },
        },
      });
    });
  }

  private _mapStatus(pyStatus: string): string {
    const map: Record<string, string> = {
      COMPLETED: 'COMPLETED',
      COMPLETED_PARTIAL: 'COMPLETED',
      FAILED: 'FAILED',
      NO_MATCH: 'NO_MATCH',
      INCONCLUSIVE: 'INCONCLUSIVE',
      MATCHING: 'MATCHING',
      REGISTERING: 'REGISTERING',
    };
    return map[pyStatus] ?? 'FAILED';
  }

  private async _markFailed(comparisonId: string, error: string) {
    try {
      await this.prisma.imageComparison.update({
        where: { id: comparisonId },
        data: { status: 'FAILED', error },
      });
    } catch { /* ignore */ }
  }

  async getById(id: string, ownerId: string) {
    const comparison = await this.prisma.imageComparison.findFirst({
      where: { id, ownerId },
      include: {
        differenceMap: true,
        regions: { orderBy: { pixelArea: 'desc' } },
      },
    });
    if (!comparison) throw notFound('Comparison not found');
    return comparison;
  }

  async list(ownerId: string, opts: { page: number; pageSize: number }) {
    const [total, items] = await Promise.all([
      this.prisma.imageComparison.count({ where: { ownerId } }),
      this.prisma.imageComparison.findMany({
        where: { ownerId },
        orderBy: { createdAt: 'desc' },
        skip: (opts.page - 1) * opts.pageSize,
        take: opts.pageSize,
      }),
    ]);
    return { items, total, page: opts.page, pageSize: opts.pageSize };
  }
}

let serviceInstance: ComparisonService | null = null;
export function getComparisonService(): ComparisonService {
  if (!serviceInstance) serviceInstance = new ComparisonService();
  return serviceInstance;
}
