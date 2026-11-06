/**
 * @pinithub/shared — Shared TypeScript types for PINITHUB FORENSICS.
 *
 * These types form the contract between the React frontend and the
 * Node.js API (and indirectly the Python forensic service via the API).
 * Keep this package free of runtime logic — it exports types only so
 * both apps compile against the same shapes.
 */

export * from './types/errors.js';
export * from './types/image.js';
export * from './types/analysis.js';
export * from './types/job.js';
export * from './types/metadata.js';
export * from './types/region.js';
export * from './types/detector.js';
export * from './types/model.js';
export * from './types/audit.js';
export * from './types/api.js';
export * from './types/comparison.js';
export * from './types/crop.js';
export * from './types/ai_detection.js';
export * from './types/travel.js';
export * from './types/investigation.js';
