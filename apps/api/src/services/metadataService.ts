/**
 * Metadata service — persists extracted metadata to the database.
 *
 * Responsibilities:
 *   1. Verify SHA-256 integrity of the stored original.
 *   2. Run metadata extraction on the image buffer.
 *   3. Write ImageMetadata, ImageCharacteristics, ForensicEvidenceItems.
 *   4. Record integrity check result.
 *   5. Mark metadata extraction complete on the DetectorOutput.
 *
 * NEVER modifies the original image buffer.
 * NEVER logs GPS coordinates.
 */
import type { PrismaClient } from '@prisma/client';
import { getPrisma } from '../config/prisma.js';
import { getLogger } from '../config/logger.js';
import { computeSha256 } from './storage.js';
import { extractMetadata } from './metadataExtractor.js';

export const METADATA_DETECTOR_NAME = 'metadata_inspector';
export const METADATA_DETECTOR_VERSION = '1.0.0';

export interface MetadataExtractionInput {
  imageId: string;
  ownerId: string;
  buffer: Buffer;
  storedSha256: string;
  analysisId?: string;
}

export interface MetadataExtractionOutput {
  integrityStatus: 'VERIFIED' | 'MISMATCH' | 'SKIPPED' | 'ERROR';
  metadataId: string | null;
  characteristicsId: string | null;
  evidenceCount: number;
  warnings: string[];
}

export class MetadataService {
  constructor(private prisma: PrismaClient = getPrisma()) {}

  /**
   * Full metadata extraction pipeline:
   *   1. Verify SHA-256
   *   2. Extract + normalize metadata
   *   3. Persist all records
   *   4. Create a DetectorOutput record if analysisId is provided
   */
  async extractAndStore(input: MetadataExtractionInput): Promise<MetadataExtractionOutput> {
    const log = getLogger();
    const start = Date.now();

    // ---- 1. SHA-256 integrity verification ----
    let integrityStatus: 'VERIFIED' | 'MISMATCH' | 'ERROR' = 'ERROR';
    let computedHash: string | null = null;
    try {
      computedHash = computeSha256(input.buffer);
      integrityStatus = computedHash === input.storedSha256 ? 'VERIFIED' : 'MISMATCH';
    } catch (err) {
      log.error({ err, imageId: input.imageId }, 'SHA-256 computation failed');
    }

    // Record integrity check
    await this.prisma.imageIntegrityCheck.create({
      data: {
        imageId: input.imageId,
        status: integrityStatus,
        storedHash: input.storedSha256,
        computedHash,
        note: integrityStatus === 'MISMATCH'
          ? 'Hash mismatch detected — stored file may differ from original'
          : null,
      },
    });

    // Audit the integrity result
    await this.prisma.auditEvent.create({
      data: {
        eventType: integrityStatus === 'VERIFIED' ? 'HASH_VERIFIED' : 'HASH_MISMATCH',
        actorId: input.ownerId,
        resourceId: input.imageId,
        resourceType: 'image',
        payload: { integrityStatus, storedHashPrefix: input.storedSha256.slice(0, 12) + '…' },
        // GPS never included in audit payload
      },
    });

    if (integrityStatus === 'MISMATCH') {
      log.warn(
        { imageId: input.imageId, storedPrefix: input.storedSha256.slice(0, 12) },
        'Image hash mismatch — stored file may have changed',
      );
      // Continue extraction — we still record what we find
    }

    // ---- 2. Extract metadata ----
    const { normalized, characteristics, evidenceItems, warnings } = await extractMetadata(input.buffer);

    const now = new Date();

    // ---- 3. Persist ImageMetadata ----
    let metadataRecord: { id: string } | null = null;
    try {
      const loc = normalized.location;
      const ts = normalized.timestamps;

      metadataRecord = await this.prisma.imageMetadata.upsert({
        where: { imageId: input.imageId },
        create: {
          imageId: input.imageId,
          cameraMake: normalized.camera.make,
          cameraModel: normalized.camera.model,
          lensMake: normalized.camera.lensMake,
          lensModel: normalized.camera.lensModel,
          focalLength: normalized.camera.focalLength,
          aperture: normalized.camera.aperture,
          shutterSpeed: normalized.camera.shutterSpeed,
          iso: normalized.camera.iso,
          orientation: normalized.orientation,
          colorSpace: normalized.colorSpace,
          colorProfile: normalized.colorProfile,
          software: normalized.software,
          editingSoftware: normalized.editingSoftware,
          capturedAt: ts.capturedAt ? new Date(ts.capturedAt) : null,
          capturedAtTimezone: ts.capturedAtTimezone,
          metadataCreatedAt: ts.metadataCreatedAt ? new Date(ts.metadataCreatedAt) : null,
          metadataModifiedAt: ts.metadataModifiedAt ? new Date(ts.metadataModifiedAt) : null,
          hasGps: loc.hasGps,
          // GPS stored in DB but never written to logs
          gpsLatitude: loc.latitude,
          gpsLongitude: loc.longitude,
          gpsAltitude: loc.altitude,
          xmpRaw: undefined,
          iptcRaw: undefined,
          comments: undefined,
          c2paStatus: normalized.c2pa.status,
          c2paPayload: normalized.c2pa.payload as any,
          extractorName: METADATA_DETECTOR_NAME,
          extractorVersion: METADATA_DETECTOR_VERSION,
          extractedAt: now,
        },
        update: {
          cameraMake: normalized.camera.make,
          cameraModel: normalized.camera.model,
          lensMake: normalized.camera.lensMake,
          lensModel: normalized.camera.lensModel,
          focalLength: normalized.camera.focalLength,
          aperture: normalized.camera.aperture,
          shutterSpeed: normalized.camera.shutterSpeed,
          iso: normalized.camera.iso,
          orientation: normalized.orientation,
          colorSpace: normalized.colorSpace,
          colorProfile: normalized.colorProfile,
          software: normalized.software,
          editingSoftware: normalized.editingSoftware,
          capturedAt: ts.capturedAt ? new Date(ts.capturedAt) : null,
          capturedAtTimezone: ts.capturedAtTimezone,
          metadataCreatedAt: ts.metadataCreatedAt ? new Date(ts.metadataCreatedAt) : null,
          metadataModifiedAt: ts.metadataModifiedAt ? new Date(ts.metadataModifiedAt) : null,
          hasGps: loc.hasGps,
          gpsLatitude: loc.latitude,
          gpsLongitude: loc.longitude,
          gpsAltitude: loc.altitude,
          c2paStatus: normalized.c2pa.status,
          c2paPayload: normalized.c2pa.payload as any,
          extractorName: METADATA_DETECTOR_NAME,
          extractorVersion: METADATA_DETECTOR_VERSION,
          extractedAt: now,
        },
      });
    } catch (err) {
      log.error({ err, imageId: input.imageId }, 'Failed to store image metadata');
      warnings.push('Metadata storage failed');
    }

    // ---- 4. Persist ImageCharacteristics ----
    let characteristicsRecord: { id: string } | null = null;
    try {
      if (Object.keys(characteristics).length > 0) {
        characteristicsRecord = await this.prisma.imageCharacteristics.upsert({
          where: { imageId: input.imageId },
          create: {
            imageId: input.imageId,
            width: characteristics.width ?? null,
            height: characteristics.height ?? null,
            aspectRatioW: characteristics.aspectRatioW ?? null,
            aspectRatioH: characteristics.aspectRatioH ?? null,
            pixelCount: characteristics.pixelCount ?? null,
            channels: characteristics.channels ?? null,
            bitDepth: characteristics.bitDepth ?? null,
            colorSpace: characteristics.colorSpace ?? null,
            hasAlpha: characteristics.hasAlpha ?? false,
            jpegProgressive: characteristics.jpegProgressive ?? null,
            jpegSamplingFactors: characteristics.jpegSamplingFactors ?? null,
            jpegQuantTables: characteristics.jpegQuantTables as any ?? null,
            jpegMarkers: characteristics.jpegMarkers as any ?? null,
            jpegQualityEstimate: characteristics.jpegQualityEstimate ?? null,
            jpegQualityIsEstimate: characteristics.jpegQualityIsEstimate ?? true,
            extractorName: characteristics.extractorName ?? 'image_characteristics',
            extractorVersion: characteristics.extractorVersion ?? '1.0.0',
            extractedAt: now,
          },
          update: {
            width: characteristics.width ?? null,
            height: characteristics.height ?? null,
            aspectRatioW: characteristics.aspectRatioW ?? null,
            aspectRatioH: characteristics.aspectRatioH ?? null,
            pixelCount: characteristics.pixelCount ?? null,
            channels: characteristics.channels ?? null,
            bitDepth: characteristics.bitDepth ?? null,
            colorSpace: characteristics.colorSpace ?? null,
            hasAlpha: characteristics.hasAlpha ?? false,
            jpegProgressive: characteristics.jpegProgressive ?? null,
            jpegSamplingFactors: characteristics.jpegSamplingFactors ?? null,
            jpegQuantTables: characteristics.jpegQuantTables as any ?? null,
            jpegMarkers: characteristics.jpegMarkers as any ?? null,
            jpegQualityEstimate: characteristics.jpegQualityEstimate ?? null,
            jpegQualityIsEstimate: characteristics.jpegQualityIsEstimate ?? true,
            extractorName: characteristics.extractorName ?? 'image_characteristics',
            extractorVersion: characteristics.extractorVersion ?? '1.0.0',
            extractedAt: now,
          },
        });
      }
    } catch (err) {
      log.error({ err, imageId: input.imageId }, 'Failed to store image characteristics');
      warnings.push('Characteristics storage failed');
    }

    // ---- 5. Persist ForensicEvidenceItems ----
    let evidenceCount = 0;
    try {
      for (const item of evidenceItems) {
        await this.prisma.forensicEvidenceItem.create({
          data: {
            imageId: input.imageId,
            category: item.category,
            key: item.key,
            value: item.value as any,
            valueType: item.valueType,
            source: METADATA_DETECTOR_NAME,
            detectorName: METADATA_DETECTOR_NAME,
            detectorVersion: METADATA_DETECTOR_VERSION,
          },
        });
        evidenceCount++;
      }
    } catch (err) {
      log.error({ err, imageId: input.imageId }, 'Failed to store evidence items');
      warnings.push('Evidence item storage partially failed');
    }

    // ---- 6. Write DetectorOutput if we have an analysisId ----
    if (input.analysisId) {
      const executionMs = Date.now() - start;
      try {
        await this.prisma.detectorOutput.create({
          data: {
            analysisId: input.analysisId,
            detector: METADATA_DETECTOR_NAME,
            version: METADATA_DETECTOR_VERSION,
            category: 'METADATA',
            status: 'DONE',
            details: {
              integrityStatus,
              metadataExtracted: !!metadataRecord,
              characteristicsExtracted: !!characteristicsRecord,
              evidenceItemCount: evidenceCount,
              warnings,
              note: 'Metadata is evidence, not a manipulation verdict',
            } as any,
            executionTimeMs: executionMs,
          },
        });
      } catch (err) {
        log.error({ err }, 'Failed to write DetectorOutput for metadata');
      }
    }

    // Audit extraction event (no GPS in payload)
    await this.prisma.auditEvent.create({
      data: {
        eventType: 'METADATA_EXTRACTED',
        actorId: input.ownerId,
        resourceId: input.imageId,
        resourceType: 'image',
        payload: {
          integrityStatus,
          hasCameraMake: !!normalized.camera.make,
          hasCaptureTime: !!normalized.timestamps.capturedAt,
          hasSoftware: !!normalized.software,
          hasGps: normalized.location.hasGps,
          c2paStatus: normalized.c2pa.status,
          evidenceItems: evidenceCount,
        },
      },
    });

    log.info(
      { imageId: input.imageId, integrityStatus, evidenceCount },
      'Metadata extraction complete',
    );

    return {
      integrityStatus,
      metadataId: metadataRecord?.id ?? null,
      characteristicsId: characteristicsRecord?.id ?? null,
      evidenceCount,
      warnings,
    };
  }
}

let serviceInstance: MetadataService | null = null;
export function getMetadataService(): MetadataService {
  if (!serviceInstance) serviceInstance = new MetadataService();
  return serviceInstance;
}
