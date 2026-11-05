/**
 * @pinithub/shared — Shared TypeScript types for PINITHUB FORENSICS.
 *
 * These types form the contract between the React frontend and the
 * Node.js API (and indirectly the Python forensic service via the API).
 * Keep this package free of runtime logic — it exports types only so
 * both apps compile against the same shapes.
 */

export * from './types/errors';
export * from './types/image';
export * from './types/analysis';
export * from './types/job';
export * from './types/metadata';
export * from './types/region';
export * from './types/detector';
export * from './types/model';
export * from './types/audit';
export * from './types/api';
export * from './types/comparison';
export * from './types/crop';
export * from './types/ai_detection';
export * from './types/travel';
export * from './types/investigation';
