/**
 * Zod validation schemas for all API request payloads.
 */
import { z } from 'zod';

// ---- Uploads ----
export const uploadImageSchema = z.object({
  role: z.enum(['ORIGINAL', 'SUSPECT', 'DATASET']).default('SUSPECT'),
  source: z.enum(['CAMERA_CAPTURE', 'FILE_UPLOAD']).default('FILE_UPLOAD'),
  datasetItemId: z.string().uuid().optional(),
  captureTimestamp: z.string().datetime().optional(),
  consentId: z.string().uuid().optional(),
});

// ---- Consents ----
export const createConsentSchema = z.object({
  sourceType: z.enum(['CAMERA_CAPTURE', 'FILE_UPLOAD']),
  consentVersion: z.string().min(1).max(50),
  policyVersion: z.string().max(50).optional(),
});

// ---- Analyses ----
export const createAnalysisSchema = z.object({
  imageId: z.string().uuid('imageId must be a valid UUID'),
  referenceImageId: z.string().uuid().optional(),
  type: z.enum([
    'AI_GENERATED_DETECTION',
    'AI_EDIT_DETECTION',
    'REGION_LOCALIZATION',
    'ORIGINAL_VS_COPY',
    'CROP_PERCENTAGE',
    'TRAVELLED_COPY',
    'METADATA_EXIF',
    'COMPREHENSIVE',
  ]),
});

// ---- Analysis query params (list) ----
export const listAnalysesQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
  status: z
    .enum(['CREATED', 'QUEUED', 'RUNNING', 'DONE', 'FAILED', 'NOT_RUN'])
    .optional(),
  type: z
    .enum([
      'AI_GENERATED_DETECTION',
      'AI_EDIT_DETECTION',
      'REGION_LOCALIZATION',
      'ORIGINAL_VS_COPY',
      'CROP_PERCENTAGE',
      'TRAVELLED_COPY',
      'METADATA_EXIF',
      'COMPREHENSIVE',
    ])
    .optional(),
});

// ---- UUID param ----
export const uuidParamSchema = z.object({
  id: z.string().uuid('id must be a valid UUID'),
});

// ---- Models ----
export const createModelVersionSchema = z.object({
  name: z.string().min(1).max(200),
  version: z.string().min(1).max(50),
  type: z.enum(['CLASSIFIER', 'SEGMENTER', 'DETECTOR', 'COMPARATOR', 'CLASSICAL']),
  category: z.string().min(1).max(200),
  status: z.enum(['DRAFT', 'ACTIVE', 'DEPRECATED']).default('DRAFT'),
  description: z.string().max(2000).optional(),
});
